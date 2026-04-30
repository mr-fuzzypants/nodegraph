"""
SafetensorsBackend — component-level PyTorch backend for the DiffusionBackend protocol.

Unlike DiffusersBackend this class never constructs a ``StableDiffusionPipeline``.
Instead it loads each model component (UNet, VAE, CLIP) individually, giving you
full control over memory layout, device placement, and the inference loop.

Supported checkpoint formats
-----------------------------
* Single-file ``.safetensors`` (CivitAI / A1111 format)
* Single-file ``.ckpt``
* HuggingFace diffusers-format directory (``unet/``, ``vae/``, ``tokenizer/`` …)

Install prerequisites
----------------------
    pip install torch safetensors diffusers transformers accelerate Pillow numpy

The pipeline loop / scheduler code uses ``diffusers.schedulers`` only — the
heavyweight pipeline classes (``StableDiffusionPipeline`` etc.) are never imported.

Sampler support
---------------
The ``sampler_name`` argument to ``sample()`` is mapped to a diffusers scheduler
class.  Scheduler hyperparameters (Karras sigmas, beta schedule, …) are set via
the ``scheduler`` string and optional ``scheduler_config`` constructor argument.

Supported sampler names (default: ``euler``)
    euler, euler_ancestral, heun, dpm_2, dpm_2_ancestral,
    lms, dpmpp_2m, dpmpp_sde, ddim, pndm

Usage
-----
::

    from python.core.backends.safetensors_backend import SafetensorsBackend

    ctx = ExecutionContext(node)
    ctx.backend = SafetensorsBackend(device="mps", dtype="float16")
"""

from __future__ import annotations

import os
from typing import Any


# ── sampler name → diffusers scheduler class name ────────────────────────────
_SAMPLER_CLASS_MAP: dict[str, str] = {
    "euler":              "EulerDiscreteScheduler",
    "euler_ancestral":    "EulerAncestralDiscreteScheduler",
    "heun":               "HeunDiscreteScheduler",
    "dpm_2":              "KDPM2DiscreteScheduler",
    "dpm_2_ancestral":    "KDPM2AncestralDiscreteScheduler",
    "lms":                "LMSDiscreteScheduler",
    "dpmpp_2m":           "DPMSolverMultistepScheduler",
    "dpmpp_sde":          "DPMSolverSDEScheduler",
    "ddim":               "DDIMScheduler",
    "pndm":               "PNDMScheduler",
}

# Default SD 1.x scheduler kwargs — used when building from scratch rather
# than from a saved config.
_DEFAULT_SCHEDULER_KWARGS: dict[str, Any] = {
    "beta_start":            0.00085,
    "beta_end":              0.012,
    "beta_schedule":         "scaled_linear",
    "clip_sample":           False,
    "steps_offset":          1,
    "prediction_type":       "epsilon",
}


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


def _require(pkg: str, install: str) -> Any:
    import importlib
    try:
        return importlib.import_module(pkg)
    except ImportError as exc:
        raise ImportError(
            f"SafetensorsBackend requires '{pkg}'. "
            f"Install it with: pip install {install}"
        ) from exc


class SafetensorsBackend:
    """
    DiffusionBackend implementation that avoids the diffusers Pipeline layer.

    Model components are loaded individually so callers can:
      * Load just the VAE or CLIP without pulling the full UNet into VRAM.
      * Swap schedulers at inference time without reloading weights.
      * Use custom UNet configs or LoRA-patched models.
    """

    def __init__(
        self,
        device: str = "cpu",
        dtype: str = "float32",
        clip_model_id: str = "openai/clip-vit-large-patch14",
        scheduler_config: dict | None = None,
    ):
        """
        Parameters
        ----------
        device : str
            PyTorch device, e.g. ``"cuda"``, ``"mps"``, ``"cpu"``.
        dtype : str
            Tensor dtype: ``"float32"`` or ``"float16"``.
        clip_model_id : str
            HuggingFace Hub ID used as fallback for the tokenizer (and text
            encoder when loading from a single-file checkpoint that doesn't
            embed extractable CLIP weights).
        scheduler_config : dict, optional
            Extra kwargs forwarded to the scheduler constructor, e.g.
            ``{"use_karras_sigmas": True}``.
        """
        self._device        = device
        self._dtype_str     = dtype
        self._clip_model_id = clip_model_id
        self._sched_cfg     = scheduler_config or {}
        self._torch: Any    = None

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_torch(self) -> Any:
        if self._torch is None:
            self._torch = _require("torch", "torch")
            _patch_torch_xpu(self._torch)
        return self._torch

    def _torch_dtype(self) -> Any:
        torch = self._get_torch()
        return getattr(torch, self._dtype_str, torch.float32)

    def _image_to_bchw_tensor(self, image: Any) -> Any:
        """
        Coerce common IMAGE representations to torch (B, C, H, W).

        The graph convention is torch (B, H, W, C), but image utility nodes can
        hand back NumPy arrays or unbatched images. Normalize that at the
        backend boundary before calling the VAE.
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

    @staticmethod
    def _is_single_file(path: str) -> bool:
        return os.path.isfile(path) and path.lower().endswith((".safetensors", ".ckpt"))

    def _build_scheduler(self, sampler_name: str, scheduler_name: str) -> Any:
        """
        Construct a fresh diffusers scheduler instance.

        ``sampler_name`` selects the algorithm class.
        ``scheduler_name`` toggles Karras sigmas when the class supports it.
        """
        diffusers_schedulers = _require("diffusers.schedulers", "diffusers")
        cls_name = _SAMPLER_CLASS_MAP.get(sampler_name, "EulerDiscreteScheduler")
        cls      = getattr(diffusers_schedulers, cls_name, None)
        if cls is None:
            cls = diffusers_schedulers.EulerDiscreteScheduler

        kwargs = {**_DEFAULT_SCHEDULER_KWARGS, **self._sched_cfg}
        if scheduler_name == "karras":
            kwargs["use_karras_sigmas"] = True

        # Not every scheduler accepts every kwarg — filter to what the class allows.
        import inspect
        valid = set(inspect.signature(cls.__init__).parameters)
        kwargs = {k: v for k, v in kwargs.items() if k in valid}

        return cls(**kwargs)

    # ── Model loading ────────────────────────────────────────────────────────

    def load_checkpoint(self, path: str) -> tuple[Any, Any, Any]:
        """
        Load a checkpoint and return ``(model_handle, clip_handle, vae_handle)``.

        Each handle is an opaque dict consumed by the other backend methods.
        For single-file checkpoints the individual model classes extract their
        own sub-weights so you do NOT need a pre-converted diffusers directory.
        """
        from diffusers import UNet2DConditionModel, AutoencoderKL  # type: ignore
        from transformers import CLIPTextModel, CLIPTokenizer       # type: ignore

        dtype = self._torch_dtype()

        if self._is_single_file(path):
            unet = UNet2DConditionModel.from_single_file(path, torch_dtype=dtype)
            vae  = AutoencoderKL.from_single_file(path,  torch_dtype=dtype)
            try:
                text_encoder = CLIPTextModel.from_single_file(path, torch_dtype=dtype)
            except Exception:
                # Some single-file formats don't support per-component extraction
                # for the text encoder; fall back to the Hub reference model.
                text_encoder = CLIPTextModel.from_pretrained(
                    self._clip_model_id, torch_dtype=dtype
                )
            tokenizer = CLIPTokenizer.from_pretrained(self._clip_model_id)
        else:
            # Diffusers-format directory or HuggingFace Hub model ID.
            # local_files_only=True for filesystem paths so newer HF Hub
            # doesn't reject absolute paths as repo IDs.
            local = os.path.isdir(path)
            extra: dict = {"local_files_only": True} if local else {}
            unet = UNet2DConditionModel.from_pretrained(
                path, subfolder="unet", torch_dtype=dtype, **extra
            )
            vae  = AutoencoderKL.from_pretrained(
                path, subfolder="vae", torch_dtype=dtype, **extra
            )
            text_encoder = CLIPTextModel.from_pretrained(
                path, subfolder="text_encoder", torch_dtype=dtype, **extra
            )
            tokenizer = CLIPTokenizer.from_pretrained(
                path, subfolder="tokenizer", **extra
            )

        unet.to(self._device).eval()
        vae.to(self._device).eval()
        text_encoder.to(self._device).eval()

        model_handle = {"unet": unet}
        clip_handle  = {"tokenizer": tokenizer, "text_encoder": text_encoder}
        vae_handle   = {"vae": vae}

        return model_handle, clip_handle, vae_handle

    def load_vae(self, path: str) -> Any:
        from diffusers import AutoencoderKL  # type: ignore
        if self._is_single_file(path):
            vae = AutoencoderKL.from_single_file(path, torch_dtype=self._torch_dtype())
        else:
            vae = AutoencoderKL.from_pretrained(path, torch_dtype=self._torch_dtype())
        return {"vae": vae.to(self._device).eval()}

    def load_clip(self, path: str, clip_type: str = "stable_diffusion") -> Any:
        from transformers import CLIPTextModel, CLIPTokenizer  # type: ignore
        text_encoder = CLIPTextModel.from_pretrained(
            path, torch_dtype=self._torch_dtype()
        ).to(self._device).eval()
        tokenizer = CLIPTokenizer.from_pretrained(path)
        return {"tokenizer": tokenizer, "text_encoder": text_encoder}

    # ── Text conditioning ────────────────────────────────────────────────────

    def encode_text(self, clip_handle: Any, text: str) -> list[tuple[Any, dict]]:
        torch        = self._get_torch()
        tokenizer    = clip_handle["tokenizer"]
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
        samples = torch.zeros(
            (batch_size, 4, height // 8, width // 8),
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
        cancel_event=None,   # threading.Event | asyncio.Event — checked each step
        steps_done=None,     # list[int] — incremented each step so callers know how far we got
        step_callback=None,  # callable(step_num: int, total: int) — fired after each step
    ) -> dict:
        torch     = self._get_torch()
        unet      = model["unet"]
        sched_obj = self._build_scheduler(sampler_name, scheduler)

        generator = torch.Generator(device=self._device).manual_seed(seed)
        pos_emb   = positive[0][0]
        neg_emb   = negative[0][0]
        text_embeddings = torch.cat([neg_emb, pos_emb])

        latents = latent["samples"].to(device=self._device, dtype=self._torch_dtype())

        sched_obj.set_timesteps(steps)
        timesteps = sched_obj.timesteps

        if denoise < 1.0:
            # img2img: add noise only up to the appropriate timestep
            noise      = torch.randn(
                latents.shape, generator=generator,
                dtype=latents.dtype, device=self._device
            )
            start_step = max(0, int(steps * (1.0 - denoise)))
            t_start    = timesteps[start_step : start_step + 1]
            latents    = sched_obj.add_noise(latents, noise, t_start)
            timesteps  = timesteps[start_step:]
        else:
            # txt2img: the input latent provides only the target shape — replace
            # it entirely with seeded Gaussian noise scaled to the scheduler's
            # expected initial magnitude.  Multiplying the zero-filled empty
            # latent by init_sigma keeps it zero, which produces a near-uniform
            # grey image regardless of the prompt.
            noise      = torch.randn(
                latents.shape, generator=generator,
                dtype=latents.dtype, device=self._device
            )
            init_sigma = getattr(sched_obj, "init_noise_sigma", 1.0)
            latents    = noise * init_sigma

        total_steps = len(timesteps)
        for i, t in enumerate(timesteps):
            # Check for cancellation before each denoising step.
            if cancel_event is not None and cancel_event.is_set():
                return {"samples": latents, "cancelled": True}

            latent_input = torch.cat([latents] * 2)
            latent_input = sched_obj.scale_model_input(latent_input, t)
            # MPS does not support float64; cast timestep to match latent dtype.
            t_cast = t.to(dtype=latents.dtype) if hasattr(t, "to") else t
            with torch.no_grad():
                noise_pred = unet(
                    latent_input, t_cast, encoder_hidden_states=text_embeddings
                ).sample
            noise_uncond, noise_text = noise_pred.chunk(2)
            noise_pred = noise_uncond + cfg * (noise_text - noise_uncond)
            # Not all schedulers accept a generator kwarg in .step()
            import inspect
            step_params = inspect.signature(sched_obj.step).parameters
            if "generator" in step_params:
                latents = sched_obj.step(
                    noise_pred, t, latents, generator=generator
                ).prev_sample
            else:
                latents = sched_obj.step(noise_pred, t, latents).prev_sample
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

        Sets up the scheduler, seed, text embeddings, and starting latent
        (including noise-scaling for txt2img / partial-denoise for img2img).
        Returns an opaque state dict for use with ``sample_step``.
        """
        torch     = self._get_torch()
        unet      = model["unet"]
        sched_obj = self._build_scheduler(sampler_name, scheduler)

        generator       = torch.Generator(device=self._device).manual_seed(seed)
        pos_emb         = positive[0][0]
        neg_emb         = negative[0][0]
        text_embeddings = torch.cat([neg_emb, pos_emb])

        latents   = latent["samples"].to(device=self._device, dtype=self._torch_dtype())
        sched_obj.set_timesteps(steps)
        timesteps = sched_obj.timesteps

        if denoise < 1.0:
            noise      = torch.randn(
                latents.shape, generator=generator,
                dtype=latents.dtype, device=self._device
            )
            start_step = max(0, int(steps * (1.0 - denoise)))
            t_start    = timesteps[start_step : start_step + 1]
            latents    = sched_obj.add_noise(latents, noise, t_start)
            timesteps  = timesteps[start_step:]
        else:
            noise      = torch.randn(
                latents.shape, generator=generator,
                dtype=latents.dtype, device=self._device
            )
            init_sigma = getattr(sched_obj, "init_noise_sigma", 1.0)
            latents    = noise * init_sigma

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
        import inspect
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
        latent_input = sched_obj.scale_model_input(latent_input, t)
        t_cast = t.to(dtype=latents.dtype) if hasattr(t, "to") else t
        with torch.no_grad():
            noise_pred = unet(
                latent_input, t_cast, encoder_hidden_states=text_embeddings
            ).sample
        noise_uncond, noise_text = noise_pred.chunk(2)
        noise_pred = noise_uncond + cfg * (noise_text - noise_uncond)

        step_params = inspect.signature(sched_obj.step).parameters
        if "generator" in step_params:
            latents = sched_obj.step(noise_pred, t, latents, generator=generator).prev_sample
        else:
            latents = sched_obj.step(noise_pred, t, latents).prev_sample

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

        Identical denoising schedule and img2img denoise-strength logic as
        ``sample()``, but the UNet forward is replaced by ``tiled_noise_pred``
        from ``._tiling``.  Overlapping tile predictions are blended by
        a Gaussian weight window so seams are not visible.
        """
        from ._tiling import tiled_noise_pred
        import inspect

        torch     = self._get_torch()
        unet      = model["unet"]
        sched_obj = self._build_scheduler(sampler_name, scheduler)

        generator       = torch.Generator(device=self._device).manual_seed(seed)
        text_embeddings = torch.cat([negative[0][0], positive[0][0]])
        latents         = latent["samples"].to(device=self._device, dtype=self._torch_dtype())

        sched_obj.set_timesteps(steps)
        timesteps = sched_obj.timesteps

        if denoise < 1.0:
            noise      = torch.randn(
                latents.shape, generator=generator,
                dtype=latents.dtype, device=self._device,
            )
            start_step = max(0, int(steps * (1.0 - denoise)))
            latents    = sched_obj.add_noise(
                latents, noise, timesteps[start_step : start_step + 1]
            )
            timesteps  = timesteps[start_step:]
        else:
            noise      = torch.randn(
                latents.shape, generator=generator,
                dtype=latents.dtype, device=self._device,
            )
            latents = noise * getattr(sched_obj, "init_noise_sigma", 1.0)

        total_steps = len(timesteps)
        for i, t in enumerate(timesteps):
            if cancel_event is not None and cancel_event.is_set():
                return {"samples": latents, "cancelled": True}

            noise_pred = tiled_noise_pred(
                unet, latents, t, text_embeddings, sched_obj,
                cfg, tile_size, tile_overlap, torch,
            )

            step_params = inspect.signature(sched_obj.step).parameters
            if "generator" in step_params:
                latents = sched_obj.step(
                    noise_pred, t, latents, generator=generator
                ).prev_sample
            else:
                latents = sched_obj.step(noise_pred, t, latents).prev_sample

            if steps_done is not None:
                steps_done[0] += 1
            if step_callback is not None:
                step_callback(i + 1, total_steps)

        return {"samples": latents}

    # ── VAE ──────────────────────────────────────────────────────────────────

    def decode_vae(self, vae_handle: Any, latent: dict) -> Any:
        torch = self._get_torch()
        vae   = vae_handle["vae"]
        # VAE decode is numerically unstable in float16 on MPS (and sometimes
        # CUDA), producing NaN/inf that clamp to a solid grey image.  Upcast to
        # float32 for the decode step only, then restore the original dtype.
        original_dtype = next(vae.parameters()).dtype
        needs_upcast = (original_dtype == torch.float16)
        if needs_upcast:
            vae = vae.to(dtype=torch.float32)
        latent_f32 = latent["samples"].to(dtype=torch.float32)
        with torch.no_grad():
            decoded = vae.decode(latent_f32 / 0.18215).sample
        if needs_upcast:
            vae.to(dtype=original_dtype)
        image = (decoded / 2 + 0.5).clamp(0, 1)
        return image.permute(0, 2, 3, 1).cpu().float()  # (B, H, W, C)

    def encode_vae(self, vae_handle: Any, image: Any) -> dict:
        torch = self._get_torch()
        vae   = vae_handle["vae"]
        x     = self._image_to_bchw_tensor(image)
        x     = 2.0 * x - 1.0
        with torch.no_grad():
            latent = vae.encode(x).latent_dist.sample() * 0.18215
        return {"samples": latent}

    # ── Image I/O ────────────────────────────────────────────────────────────

    def load_image(self, path: str) -> tuple[Any, Any]:
        torch = self._get_torch()
        PIL   = _require("PIL.Image", "Pillow")
        np    = _require("numpy", "numpy")

        img     = PIL.open(path).convert("RGBA")
        rgb_arr = np.array(img.convert("RGB")).astype("float32") / 255.0
        image   = torch.from_numpy(rgb_arr).unsqueeze(0)  # (1, H, W, 3)

        alpha = img.getchannel("A")
        if alpha.getextrema() == (255, 255):
            mask = None
        else:
            mask_arr = 1.0 - np.array(alpha).astype("float32") / 255.0
            mask     = torch.from_numpy(mask_arr).unsqueeze(0)  # (1, H, W)

        return image, mask

    def save_image(self, image: Any, path: str) -> str:
        np  = _require("numpy", "numpy")
        PIL = _require("PIL.Image", "Pillow")

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        arr = image
        if hasattr(arr, "cpu"):
            arr = arr.cpu()
        if hasattr(arr, "numpy"):
            arr = arr.numpy()
        if arr.ndim == 4:
            arr = arr[0]

        arr = (arr * 255).clip(0, 255).astype("uint8")
        PIL.fromarray(arr).save(path)
        return os.path.abspath(path)
