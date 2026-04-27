"""
KSamplerStepNode — step-by-step diffusion sampler that yields one
partially-denoised latent per graph iteration.

This node mirrors the LOOP_AGAIN / COMPLETED pattern used by ForLoopNode and
ForEachNode: instead of running every denoising step in a single blocking call
it executes ONE timestep per compute() invocation and re-schedules itself via
LOOP_AGAIN until all steps are exhausted.

Wiring this node's ``loop_body`` output to a VAEDecode → SaveImage chain lets
you preview (or process) the latent at every diffusion step.

Ports
-----
Control in  : exec
Data in     : MODEL, positive (CONDITIONING), negative (CONDITIONING),
              latent_image (LATENT), seed (INT), steps (INT),
              cfg (FLOAT), sampler_name (STRING), scheduler (STRING),
              denoise (FLOAT)
Control out : loop_body  — fires after each step        (LOOP_AGAIN)
              done       — fires when all steps finish   (COMPLETED)
Data out    : LATENT      — latent at the current step
              step        — current step number (1-based)
              total_steps — total number of scheduled timesteps
              error       — error string (empty on success)
"""

from __future__ import annotations

import asyncio
from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("KSamplerStep")
class KSamplerStepNode(Node):
    """
    Step-by-step KSampler.

    On the **first** call it initialises the scheduler and noise via
    ``backend.sample_init()``, then immediately runs the first timestep via
    ``backend.sample_step()``.  Each subsequent LOOP_AGAIN re-invocation
    advances the sampler by exactly one timestep.  When the final step
    completes the node returns COMPLETED and fires ``done``.

    The per-run state (latents tensor, scheduler object, timestep list, …) is
    stored in ``self._sampler_state`` between iterations since the node
    instance persists across LOOP_AGAIN calls within a single graph execution.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        # Per-run state held between LOOP_AGAIN iterations.
        # None means "not yet initialised for this run".
        self._sampler_state: dict | None = None

        # ── control ──────────────────────────────────────────────────────────
        self.cin_exec         = self.add_control_input('exec')
        self.cout_loop_body   = self.add_control_output('loop_body')
        self.cout_done        = self.add_control_output('done')

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

        # ── data outputs ─────────────────────────────────────────────────────
        self.dout_latent      = self.add_data_output('LATENT',       data_type=ValueType.LATENT)
        self.dout_step        = self.add_data_output('step',         data_type=ValueType.INT)
        self.dout_total_steps = self.add_data_output('total_steps',  data_type=ValueType.INT)
        self.dout_error       = self.add_data_output('error',        data_type=ValueType.STRING)

    # -------------------------------------------------------------------------

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        backend = env.backend if env is not None else executionContext.env.backend

        # ── First call: initialise sampler state ──────────────────────────────
        if self._sampler_state is None:
            model         = self.din_model.value
            positive      = self.din_positive.value     or []
            negative      = self.din_negative.value     or []
            latent_image  = self.din_latent_image.value or {}
            seed:    int  = int(self.din_seed.value          or 0)
            steps:   int  = int(self.din_steps.value         or 20)
            cfg:   float  = float(self.din_cfg.value          or 7.0)
            sampler: str  = self.din_sampler_name.value       or 'euler'
            sched:   str  = self.din_scheduler.value          or 'karras'
            denoise: float = float(self.din_denoise.value    or 1.0)

            try:
                self._sampler_state = await asyncio.to_thread(
                    backend.sample_init,
                    model, positive, negative, latent_image,
                    seed, steps, cfg, sampler, sched, denoise,
                )
            except Exception as exc:
                self._sampler_state = None
                self.dout_error.value = str(exc)
                result = ExecutionResult(ExecCommand.COMPLETED)
                result.control_outputs['loop_body'] = False
                result.control_outputs['done']      = True
                return result

        # ── Every call: advance one denoising step ────────────────────────────
        total       = len(self._sampler_state["timesteps"])
        # step_idx hasn't been incremented yet — this gives the 1-based human label.
        step_label  = self._sampler_state["step_idx"] + 1

        if executionContext is not None:
            await executionContext.report_status(
                f"Diffusion step {step_label} / {total}…"
            )

        try:
            latent_dict, is_done = await asyncio.to_thread(
                backend.sample_step, self._sampler_state
            )
        except Exception as exc:
            self._sampler_state = None
            self.dout_error.value = str(exc)
            result = ExecutionResult(ExecCommand.COMPLETED)
            result.control_outputs['loop_body'] = False
            result.control_outputs['done']      = True
            return result

        if executionContext is not None:
            await executionContext.report_progress(
                step_label / total,
                f"Step {step_label} / {total}",
            )

        # ── Publish outputs ───────────────────────────────────────────────────
        self.dout_latent.value      = latent_dict
        self.dout_step.value        = step_label
        self.dout_total_steps.value = total
        self.dout_error.value       = ''

        if is_done:
            # All timesteps exhausted — clean up and signal completion.
            self._sampler_state = None
            result = ExecutionResult(ExecCommand.COMPLETED)
            result.data_outputs['LATENT']      = latent_dict
            result.data_outputs['step']        = step_label
            result.data_outputs['total_steps'] = total
            result.control_outputs['loop_body'] = False
            result.control_outputs['done']      = True
        else:
            # More steps remain — fire loop_body and re-schedule this node.
            result = ExecutionResult(ExecCommand.LOOP_AGAIN)
            result.data_outputs['LATENT']      = latent_dict
            result.data_outputs['step']        = step_label
            result.data_outputs['total_steps'] = total
            result.control_outputs['loop_body'] = True
            result.control_outputs['done']      = False

        return result
