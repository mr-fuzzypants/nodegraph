"""
CheckpointLoaderNode — load a full diffusion checkpoint.

Ports
-----
Inputs  (data)   : ckpt_path : STRING
Outputs (data)   : MODEL, CLIP, VAE
Control outputs  : next, failed
"""

from __future__ import annotations

import asyncio
from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType

DEFAULT_CHECKPOINT_PATH = "/Users/robertpringle/development/ai_models"


@Node.register("CheckpointLoader")
class CheckpointLoaderNode(Node):
    """
    Loads a diffusion checkpoint and exposes its three components
    (UNet model, CLIP text encoder, VAE) as separate output ports so
    downstream nodes can be connected independently.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True

        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        self.din_path    = self.add_data_input('ckpt_path', data_type=ValueType.STRING)
        self.din_path.value = DEFAULT_CHECKPOINT_PATH

        self.dout_model  = self.add_data_output('MODEL', data_type=ValueType.MODEL)
        self.dout_clip   = self.add_data_output('CLIP',  data_type=ValueType.CLIP)
        self.dout_vae    = self.add_data_output('VAE',   data_type=ValueType.VAE)
        self.dout_error  = self.add_data_output('error', data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        path: str = self.din_path.value or DEFAULT_CHECKPOINT_PATH
        try:
            runtime_env = env if env is not None else getattr(executionContext, "env", None)
            backend = getattr(runtime_env, "backend", None)
            if backend is None:
                raise RuntimeError(
                    "CheckpointLoader requires a diffusion backend. "
                    "Run through WorkflowManager or pass NodeEnvironment(backend=...) to compute()."
                )
            model, clip, vae = await asyncio.to_thread(backend.load_checkpoint, path)
            self.dout_model.value = model
            self.dout_clip.value  = clip
            self.dout_vae.value   = vae
            self.dout_error.value = ''
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_model.value = None
            self.dout_clip.value  = None
            self.dout_vae.value   = None
            self.dout_error.value = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
