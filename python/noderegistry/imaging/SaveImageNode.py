"""
SaveImageNode — write an IMAGE tensor to disk as a PNG file.

Ports
-----
Inputs  (data)  : images : IMAGE, filename_prefix : STRING, output_dir : STRING
Outputs (data)  : saved_path : STRING
Control outputs : done, failed
"""

from __future__ import annotations

import asyncio
import os

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("SaveImage")
class SaveImageNode(Node):
    """
    Saves an IMAGE tensor to the filesystem.

    *filename_prefix* is used as the base filename; a counter suffix and
    ``.png`` extension are appended automatically when the file already
    exists so existing images are never silently overwritten.

    *output_dir* defaults to ``./output`` relative to the working directory
    if not supplied.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.cin_exec        = self.add_control_input('exec')
        self.cout_done       = self.add_control_output('done')
        self.cout_failed     = self.add_control_output('failed')

        self.din_images          = self.add_data_input('images',          data_type=ValueType.IMAGE)
        self.din_filename_prefix = self.add_data_input('filename_prefix', data_type=ValueType.STRING)
        self.din_output_dir      = self.add_data_input('output_dir',      data_type=ValueType.STRING)

        self.dout_saved_path = self.add_data_output('saved_path', data_type=ValueType.STRING)
        self.dout_error      = self.add_data_output('error',      data_type=ValueType.STRING)

    @staticmethod
    def _unique_path(directory: str, prefix: str) -> str:
        """Return a non-colliding file path inside *directory*."""
        os.makedirs(directory, exist_ok=True)
        candidate = os.path.join(directory, f"{prefix}.png")
        counter   = 1
        while os.path.exists(candidate):
            candidate = os.path.join(directory, f"{prefix}_{counter:05d}.png")
            counter  += 1
        return candidate

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        image      = self.din_images.value
        prefix: str = self.din_filename_prefix.value or 'image'
        out_dir: str = self.din_output_dir.value or './output'

        try:
            backend  = env.backend if env is not None else executionContext.env.backend
            out_path = self._unique_path(out_dir, prefix)
            saved    = await asyncio.to_thread(backend.save_image, image, out_path)
            self.dout_saved_path.value = saved
            self.dout_error.value      = ''
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'done': True, 'failed': False})
        except Exception as exc:
            self.dout_saved_path.value = ''
            self.dout_error.value      = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'done': False, 'failed': True})
