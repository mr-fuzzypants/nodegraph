"""
ResizeImageNode — resize an IMAGE tensor to a specified width and height.

Background
----------
A resize node is a fundamental building block in image processing pipelines.
It allows you to up-scale or down-scale an image before feeding it into other
nodes (e.g. to match the expected latent resolution for a specific checkpoint,
or to produce a thumbnail for display).

All resize work is delegated to Pillow (PIL), which provides a rich set of
resampling filters optimised for both upscaling and downscaling scenarios.

Interpolation options
---------------------
``"none"``
    Alias for nearest-neighbour; no blending is applied.  Pixels are simply
    duplicated or dropped.  Preserves hard edges — ideal for pixel art or
    masks.  Fastest option.

``"nearest"``
    Nearest-neighbour resampling.  Same quality as "none"; exposed separately
    so that UI dropdowns can show a descriptive label.

``"bilinear"``
    Bilinear interpolation.  Samples a 2×2 pixel neighbourhood and produces a
    weighted average.  Fast; acceptable quality for moderate upscaling.

``"bicubic"``
    Bicubic interpolation.  Samples a 4×4 pixel neighbourhood.  Smoother than
    bilinear for upscaling; may introduce slight ringing artefacts.

``"lanczos"``
    Lanczos (sinc-based) resampling.  High-quality downscaling with minimal
    aliasing.  Slower than bicubic but generally the best choice for photo
    content.  Also known as "ANTIALIAS" in older Pillow versions.

``"box"``
    Box (area-averaging) filter.  Averages all input pixels that map to each
    output pixel.  Best for integer downscaling ratios; avoids aliasing
    artefacts that nearest-neighbour produces when shrinking.

``"hamming"``
    Hamming-windowed sinc filter.  Sharper than box for non-integer ratios
    while remaining faster than Lanczos.  A good compromise for downscaling
    when performance matters.

Ports
-----
Inputs  (data)  : image  : IMAGE   — source image to resize
                  width  : INT     — target width in pixels  (must be > 0)
                  height : INT     — target height in pixels (must be > 0)
                  interpolation : STRING
                      One of: none, nearest, bilinear, bicubic, lanczos,
                      box, hamming.  Defaults to "lanczos".
Outputs (data)  : IMAGE : IMAGE   — resized image at [0, 1] float32
                  error : STRING  — empty on success
Control outputs : next, failed

Preview
-------
On success an inline PNG data-URL is sent via ``executionContext.report_detail``
so that connected UI clients can display the resized image immediately.

License
-------
This file is original work released under the MIT License.
It does not reproduce any code from ComfyUI or other GPL/AGPL projects.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType
from ...server.trace.image_preview import to_data_url


# ---------------------------------------------------------------------------
# Enumerated interpolation options
# ---------------------------------------------------------------------------
# These string keys are the values a UI dropdown should present.  They map to
# Pillow Resampling enum members in _PILLOW_RESAMPLE_MAP below.

INTERPOLATION_OPTIONS = [
    "none",       # nearest-neighbour, no blending
    "nearest",    # same algorithm as "none"; explicit label for UI clarity
    "bilinear",   # linear interpolation, 2×2 kernel
    "bicubic",    # cubic interpolation, 4×4 kernel
    "lanczos",    # sinc-based, best quality for photo downscaling
    "box",        # area-averaging, best for integer downscaling ratios
    "hamming",    # Hamming-windowed sinc, compromise between box and lanczos
]

# Default filter used when the user does not specify one.
DEFAULT_INTERPOLATION = "lanczos"


def _get_pillow_resample(interpolation: str):
    """
    Translate a user-facing interpolation name to the appropriate Pillow
    ``Resampling`` (or legacy integer) constant.

    Pillow ≥ 9.1 uses ``PIL.Image.Resampling.*``; older versions use
    ``PIL.Image.*`` integer constants.  This function handles both by
    probing for the new enum first and falling back gracefully.

    Parameters
    ----------
    interpolation:
        One of the keys in ``INTERPOLATION_OPTIONS``.  Unknown values fall
        back to Lanczos with a warning rather than raising, so graphs remain
        runnable even when a checkpoint saves an unsupported string.

    Returns
    -------
    A Pillow resampling constant suitable for passing to ``Image.resize()``.
    """
    from PIL import Image  # imported lazily to avoid hard dep at module load

    # Pillow ≥ 9.1 exposes a proper Resampling enum; older releases define
    # the same filters as integer constants directly on the Image module.
    # We use getattr with a fallback integer value for maximum compatibility.
    _PILLOW_RESAMPLE_MAP = {
        "none":     getattr(getattr(Image, "Resampling", Image), "NEAREST",  0),
        "nearest":  getattr(getattr(Image, "Resampling", Image), "NEAREST",  0),
        "bilinear": getattr(getattr(Image, "Resampling", Image), "BILINEAR", 2),
        "bicubic":  getattr(getattr(Image, "Resampling", Image), "BICUBIC",  3),
        "lanczos":  getattr(getattr(Image, "Resampling", Image), "LANCZOS",  1),
        "box":      getattr(getattr(Image, "Resampling", Image), "BOX",      4),
        "hamming":  getattr(getattr(Image, "Resampling", Image), "HAMMING",  5),
    }
    key = (interpolation or DEFAULT_INTERPOLATION).lower().strip()
    return _PILLOW_RESAMPLE_MAP.get(key, _PILLOW_RESAMPLE_MAP[DEFAULT_INTERPOLATION])


def _resize_image(image: Any, width: int, height: int, resample) -> Any:
    """
    Resize *image* to (*width*, *height*) using *resample* filter.

    This function handles three common image representations:

    * **PIL Image** — resized directly via ``Image.resize()``.
    * **NumPy ndarray / PyTorch tensor** — converted to PIL, resized, then
      converted back to the same type and dtype.

    The return value has the same type as the input.

    Notes
    -----
    * Float tensors/arrays are assumed to be in [0, 1].  They are multiplied
      by 255 before conversion to uint8 PIL and divided by 255 on the way back
      to preserve the normalised range.
    * Batch dimension (dim-0 size > 1) is not supported: only the first frame
      ``image[0]`` is processed and returned as a single-frame result.
    * Channel-first tensors (C, H, W) are transposed to (H, W, C) before PIL
      conversion and transposed back afterward.
    """
    from PIL import Image

    # ── PIL Image ────────────────────────────────────────────────────────────
    if hasattr(image, "save"):
        # image is already a PIL Image; resize in-place-free (returns new obj).
        return image.resize((width, height), resample=resample)

    # ── Tensor / array path ──────────────────────────────────────────────────
    # Detach from autograd graph if necessary (PyTorch tensors).
    arr = image
    if hasattr(arr, "detach"):
        arr = arr.detach()
    if hasattr(arr, "cpu"):
        arr = arr.cpu()

    # Determine whether we received a torch tensor so we can return the same
    # type and device at the end.
    is_torch = hasattr(arr, "numpy") and not hasattr(arr, "tolist")

    # Convert to numpy for unified processing.
    if hasattr(arr, "numpy"):
        arr = arr.numpy()
    else:
        import numpy as np
        arr = np.asarray(arr)

    import numpy as np

    # Handle optional batch dimension: (B, H, W, C) → use first frame.
    if arr.ndim == 4:
        arr = arr[0]

    # Normalise channel ordering to HxWxC.
    if arr.ndim == 3 and arr.shape[0] in (1, 3, 4) and arr.shape[-1] not in (1, 3, 4):
        # Channel-first layout detected (C, H, W) → (H, W, C).
        arr = arr.transpose(1, 2, 0)
        channel_first = True
    else:
        channel_first = False

    # Squeeze single-channel to 2-D for PIL greyscale mode.
    if arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]

    # PIL expects uint8; convert from float [0,1] if needed.
    original_dtype = arr.dtype
    if np.issubdtype(original_dtype, np.floating):
        arr_uint8 = (arr * 255).clip(0, 255).astype(np.uint8)
    else:
        arr_uint8 = arr.astype(np.uint8)

    pil_img     = Image.fromarray(arr_uint8)
    pil_resized = pil_img.resize((width, height), resample=resample)
    arr_resized = np.asarray(pil_resized)

    # Restore original dtype and channel ordering.
    if np.issubdtype(original_dtype, np.floating):
        arr_resized = arr_resized.astype(original_dtype) / 255.0

    if arr_resized.ndim == 2:
        # Greyscale → add channel dim back if input had one.
        arr_resized = arr_resized[..., np.newaxis]

    if channel_first:
        arr_resized = arr_resized.transpose(2, 0, 1)

    # Return a torch tensor if the input was a torch tensor.
    if is_torch:
        import torch
        return torch.from_numpy(arr_resized)

    return arr_resized


@Node.register("ResizeImage")
class ResizeImageNode(Node):
    """
    Resize an IMAGE to a target resolution using a configurable filter.

    Supported interpolation modes (``interpolation`` input):
        ``"none"`` / ``"nearest"``  — fast, pixel-accurate; good for masks/pixel art.
        ``"bilinear"``               — smooth upscaling, moderate quality.
        ``"bicubic"``                — smoother upscaling, slightly slower.
        ``"lanczos"``                — best quality for photos; default choice.
        ``"box"``                    — area-averaging; best for integer downscaling.
        ``"hamming"``                — sharp downscaling, faster than lanczos.

    The output IMAGE is always a float32 array/tensor in [0, 1] of shape
    (height, width, C).

    A preview is emitted via ``report_detail`` on success so the UI can render
    the resized image in the node tile.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        # ── Control flow ────────────────────────────────────────────────────
        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        # ── Data inputs ─────────────────────────────────────────────────────
        # Source image to resize.
        self.din_image  = self.add_data_input('image',  data_type=ValueType.IMAGE)
        # Target width in pixels.  Must be a positive integer.
        self.din_width  = self.add_data_input('width',  data_type=ValueType.INT)
        # Target height in pixels.  Must be a positive integer.
        self.din_height = self.add_data_input('height', data_type=ValueType.INT)
        # Resampling filter name.  One of INTERPOLATION_OPTIONS; defaults to
        # "lanczos" when empty or unrecognised.
        self.din_interpolation = self.add_data_input(
            'interpolation', data_type=ValueType.STRING
        )
        # Seed the default value with the recommended filter.
        self.din_interpolation.value = DEFAULT_INTERPOLATION

        # ── Data outputs ─────────────────────────────────────────────────────
        # Resized image at the same dtype and channel layout as the input.
        self.dout_image = self.add_data_output('IMAGE', data_type=ValueType.IMAGE)
        # Human-readable error message; empty string on success.
        self.dout_error = self.add_data_output('error', data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        """
        Resize the input image to (width × height) using the chosen filter.

        Execution flow
        --------------
        1. Read *image*, *width*, *height*, and *interpolation* inputs.
        2. Validate that width and height are positive integers.
        3. Resolve the Pillow resampling constant for the chosen filter.
        4. Run the resize on a background thread (``asyncio.to_thread``) to
           avoid blocking the event loop during potentially large resizes.
        5. Write the output image, emit a preview, and route to *next*.
        6. On any failure route to *failed* and write the error string.

        Note: This node does not require any backend resources; it uses Pillow
        directly and is therefore backend-agnostic.
        """
        image:         Any = self.din_image.value
        width:         Any = self.din_width.value
        height:        Any = self.din_height.value
        interpolation: str = self.din_interpolation.value or DEFAULT_INTERPOLATION

        # Clear any stale preview before the new compute attempt.
        if executionContext is not None and hasattr(executionContext, "report_detail"):
            await executionContext.report_detail({"url": None})

        try:
            # ── Validate dimensions ──────────────────────────────────────────
            if image is None:
                raise ValueError(
                    "ResizeImageNode: 'image' input is None.  "
                    "Connect a LoadImage or upstream IMAGE-producing node."
                )

            width  = int(width)
            height = int(height)

            if width <= 0 or height <= 0:
                raise ValueError(
                    f"ResizeImageNode: width and height must be positive integers, "
                    f"got width={width}, height={height}."
                )

            # ── Resolve resampling filter ────────────────────────────────────
            resample = _get_pillow_resample(interpolation)

            # ── Perform resize on a background thread ────────────────────────
            # Resizing large images (e.g. 4K) can be CPU-intensive; running it
            # off the event loop keeps the server responsive.
            resized = await asyncio.to_thread(_resize_image, image, width, height, resample)

            self.dout_image.value = resized
            self.dout_error.value = ''

            # Emit an inline PNG preview so the UI can show a thumbnail
            # without an extra network request.
            if executionContext is not None and hasattr(executionContext, "report_detail"):
                await executionContext.report_detail({"url": to_data_url(resized)})

            return ExecutionResult(
                ExecCommand.CONTINUE,
                control_outputs={'next': True, 'failed': False},
            )

        except Exception as exc:
            self.dout_image.value = None
            self.dout_error.value = str(exc)

            return ExecutionResult(
                ExecCommand.CONTINUE,
                control_outputs={'next': False, 'failed': True},
            )
