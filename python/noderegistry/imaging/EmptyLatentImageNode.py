"""
EmptyLatentImageNode — produce a zeroed latent tensor of a given resolution.

Ports
-----
Inputs  (data)  : width : INT, height : INT, batch_size : INT
Outputs (data)  : LATENT : LATENT
Control outputs : next, failed
"""

from __future__ import annotations

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("EmptyLatentImage")
class EmptyLatentImageNode(Node):
    """
    Creates an empty (zeroed) latent image tensor that can be fed directly
    into a KSampler node for text-to-image generation.

    Default resolution: 512 × 512, batch size 1.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.cin_exec       = self.add_control_input('exec')
        self.cout_next      = self.add_control_output('next')
        self.cout_failed    = self.add_control_output('failed')

        self.din_width      = self.add_data_input('width',      data_type=ValueType.INT)
        self.din_height     = self.add_data_input('height',     data_type=ValueType.INT)
        self.din_batch_size = self.add_data_input('batch_size', data_type=ValueType.INT)

        self.dout_latent    = self.add_data_output('LATENT', data_type=ValueType.LATENT)
        self.dout_error     = self.add_data_output('error',  data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        width:      int = int(self.din_width.value      or 512)
        height:     int = int(self.din_height.value     or 512)
        batch_size: int = int(self.din_batch_size.value or 1)
        try:
            backend = env.backend if env is not None else executionContext.env.backend
            latent  = backend.empty_latent(width, height, batch_size)
            self.dout_latent.value = latent
            self.dout_error.value  = ''
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_latent.value = {}
            self.dout_error.value  = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
