"""
CLIPTextEncodeNode — encode a text prompt into a CONDITIONING tensor.

Ports
-----
Inputs  (data)  : CLIP : CLIP, text : STRING
Outputs (data)  : CONDITIONING : CONDITIONING
Control outputs : next, failed
"""

from __future__ import annotations

import asyncio
from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("CLIPTextEncode")
class CLIPTextEncodeNode(Node):
    """
    Runs CLIP text encoding on a single prompt string and emits the
    resulting conditioning tensors.  Create two instances (positive and
    negative) for a typical diffusion run.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        self.din_clip    = self.add_data_input('CLIP', data_type=ValueType.CLIP)
        self.din_text    = self.add_data_input('text', data_type=ValueType.STRING)

        self.dout_cond   = self.add_data_output('CONDITIONING', data_type=ValueType.CONDITIONING)
        self.dout_error  = self.add_data_output('error',        data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        clip_handle = self.din_clip.value
        text: str   = self.din_text.value or ''
        try:
            backend = env.backend if env is not None else executionContext.env.backend
            conditioning = await asyncio.to_thread(backend.encode_text, clip_handle, text)
            self.dout_cond.value  = conditioning
            self.dout_error.value = ''
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_cond.value  = []
            self.dout_error.value = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
