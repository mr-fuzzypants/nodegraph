"""
Imaging nodes — ComfyUI-concept equivalents for the NodeGraph engine.

These nodes implement the canonical Stable Diffusion pipeline steps
(load → encode → sample → decode → save) as independent graph nodes
that can be wired together in any topology.

All backend-specific work is delegated to ``executionContext.backend``,
which must satisfy the ``DiffusionBackend`` protocol defined in
``python/core/backends/protocol.py``.

Nodes registered here:
    CheckpointLoader
    CLIPTextEncode
    EmptyLatentImage
    KSampler
    VAEDecode
    VAEEncode
    LoadImage
    SaveImage
    ReferenceLatent
    ResizeImage

Minimum viable txt2img wiring
──────────────────────────────
CheckpointLoader ──MODEL──► KSampler
                 ──CLIP──►  CLIPTextEncode (×2, positive + negative)
                 ──VAE──►   VAEDecode
CLIPTextEncode   ──CONDITIONING──► KSampler.positive / .negative
EmptyLatentImage ──LATENT──►       KSampler.latent_image
KSampler         ──LATENT──►       VAEDecode
VAEDecode        ──IMAGE──►        SaveImage
"""

from .CheckpointLoaderNode  import CheckpointLoaderNode
from .CLIPTextEncodeNode     import CLIPTextEncodeNode
from .EmptyLatentImageNode   import EmptyLatentImageNode
from .KSamplerNode           import KSamplerNode
from .KSamplerStepNode       import KSamplerStepNode
from .TiledKSamplerNode      import TiledKSamplerNode
from .VAEDecodeNode          import VAEDecodeNode
from .VAEEncodeNode          import VAEEncodeNode
from .LoadImageNode          import LoadImageNode
from .SaveImageNode          import SaveImageNode
from .ReferenceLatentNode    import ReferenceLatentNode
from .ResizeImageNode        import ResizeImageNode

__all__ = [
    "CheckpointLoaderNode",
    "CLIPTextEncodeNode",
    "EmptyLatentImageNode",
    "KSamplerNode",
    "KSamplerStepNode",
    "TiledKSamplerNode",
    "VAEDecodeNode",
    "VAEEncodeNode",
    "LoadImageNode",
    "SaveImageNode",
    "ReferenceLatentNode",
    "ResizeImageNode",
]
