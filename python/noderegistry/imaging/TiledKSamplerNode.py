"""
TiledKSamplerNode — KSampler with MultiDiffusion tiled diffusion.

Use this node instead of KSamplerNode when generating images larger than the
model's training resolution (e.g. SD 1.x models trained at 512 px used at
768 px or above).  The UNet sees tile_size × tile_size latent-pixel crops;
overlapping predictions are blended with a Gaussian weight window so seams
are not visible.

Ports
-----
Control in  : exec
Data in     : MODEL, positive (CONDITIONING), negative (CONDITIONING),
              latent_image (LATENT), seed (INT), steps (INT),
              cfg (FLOAT), sampler_name (STRING), scheduler (STRING),
              denoise (FLOAT), tile_size (INT), tile_overlap (INT)
Control out : next, failed
Data out    : LATENT, error (STRING)

tile_size    — tile side in latent pixels; default 64 = 512 image pixels
tile_overlap — overlap between adjacent tiles in latent pixels; default 8 = 64 px
"""

from __future__ import annotations

import asyncio
import threading
from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("TiledKSampler")
class TiledKSamplerNode(Node):
    """
    Tiled-diffusion wrapper around the backend's ``sample_tiled()`` call.

    Port layout mirrors KSamplerNode with two additions: ``tile_size`` and
    ``tile_overlap``.  The cancellation and progress-reporting plumbing is
    identical to KSamplerNode.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step      = True

        self._cancel_event: threading.Event = threading.Event()

        # ── control ──────────────────────────────────────────────────────────
        self.cin_exec         = self.add_control_input('exec')
        self.cout_next        = self.add_control_output('next')
        self.cout_failed      = self.add_control_output('failed')

        # ── data inputs ──────────────────────────────────────────────────────
        self.din_model        = self.add_data_input('MODEL',        data_type=ValueType.MODEL)
        self.din_positive     = self.add_data_input('positive',     data_type=ValueType.CONDITIONING)
        self.din_negative     = self.add_data_input('negative',     data_type=ValueType.CONDITIONING)
        self.din_latent_image = self.add_data_input('latent_image', data_type=ValueType.LATENT)
        self.din_seed         = self.add_data_input('seed',         data_type=ValueType.INT)
        self.din_steps        = self.add_data_input('steps',        data_type=ValueType.INT)
        self.din_cfg          = self.add_data_input('cfg',          data_type=ValueType.FLOAT)
        self.din_sampler_name = self.add_data_input('sampler_name', data_type=ValueType.STRING)
        self.din_scheduler    = self.add_data_input('scheduler',    data_type=ValueType.STRING)
        self.din_denoise      = self.add_data_input('denoise',      data_type=ValueType.FLOAT)
        self.din_tile_size    = self.add_data_input('tile_size',    data_type=ValueType.INT)
        self.din_tile_overlap = self.add_data_input('tile_overlap', data_type=ValueType.INT)

        # ── data outputs ─────────────────────────────────────────────────────
        self.dout_latent      = self.add_data_output('LATENT', data_type=ValueType.LATENT)
        self.dout_error       = self.add_data_output('error',  data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        model         = self.din_model.value
        positive      = self.din_positive.value     or []
        negative      = self.din_negative.value     or []
        latent_image  = self.din_latent_image.value or {}
        seed:         int   = int(self.din_seed.value         or 0)
        steps:        int   = int(self.din_steps.value        or 20)
        cfg:          float = float(self.din_cfg.value         or 7.0)
        sampler:      str   = self.din_sampler_name.value      or 'euler'
        sched:        str   = self.din_scheduler.value         or 'karras'
        denoise:      float = float(self.din_denoise.value     or 1.0)
        tile_size:    int   = int(self.din_tile_size.value     or 64)
        tile_overlap: int   = int(self.din_tile_overlap.value  or 8)

        try:
            backend = env.backend if env is not None else executionContext.env.backend
            self._cancel_event.clear()
            steps_done = [0]

            if executionContext is not None:
                await executionContext.report_status(
                    f"Tiled sampling {steps} steps "
                    f"(tile={tile_size}px, overlap={tile_overlap}px)\u2026"
                )

            loop = asyncio.get_running_loop()

            def _on_step(step_num: int, total: int) -> None:
                if executionContext is not None:
                    asyncio.run_coroutine_threadsafe(
                        executionContext.report_progress(
                            step_num / total,
                            f"Step {step_num} / {total}",
                        ),
                        loop,
                    )

            latent = await asyncio.to_thread(
                backend.sample_tiled,
                model, positive, negative, latent_image,
                seed, steps, cfg, sampler, sched, denoise,
                tile_size, tile_overlap,
                cancel_event=self._cancel_event,
                steps_done=steps_done,
                step_callback=_on_step,
            )
            cancelled = latent.pop("cancelled", False)
            self.dout_latent.value = latent
            self.dout_error.value  = ''
            if cancelled:
                from nodegraph.python.server.trace.trace_emitter import global_tracer
                global_tracer.fire({
                    "type": "SAMPLING_CANCELLED",
                    "nodeId": self.id,
                    "stepsCompleted": steps_done[0],
                })
            return ExecutionResult(
                ExecCommand.CONTINUE,
                control_outputs={'next': True, 'failed': False},
            )
        except Exception as exc:
            self.dout_latent.value = {}
            self.dout_error.value  = str(exc)
            return ExecutionResult(
                ExecCommand.CONTINUE,
                control_outputs={'next': False, 'failed': True},
            )
