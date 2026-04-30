"""
LoadImageNode — load an image file from disk into an IMAGE tensor.

Ports
-----
Inputs  (data)  : image_path : STRING
Outputs (data)  : IMAGE : IMAGE, MASK : MASK, error : STRING
Control outputs : next, failed

Preview
-------
On success an inline PNG data-URL is sent via ``executionContext.report_detail``
so that connected UI clients can display the loaded image immediately.
"""

from __future__ import annotations

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType
from ...server.trace.image_preview import to_data_url


@Node.register("LoadImage")
class LoadImageNode(Node):
    """
    Loads an image from the filesystem and emits it on the IMAGE port.

    If the source image has an alpha channel the inverse alpha is emitted
    on the MASK port; otherwise MASK is ``None``.

    After a successful load a small PNG preview is pushed through
    ``executionContext.report_detail`` as a ``{"url": "<data-url>"}`` dict
    so that the front-end can render it in the node tile without an extra
    round-trip.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        # ── Control flow ────────────────────────────────────────────────────
        self.cin_exec        = self.add_control_input('exec')
        self.cout_next       = self.add_control_output('next')
        self.cout_failed     = self.add_control_output('failed')

        # ── Data inputs ─────────────────────────────────────────────────────
        # Absolute or relative filesystem path to the image file.
        # Supported formats depend on the active backend (typically anything
        # PIL / Pillow can open: PNG, JPEG, WEBP, TIFF, BMP, …).
        self.din_image_path  = self.add_data_input('image_path', data_type=ValueType.STRING)

        # ── Data outputs ─────────────────────────────────────────────────────
        # Loaded pixel data as a float32 HxWxC tensor in the [0, 1] range.
        self.dout_image      = self.add_data_output('IMAGE', data_type=ValueType.IMAGE)
        # Per-pixel alpha mask in [0, 1].  None when the image has no alpha.
        # Convention: 1.0 = fully opaque region, 0.0 = fully transparent.
        self.dout_mask       = self.add_data_output('MASK',  data_type=ValueType.MASK)
        # Human-readable error message; empty string on success.
        self.dout_error      = self.add_data_output('error', data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        """
        Load the image at ``image_path`` via the active backend.

        Execution flow
        --------------
        1. Read *image_path* from the data input.
        2. Delegate loading to ``backend.load_image(path)`` which returns
           ``(image_tensor, mask_tensor_or_None)``.
        3. On success: write outputs, emit a preview, route to *next*.
        4. On failure: write the error string, route to *failed*.

        The *env* / *executionContext* split follows Option-B architecture:
        ``env`` carries process-local resources (backend, tensor store) that
        are **not** serialisable and therefore cannot live inside NodeContext.
        """
        path: str = self.din_image_path.value or ''

        # Clear any stale preview before the new load attempt.
        if executionContext is not None and hasattr(executionContext, "report_detail"):
            await executionContext.report_detail({"url": None})

        try:
            backend = env.backend if env is not None else executionContext.env.backend
            image, mask = backend.load_image(path)

            self.dout_image.value = image
            self.dout_mask.value  = mask
            self.dout_error.value = ''

            # Emit an inline PNG preview so the UI can show a thumbnail
            # immediately after execution without any extra network request.
            if executionContext is not None and hasattr(executionContext, "report_detail"):
                await executionContext.report_detail({"url": to_data_url(image)})

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})

        except Exception as exc:
            self.dout_image.value = None
            self.dout_mask.value  = None
            self.dout_error.value = str(exc)

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
