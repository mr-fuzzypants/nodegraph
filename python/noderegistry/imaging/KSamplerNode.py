"""
KSamplerNode — run the core denoising / sampling loop.

This is the most central node in a diffusion pipeline; it consumes a model,
positive and negative conditioning, and an initial latent, then produces the
denoised latent.

Ports
-----
Inputs  (data)  : MODEL, positive (CONDITIONING), negative (CONDITIONING),
                  latent_image (LATENT), seed (INT), steps (INT),
                  cfg (FLOAT), sampler_name (STRING), scheduler (STRING),
                  denoise (FLOAT)
Outputs (data)  : LATENT, error (STRING)
Control outputs : next, failed
"""

from __future__ import annotations

import asyncio
import threading
from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType

# Enumerated choices — informational only, not enforced at the port layer
SAMPLER_NAMES = [
    "euler", "euler_ancestral", "heun", "dpm_2", "dpm_2_ancestral",
    "lms", "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral",
    "dpmpp_sde", "dpmpp_2m", "dpmpp_2m_sde", "ddim", "uni_pc",
]
SCHEDULER_NAMES = ["normal", "karras", "exponential", "simple", "ddim_uniform"]


@Node.register("KSampler")
class KSamplerNode(Node):
    """
    Wraps the backend's ``sample()`` call with the standard KSampler
    port layout familiar to ComfyUI users.

    ``is_durable_step`` is set so the executor can wrap the potentially
    long-running sampling call in an exactly-once DBOS step.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step      = True

        # Cancel flag: set via the cancel endpoint to stop sampling early.
        # A plain threading.Event is used so it can be checked synchronously
        # inside the (non-async) sample() loop without needing the event loop.
        self._cancel_event: threading.Event = threading.Event()

        self.cin_exec            = self.add_control_input('exec')
        self.cout_next           = self.add_control_output('next')
        self.cout_failed         = self.add_control_output('failed')

        self.din_model           = self.add_data_input('MODEL',        data_type=ValueType.MODEL)
        self.din_positive        = self.add_data_input('positive',     data_type=ValueType.CONDITIONING)
        self.din_negative        = self.add_data_input('negative',     data_type=ValueType.CONDITIONING)
        self.din_latent_image    = self.add_data_input('latent_image', data_type=ValueType.LATENT)
        self.din_seed            = self.add_data_input('seed',         data_type=ValueType.INT)
        self.din_steps           = self.add_data_input('steps',        data_type=ValueType.INT)
        self.din_cfg             = self.add_data_input('cfg',          data_type=ValueType.FLOAT)
        self.din_sampler_name    = self.add_data_input('sampler_name', data_type=ValueType.STRING)
        self.din_scheduler       = self.add_data_input('scheduler',    data_type=ValueType.STRING)
        self.din_denoise         = self.add_data_input('denoise',      data_type=ValueType.FLOAT)

        self.dout_latent         = self.add_data_output('LATENT', data_type=ValueType.LATENT)
        self.dout_error          = self.add_data_output('error',  data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        model        = self.din_model.value
        positive     = self.din_positive.value     or []
        negative     = self.din_negative.value     or []
        latent_image = self.din_latent_image.value or {}
        seed:   int   = int(self.din_seed.value          or 0)
        steps:  int   = int(self.din_steps.value         or 20)
        cfg:    float = float(self.din_cfg.value          or 7.0)
        sampler: str  = self.din_sampler_name.value       or 'euler'
        sched:   str  = self.din_scheduler.value          or 'karras'
        denoise: float = float(self.din_denoise.value     or 1.0)

        try:
            backend = env.backend if env is not None else executionContext.env.backend
            # Reset any previous cancellation before starting a new run.
            self._cancel_event.clear()
            steps_done = [0]  # mutable counter updated by backend each step

            if executionContext is not None:
                await executionContext.report_status(f"Sampling {steps} steps\u2026")

            # Bridge: sample() runs in a threadpool thread; schedule async
            # report_progress() back onto the event loop with run_coroutine_threadsafe.
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
                backend.sample,
                model, positive, negative, latent_image,
                seed, steps, cfg, sampler, sched, denoise,
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
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_latent.value = {}
            self.dout_error.value  = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
