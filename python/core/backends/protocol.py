"""
DiffusionBackend — the single interface that all imaging nodes program against.

Nodes never import concrete libraries (torch, diffusers, onnxruntime, etc.)
directly.  They call methods on whatever object is stored at
``executionContext.backend``, which must satisfy this Protocol.

All tensor-like objects are intentionally typed as ``Any`` so this file has
zero hard dependencies; backends are responsible for coercing values into
whatever representation their underlying library expects.

To add a new backend (ONNX, CoreML, TensorRT, …):
  1. Create a new file under ``python/core/backends/``.
  2. Implement every method in ``DiffusionBackend``.
  3. Point ``executionContext.backend`` at an instance before running a graph.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DiffusionBackend(Protocol):
    """
    Abstract interface for diffusion-pipeline operations.

    Every method maps 1-to-1 with a ComfyUI-equivalent node concept but is
    deliberately implementation-agnostic: callers never see raw torch tensors,
    HuggingFace model objects, or file-system paths from the library side.
    """

    # ── Model loading ────────────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> tuple[Any, Any, Any]:
        """
        Load a full diffusion checkpoint from *path*.

        Returns
        -------
        (model, clip, vae)
            Opaque handles.  Subsequent calls treat these as black boxes.
        """
        ...

    def load_vae(self, path: str) -> Any:
        """Load a standalone VAE checkpoint and return an opaque handle."""
        ...

    def load_clip(self, path: str, clip_type: str = "stable_diffusion") -> Any:
        """Load a standalone CLIP checkpoint and return an opaque handle."""
        ...

    # ── Text conditioning ────────────────────────────────────────────────────

    def encode_text(self, clip_handle: Any, text: str) -> list[tuple[Any, dict]]:
        """
        Run CLIP text encoding.

        Returns
        -------
        conditioning
            A list of ``(tensor, metadata_dict)`` tuples in the format nodes
            pass on their CONDITIONING ports.
        """
        ...

    # ── Latent helpers ───────────────────────────────────────────────────────

    def empty_latent(self, width: int, height: int, batch_size: int = 1) -> dict:
        """
        Create a zero-filled latent tensor.

        Returns
        -------
        {"samples": tensor}  shape (batch, 4, height//8, width//8)
        """
        ...

    # ── Diffusion sampling ───────────────────────────────────────────────────

    def sample(
        self,
        model: Any,
        positive: list[tuple[Any, dict]],
        negative: list[tuple[Any, dict]],
        latent: dict,
        seed: int,
        steps: int,
        cfg: float,
        sampler_name: str,
        scheduler: str,
        denoise: float,
        cancel_event=None,
        steps_done=None,
        step_callback=None,
    ) -> dict:
        """
        Run the denoising loop.

        Returns
        -------
        {"samples": tensor}  — updated latent dict.
        """
        ...

    def sample_init(
        self,
        model: Any,
        positive: list[tuple[Any, dict]],
        negative: list[tuple[Any, dict]],
        latent: dict,
        seed: int,
        steps: int,
        cfg: float,
        sampler_name: str,
        scheduler: str,
        denoise: float,
    ) -> dict:
        """
        Prepare the denoising loop without running any steps.

        Returns an opaque *state dict* that must be passed to every subsequent
        ``sample_step`` call.  The dict is backend-specific and contains
        (at minimum) the current latent tensor, timestep list, step index,
        text embeddings, and all static run parameters.

        Call ``sample_step(state)`` once per desired iteration.
        """
        ...

    def sample_step(self, state: dict) -> tuple[dict, bool]:
        """
        Execute a single denoising step and advance *state* in-place.

        Parameters
        ----------
        state : dict
            The opaque dict returned by ``sample_init`` (and subsequently
            mutated by each successive ``sample_step`` call).

        Returns
        -------
        (latent_dict, is_done)
            latent_dict : {"samples": tensor} — the partially-denoised latent
                         *after* this step.
            is_done     : True when all scheduled timesteps have been processed.
        """
        ...

    def sample_tiled(
        self,
        model: Any,
        positive: list[tuple[Any, dict]],
        negative: list[tuple[Any, dict]],
        latent: dict,
        seed: int,
        steps: int,
        cfg: float,
        sampler_name: str,
        scheduler: str,
        denoise: float,
        tile_size: int = 64,
        tile_overlap: int = 8,
        cancel_event=None,
        steps_done=None,
        step_callback=None,
    ) -> dict:
        """
        Tiled diffusion sampling (MultiDiffusion).

        Runs the same denoising schedule as ``sample()`` but each UNet
        forward operates on a ``tile_size × tile_size`` latent-pixel crop.
        Overlapping tile predictions are blended with a Gaussian weight
        window to eliminate visible seams.

        Use this instead of ``sample()`` when generating at resolutions
        above the model's training size (e.g. SD 1.x at >512 px).

        Parameters
        ----------
        tile_size    : tile side in latent pixels (default 64 = 512 image px).
        tile_overlap : overlap between adjacent tiles in latent pixels
                       (default 8 = 64 image px).
        """
        ...

    # ── VAE ──────────────────────────────────────────────────────────────────

    def decode_vae(self, vae_handle: Any, latent: dict) -> Any:
        """
        Decode a latent tensor to a pixel-space image.

        Returns
        -------
        image  shape (H, W, C) float32 in [0, 1], or a batch tensor of
               shape (B, H, W, C).
        """
        ...

    def encode_vae(self, vae_handle: Any, image: Any) -> dict:
        """
        Encode a pixel-space image to latent space.

        Returns
        -------
        {"samples": tensor}
        """
        ...

    # ── Image I/O ────────────────────────────────────────────────────────────

    def load_image(self, path: str) -> tuple[Any, Any]:
        """
        Load an image from *path* into the backend's native format.

        Returns
        -------
        (image, mask)
            image : (H, W, C) float32 in [0, 1]
            mask  : (H, W) float32 in [0, 1], or None if no alpha channel
        """
        ...

    def save_image(self, image: Any, path: str) -> str:
        """
        Save *image* to *path* (PNG by default).

        Returns
        -------
        Absolute path of the written file.
        """
        ...
