"""
DiffusersBackend — HuggingFace diffusers + torch implementation of DiffusionBackend.

Install prerequisites:
    pip install torch torchvision diffusers transformers accelerate Pillow

All torch/diffusers imports are deferred to individual methods so that the
module can be imported (and nodes can be registered) even in environments
where these libraries are not installed.  A clear ImportError is raised at
call-time when a dependency is missing.
"""

from __future__ import annotations

import os
from typing import Any


def _require(pkg: str, install: str) -> Any:
    """Import *pkg* or raise a helpful ImportError."""
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError as exc:
        raise ImportError(
            f"DiffusersBackend requires '{pkg}'. "
            f"Install it with: pip install {install}"
        ) from exc


def _patch_torch_xpu(torch: Any) -> None:
    """
    Stub out ``torch.xpu`` on builds that don't include Intel XPU support.

    diffusers ≥ 0.26 probes ``torch.xpu.is_available()``; diffusers ≥ 0.37
    also accesses ``torch.xpu.empty_cache`` at module-level import time.
    The ``__getattr__`` fallback returns a no-op callable for any attribute
    not explicitly defined, making the stub forward-compatible.
    """
    if not hasattr(torch, "xpu"):
        class _XPUStub:
            @staticmethod
            def is_available() -> bool:
                return False
            @staticmethod
            def device_count() -> int:
                return 0
            @staticmethod
            def current_device() -> int:
                return 0
            def __getattr__(self, name: str):  # catch-all for e.g. empty_cache
                return lambda *args, **kwargs: None
        torch.xpu = _XPUStub()


# Apply eagerly at module-import time so that `from diffusers import …`
# (which accesses torch.xpu and torch.distributed.device_mesh at its own
# module level) doesn't fail.
try:
    import torch as _torch_mod
    _patch_torch_xpu(_torch_mod)
    # Bind device_mesh as an attribute on torch.distributed so that
    # transformers' _modeling_parallel.py can access it without error.
    import torch.distributed.device_mesh as _dm  # noqa: F401
    del _dm
    del _torch_mod
except ImportError:
    pass


class DiffusersBackend:
    """
    Concrete DiffusionBackend backed by HuggingFace diffusers and PyTorch.

    This class satisfies the DiffusionBackend Protocol; it does NOT inherit
    from it to avoid import-time torch dependency.

    Usage
    -----
    ::

        from python.core.backends.diffusers_backend import DiffusersBackend

        ctx = ExecutionContext(node)
        ctx.backend = DiffusersBackend(device="cuda")
    """

    def __init__(self, device: str = "cpu", dtype: str = "float32"):
        """
        Parameters
        ----------
        device : str
            PyTorch device string, e.g. ``"cpu"``, ``"cuda"``, ``"mps"``.
        dtype : str
            Tensor dtype, e.g. ``"float32"`` or ``"float16"``.
        """
        self._device = device
        self._dtype_str = dtype
        self._torch: Any = None   # lazy-loaded

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _torch_dtype(self) -> Any:
        torch = self._get_torch()
        return getattr(torch, self._dtype_str, torch.float32)

    def _get_torch(self) -> Any:
        if self._torch is None:
            self._torch = _require("torch", "torch")
            _patch_torch_xpu(self._torch)
        return self._torch

    def _image_to_bchw_tensor(self, image: Any) -> Any:
        """
        Coerce common IMAGE representations to torch (B, C, H, W).

        Nodes generally pass torch (B, H, W, C), but resize/preview utilities
        may produce NumPy arrays or unbatched HWC values. Accepting those here
        keeps VAEEncode robust at the backend boundary.
        """
        torch = self._get_torch()
        x = image

        # PIL images do not expose tensor shape helpers; normalize them first
        # into the same float RGB range used by LoadImage.
        if hasattr(x, "save"):
            np = _require("numpy", "numpy")
            x = np.array(x.convert("RGB")).astype("float32") / 255.0

        # NumPy arrays and nested lists do not support torch.permute(), so
        # convert every non-tensor input before layout normalization.
        if not torch.is_tensor(x):
            x = torch.as_tensor(x)

        # VAE encode expects a batch axis. Accept single images from utilities
        # and promote HWC/CHW to NHWC/NCHW.
        if x.ndim == 3:
            x = x.unsqueeze(0)

        if x.ndim != 4:
            raise ValueError(f"VAE image input must be 3D or 4D, got shape {tuple(x.shape)}")

        # Convert NHWC to NCHW. Leave already-channel-first tensors alone.
        # Alpha channels are discarded because the Stable Diffusion VAE encodes
        # RGB pixels.
        if x.shape[-1] in (1, 3, 4):
            x = x[..., :3].permute(0, 3, 1, 2)
        elif x.shape[1] in (1, 3, 4):
            x = x[:, :3, :, :]
        else:
            raise ValueError(f"VAE image input must have 1, 3, or 4 channels, got shape {tuple(x.shape)}")

        return x.to(dtype=self._torch_dtype(), device=self._device)

    # ── Model loading ────────────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> tuple[Any, Any, Any]:
        """
        Load a Stable Diffusion checkpoint.

        Accepts:
          - A local ``.safetensors`` or ``.ckpt`` single-file checkpoint
          - A local diffusers-format directory
          - A HuggingFace Hub model ID (e.g. ``"runwayml/stable-diffusion-v1-5"``)

        Returns (model_handle, clip_handle, vae_handle) opaque dicts.
        """
        diffusers = _require("diffusers", "diffusers")

        _is_single_file = (
            os.path.isfile(path)
            and path.lower().endswith((".safetensors", ".ckpt"))
        )

        if _is_single_file:
            pipeline = diffusers.StableDiffusionPipeline.from_single_file(
                path,
                torch_dtype=self._torch_dtype(),
                safety_checker=None,
            ).to(self._device)
        else:
            pipeline = diffusers.StableDiffusionPipeline.from_pretrained(
                path,
                torch_dtype=self._torch_dtype(),
                safety_checker=None,
            ).to(self._device)

        # Expose sub-components as separate handles for downstream nodes
        model_handle = {"unet": pipeline.unet, "scheduler": pipeline.scheduler}
        clip_handle  = {"tokenizer": pipeline.tokenizer, "text_encoder": pipeline.text_encoder}
        vae_handle   = {"vae": pipeline.vae}

        return model_handle, clip_handle, vae_handle

    def load_vae(self, path: str) -> Any:
        diffusers = _require("diffusers", "diffusers")
        vae = diffusers.AutoencoderKL.from_pretrained(path, torch_dtype=self._torch_dtype()).to(self._device)
        return {"vae": vae}

    def load_clip(self, path: str, clip_type: str = "stable_diffusion") -> Any:
        transformers = _require("transformers", "transformers")
        tokenizer    = transformers.CLIPTokenizer.from_pretrained(path)
        text_encoder = transformers.CLIPTextModel.from_pretrained(path, torch_dtype=self._torch_dtype()).to(self._device)
        return {"tokenizer": tokenizer, "text_encoder": text_encoder}

    # ── Text conditioning ────────────────────────────────────────────────────

    def encode_text(self, clip_handle: Any, text: str) -> list[tuple[Any, dict]]:
        torch       = self._get_torch()
        tokenizer   = clip_handle["tokenizer"]
        text_encoder = clip_handle["text_encoder"]

        tokens = tokenizer(
            [text],
            padding="max_length",
            max_length=tokenizer.model_max_length,
            truncation=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            embeddings = text_encoder(tokens.input_ids.to(self._device))[0]

        return [(embeddings, {})]

    # ── Latent helpers ───────────────────────────────────────────────────────

    def empty_latent(self, width: int, height: int, batch_size: int = 1) -> dict:
        torch = self._get_torch()
        latent_h = height // 8
        latent_w = width  // 8
        samples  = torch.zeros(
            (batch_size, 4, latent_h, latent_w),
            dtype=self._torch_dtype(),
            device=self._device,
        )
        return {"samples": samples}

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
        cancel_event=None,   # threading.Event — checked each step
        steps_done=None,     # list[int] — incremented each step
        step_callback=None,  # callable(step_num: int, total: int)
    ) -> dict:
        torch     = self._get_torch()
        diffusers = _require("diffusers", "diffusers")

        unet      = model["unet"]
        sched_obj = model["scheduler"]

        # Seed
        generator = torch.Generator(device=self._device).manual_seed(seed)

        # Conditioning tensors
        pos_emb = positive[0][0]
        neg_emb = negative[0][0]
        text_embeddings = torch.cat([neg_emb, pos_emb])

        # Activate scheduler
        sched_obj.set_timesteps(steps)
        latents = latent["samples"] * sched_obj.init_noise_sigma

        timesteps = sched_obj.timesteps
        total_steps = len(timesteps)
        for i, t in enumerate(timesteps):
            if cancel_event is not None and cancel_event.is_set():
                return {"samples": latents, "cancelled": True}
            latent_input = torch.cat([latents] * 2)
            latent_input = sched_obj.scale_model_input(latent_input, timestep=t)
            with torch.no_grad():
                noise_pred = unet(latent_input, t, encoder_hidden_states=text_embeddings).sample
            noise_uncond, noise_text = noise_pred.chunk(2)
            noise_pred = noise_uncond + cfg * (noise_text - noise_uncond)
            latents = sched_obj.step(noise_pred, t, latents, generator=generator).prev_sample
            if steps_done is not None:
                steps_done[0] += 1
            if step_callback is not None:
                step_callback(i + 1, total_steps)

        return {"samples": latents}

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
        Initialise the denoising loop without running any steps.

        Sets up the scheduler, seed, text embeddings, and starting latent.
        Returns an opaque state dict for use with ``sample_step``.
        """
        torch     = self._get_torch()
        unet      = model["unet"]
        sched_obj = model["scheduler"]

        generator       = torch.Generator(device=self._device).manual_seed(seed)
        pos_emb         = positive[0][0]
        neg_emb         = negative[0][0]
        text_embeddings = torch.cat([neg_emb, pos_emb])

        sched_obj.set_timesteps(steps)
        latents   = latent["samples"] * sched_obj.init_noise_sigma
        timesteps = sched_obj.timesteps

        return {
            "latents":         latents,
            "timesteps":       timesteps,
            "step_idx":        0,
            "text_embeddings": text_embeddings,
            "sched_obj":       sched_obj,
            "unet":            unet,
            "cfg":             cfg,
            "generator":       generator,
        }

    def sample_step(self, state: dict) -> tuple[dict, bool]:
        """
        Execute one denoising step and advance *state* in-place.

        Returns ``({"samples": latent_tensor}, is_done)``.
        """
        torch           = self._get_torch()
        latents         = state["latents"]
        timesteps       = state["timesteps"]
        i               = state["step_idx"]
        t               = timesteps[i]
        text_embeddings = state["text_embeddings"]
        sched_obj       = state["sched_obj"]
        unet            = state["unet"]
        cfg             = state["cfg"]
        generator       = state["generator"]

        latent_input = torch.cat([latents] * 2)
        latent_input = sched_obj.scale_model_input(latent_input, timestep=t)
        with torch.no_grad():
            noise_pred = unet(latent_input, t, encoder_hidden_states=text_embeddings).sample
        noise_uncond, noise_text = noise_pred.chunk(2)
        noise_pred = noise_uncond + cfg * (noise_text - noise_uncond)
        latents    = sched_obj.step(noise_pred, t, latents, generator=generator).prev_sample

        state["latents"]  = latents
        state["step_idx"] = i + 1

        is_done = state["step_idx"] >= len(timesteps)
        return {"samples": latents}, is_done

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

        Same as ``sample()`` but the UNet forward is replaced by the
        Gaussian-weighted tiled noise prediction from ``._tiling``.
        """
        from ._tiling import tiled_noise_pred

        torch     = self._get_torch()
        unet      = model["unet"]
        sched_obj = model["scheduler"]

        generator       = torch.Generator(device=self._device).manual_seed(seed)
        text_embeddings = torch.cat([negative[0][0], positive[0][0]])

        sched_obj.set_timesteps(steps)
        latents     = latent["samples"] * sched_obj.init_noise_sigma
        timesteps   = sched_obj.timesteps
        total_steps = len(timesteps)

        for i, t in enumerate(timesteps):
            if cancel_event is not None and cancel_event.is_set():
                return {"samples": latents, "cancelled": True}

            noise_pred = tiled_noise_pred(
                unet, latents, t, text_embeddings, sched_obj,
                cfg, tile_size, tile_overlap, torch,
            )
            latents = sched_obj.step(
                noise_pred, t, latents, generator=generator
            ).prev_sample

            if steps_done is not None:
                steps_done[0] += 1
            if step_callback is not None:
                step_callback(i + 1, total_steps)

        return {"samples": latents}

    # ── VAE ──────────────────────────────────────────────────────────────────

    def decode_vae(self, vae_handle: Any, latent: dict) -> Any:
        torch = self._get_torch()
        vae   = vae_handle["vae"]
        with torch.no_grad():
            decoded = vae.decode(latent["samples"] / 0.18215).sample
        # Convert (B, C, H, W) → (B, H, W, C) float32 in [0, 1]
        image = (decoded / 2 + 0.5).clamp(0, 1)
        image = image.permute(0, 2, 3, 1).cpu().float()
        return image

    def encode_vae(self, vae_handle: Any, image: Any) -> dict:
        torch = self._get_torch()
        vae   = vae_handle["vae"]
        x = self._image_to_bchw_tensor(image)
        x = 2.0 * x - 1.0
        with torch.no_grad():
            latent = vae.encode(x).latent_dist.sample() * 0.18215
        return {"samples": latent}

    # ── Image I/O ────────────────────────────────────────────────────────────

    def load_image(self, path: str) -> tuple[Any, Any]:
        torch = self._get_torch()
        PIL   = _require("PIL.Image", "Pillow")

        img = PIL.open(path).convert("RGBA")
        rgb = img.convert("RGB")

        np = _require("numpy", "numpy")
        rgb_arr  = np.array(rgb).astype("float32") / 255.0
        image    = torch.from_numpy(rgb_arr).unsqueeze(0)   # (1, H, W, 3)

        alpha = img.getchannel("A")
        if alpha.getextrema() == (255, 255):
            mask = None
        else:
            mask_arr = 1.0 - np.array(alpha).astype("float32") / 255.0
            mask = torch.from_numpy(mask_arr).unsqueeze(0)  # (1, H, W)

        return image, mask

    def save_image(self, image: Any, path: str) -> str:
        np = _require("numpy", "numpy")
        PIL = _require("PIL.Image", "Pillow")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        # Accept (B, H, W, C) or (H, W, C)
        arr = image
        if hasattr(arr, "cpu"):
            arr = arr.cpu()
        if hasattr(arr, "numpy"):
            arr = arr.numpy()
        if arr.ndim == 4:
            arr = arr[0]  # take first in batch

        arr = (arr * 255).clip(0, 255).astype("uint8")
        PIL.fromarray(arr).save(path)
        return os.path.abspath(path)
