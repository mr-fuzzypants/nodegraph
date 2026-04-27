"""
Diffusion / imaging backend abstraction layer.

Import the protocol to type-annotate against the interface:
    from ..core.backends import DiffusionBackend

Use a concrete backend when building an ExecutionContext that runs
imaging nodes:

    # HuggingFace diffusers (pipeline-level, simplest):
    from ..core.backends.diffusers_backend import DiffusersBackend
    ctx.backend = DiffusersBackend(device="cuda")

    # Component-level PyTorch — single .safetensors or diffusers directory:
    from ..core.backends.safetensors_backend import SafetensorsBackend
    ctx.backend = SafetensorsBackend(device="mps", dtype="float16")
"""

from .protocol import DiffusionBackend

__all__ = ["DiffusionBackend"]
