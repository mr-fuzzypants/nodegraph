"""
LoadImageNode — load an image file from disk into an IMAGE tensor.

Ports
-----
Inputs  (data)  : image_path : STRING
Outputs (data)  : IMAGE : IMAGE, MASK : MASK
Control outputs : next, failed
"""

from __future__ import annotations

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("LoadImage")
class LoadImageNode(Node):
    """
    Loads an image from the filesystem and emits it on the IMAGE port.
    If the source image has an alpha channel the inverse alpha is emitted
    on the MASK port; otherwise MASK is None.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.cin_exec        = self.add_control_input('exec')
        self.cout_next       = self.add_control_output('next')
        self.cout_failed     = self.add_control_output('failed')

        self.din_image_path  = self.add_data_input('image_path', data_type=ValueType.STRING)

        self.dout_image      = self.add_data_output('IMAGE', data_type=ValueType.IMAGE)
        self.dout_mask       = self.add_data_output('MASK',  data_type=ValueType.MASK)
        self.dout_error      = self.add_data_output('error', data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        path: str = self.din_image_path.value or ''
        try:
            backend = env.backend if env is not None else executionContext.env.backend
            image, mask = backend.load_image(path)
            self.dout_image.value = image
            self.dout_mask.value  = mask
            self.dout_error.value = ''
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_image.value = None
            self.dout_mask.value  = None
            self.dout_error.value = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
