"""
Utility for converting image-like objects to inline base64 data-URLs.
Used by VAEDecodeNode to send preview frames over the trace socket.
"""

from __future__ import annotations

import base64
import io


def to_data_url(image) -> str:
    """Convert a PIL image, tensor, ndarray, or nested list to a PNG data URL."""
    buf = io.BytesIO()
    pil_image = _to_pil_image(image)
    pil_image.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _to_pil_image(image):
    if hasattr(image, "save"):
        return image

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Image previews require Pillow") from exc

    arr = image
    if hasattr(arr, "detach"):
        arr = arr.detach()
    if hasattr(arr, "cpu"):
        arr = arr.cpu()
    if hasattr(arr, "numpy"):
        arr = arr.numpy()
    else:
        try:
            import numpy as np
            arr = np.asarray(arr)
        except ImportError as exc:
            raise RuntimeError("Image previews require numpy for non-PIL images") from exc

    if getattr(arr, "ndim", None) == 4:
        arr = arr[0]
    if getattr(arr, "ndim", None) == 3 and arr.shape[0] in (1, 3, 4) and arr.shape[-1] not in (1, 3, 4):
        arr = arr.transpose(1, 2, 0)
    if getattr(arr, "ndim", None) == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]

    arr = (arr * 255).clip(0, 255).astype("uint8")
    return Image.fromarray(arr)
