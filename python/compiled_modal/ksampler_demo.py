#!/usr/bin/env python3
"""
Compiled from NodeGraph: ksampler-demo
Target:    modal.com

Graph topology (sequential):
  CheckpointLoader
    → CLIPTextEncode (PositivePrompt)
    → CLIPTextEncode (NegativePrompt)
    → EmptyLatentImage
    → KSampler
    → VAEDecode
    → SaveImage

Source graph parameters (from saves/kSamplerDemo.json):
  positive_prompt : "a small robot sketching a node graph, soft studio light"
  negative_prompt : "blurry, low quality, distorted"
  width / height  : 512 × 512   batch_size : 1
  seed : 12345   steps : 12   cfg : 7.0
  sampler_name : "euler"   scheduler : "normal"   denoise : 1.0
  model_id : "runwayml/stable-diffusion-v1-5"  (local ckpt_path → HF hub)

Dependencies (installed automatically by Modal):
  torch, diffusers, transformers, accelerate, safetensors, Pillow

Usage:
  modal run python/compiled_modal/ksampler_demo.py
  modal run python/compiled_modal/ksampler_demo.py --detach
"""

from __future__ import annotations

import io
import modal

# ── Modal app & container image ───────────────────────────────────────────────

app = modal.App("ksampler-demo")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.4.1",
        "torchvision==0.19.1",
        "diffusers==0.31.0",
        "transformers==4.44.2",
        "accelerate>=0.33.0",
        "safetensors>=0.4.3",
        "Pillow>=10.3.0",
    )
)

# Modal Volume caches model weights across runs so you only download once.
# Create it once: `modal volume create ksampler-model-cache`
model_volume = modal.Volume.from_name("ksampler-model-cache", create_if_missing=True)
MODEL_CACHE_DIR = "/model-cache"

# ── Scheduler mapping ─────────────────────────────────────────────────────────
# Maps (sampler_name, scheduler_name) used in the graph to the corresponding
# diffusers scheduler class name.  The scheduler is built from the pipeline's
# own config so all beta/sigma settings stay consistent with the checkpoint.

_SCHEDULER_CLASS_MAP: dict[tuple[str, str], str] = {
    ("euler",               "normal"):  "EulerDiscreteScheduler",
    ("euler",               "karras"):  "EulerDiscreteScheduler",          # use_karras_sigmas=True
    ("euler_ancestral",     "normal"):  "EulerAncestralDiscreteScheduler",
    ("euler_ancestral",     "karras"):  "EulerAncestralDiscreteScheduler",
    ("dpm_2",               "normal"):  "KDPM2DiscreteScheduler",
    ("dpm_2",               "karras"):  "KDPM2DiscreteScheduler",
    ("dpmpp_2m",            "normal"):  "DPMSolverMultistepScheduler",
    ("dpmpp_2m",            "karras"):  "DPMSolverMultistepScheduler",     # use_karras_sigmas=True
    ("dpmpp_sde",           "normal"):  "DPMSolverSDEScheduler",
    ("ddim",                "normal"):  "DDIMScheduler",
    ("uni_pc",              "normal"):  "UniPCMultistepScheduler",
}

_KARRAS_SCHEDULERS = {
    "EulerDiscreteScheduler",
    "KDPM2DiscreteScheduler",
    "DPMSolverMultistepScheduler",
}


def _build_scheduler(pipe, sampler_name: str, scheduler_name: str):
    """
    Corresponds to the KSampler node's sampler_name / scheduler inputs.
    Builds a diffusers scheduler from the pipeline's existing config so that
    the beta schedule and other checkpoint-specific settings are preserved.
    """
    import diffusers

    key = (sampler_name, scheduler_name)
    class_name = _SCHEDULER_CLASS_MAP.get(key)
    if class_name is None:
        print(
            f"[warn] Unknown sampler/scheduler pair {key!r}; "
            "falling back to EulerDiscreteScheduler."
        )
        class_name = "EulerDiscreteScheduler"

    cls = getattr(diffusers, class_name)
    kwargs: dict = {}
    if scheduler_name == "karras" and class_name in _KARRAS_SCHEDULERS:
        kwargs["use_karras_sigmas"] = True

    return cls.from_config(pipe.scheduler.config, **kwargs)


# ── Node implementations ───────────────────────────────────────────────────────

def _checkpoint_loader(model_id: str, cache_dir: str, sampler_name: str, scheduler_name: str):
    """
    CheckpointLoader node.
    Loads the pipeline from the HuggingFace hub (or local volume cache) and
    replaces its default scheduler with the one specified in the graph.
    Returns the configured pipeline on the GPU.
    """
    import torch
    from diffusers import StableDiffusionPipeline

    print(f"[CheckpointLoader] Loading {model_id!r} …")
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        cache_dir=cache_dir,
        torch_dtype=torch.float16,
        safety_checker=None,
        requires_safety_checker=False,
    )
    pipe = pipe.to("cuda")
    pipe.scheduler = _build_scheduler(pipe, sampler_name, scheduler_name)
    print("[CheckpointLoader] Done.")
    return pipe


def _clip_text_encode(pipe, text: str):
    """
    CLIPTextEncode node.
    Encodes a single text prompt.  Call once for positive, once for negative.
    Returns the conditioning tensor.
    """
    import torch

    tokens = pipe.tokenizer(
        text,
        padding="max_length",
        max_length=pipe.tokenizer.model_max_length,
        truncation=True,
        return_tensors="pt",
    )
    with torch.no_grad():
        conditioning = pipe.text_encoder(tokens.input_ids.to("cuda"))[0]
    return conditioning


def _empty_latent_image(pipe, width: int, height: int, batch_size: int):
    """
    EmptyLatentImage node.
    Creates a zeroed latent tensor of the correct shape for this pipeline.
    KSampler will overwrite it with noise when denoise=1.0.
    """
    import torch

    return torch.zeros(
        (batch_size, pipe.unet.config.in_channels, height // 8, width // 8),
        device="cuda",
        dtype=torch.float16,
    )


def _ksampler(
    pipe,
    positive_cond,
    negative_cond,
    latent_image,
    seed: int,
    steps: int,
    cfg: float,
    denoise: float,
):
    """
    KSampler node.
    Runs the denoising loop with classifier-free guidance.
    Returns the denoised latent tensor.
    """
    import torch

    scheduler = pipe.scheduler
    scheduler.set_timesteps(steps)
    timesteps = scheduler.timesteps

    # Apply denoise strength — skip early timesteps for img2img-style runs
    if denoise < 1.0:
        start_idx = int((1.0 - denoise) * len(timesteps))
        timesteps = timesteps[start_idx:]

    # Start from pure noise (text-to-image, denoise=1.0)
    generator = torch.Generator(device="cuda").manual_seed(seed)
    latent = torch.randn(
        latent_image.shape,
        generator=generator,
        device="cuda",
        dtype=torch.float16,
    )
    latent = latent * scheduler.init_noise_sigma

    # Classifier-free guidance — batch positive and negative together
    cond_batch = torch.cat([negative_cond, positive_cond])

    for i, t in enumerate(timesteps):
        latent_input = torch.cat([latent] * 2)
        latent_input = scheduler.scale_model_input(latent_input, t)

        with torch.no_grad():
            noise_pred = pipe.unet(
                latent_input, t, encoder_hidden_states=cond_batch
            ).sample

        noise_uncond, noise_cond = noise_pred.chunk(2)
        noise_pred = noise_uncond + cfg * (noise_cond - noise_uncond)
        latent = scheduler.step(noise_pred, t, latent).prev_sample

        print(f"  [KSampler] step {i + 1}/{len(timesteps)}")

    return latent


def _vae_decode(pipe, latent):
    """
    VAEDecode node.
    Decodes a latent tensor to a PIL Image.
    """
    import torch
    from PIL import Image as PILImage

    latent = latent / pipe.vae.config.scaling_factor
    with torch.no_grad():
        image_tensor = pipe.vae.decode(latent).sample

    image_tensor = (image_tensor / 2 + 0.5).clamp(0, 1)
    image_np = (
        image_tensor.cpu()
        .permute(0, 2, 3, 1)
        .float()
        .numpy()[0]
    )
    return PILImage.fromarray((image_np * 255).round().astype("uint8"))


def _save_image(image) -> bytes:
    """
    SaveImage node.
    Returns the image as PNG bytes; the local entrypoint writes them to disk.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


# ── Modal function ────────────────────────────────────────────────────────────

@app.function(
    image=image,
    gpu="A10G",
    volumes={MODEL_CACHE_DIR: model_volume},
    timeout=600,
)
def generate(
    positive_prompt: str = "a small robot sketching a node graph, soft studio light",
    negative_prompt: str = "blurry, low quality, distorted",
    width: int = 512,
    height: int = 512,
    batch_size: int = 1,
    seed: int = 12345,
    steps: int = 12,
    cfg: float = 7.0,
    sampler_name: str = "euler",
    scheduler_name: str = "normal",
    denoise: float = 1.0,
    model_id: str = "runwayml/stable-diffusion-v1-5",
) -> bytes:
    """
    KSampler demo pipeline compiled from NodeGraph.
    Executes the graph nodes in topological order and returns a PNG image
    as bytes.  All graph parameter defaults match the saved graph exactly.
    """
    # ── CheckpointLoader ──────────────────────────────────────────────────────
    pipe = _checkpoint_loader(model_id, MODEL_CACHE_DIR, sampler_name, scheduler_name)

    # ── CLIPTextEncode (PositivePrompt) ───────────────────────────────────────
    print(f"[CLIPTextEncode] Encoding positive prompt …")
    positive_cond = _clip_text_encode(pipe, positive_prompt)

    # ── CLIPTextEncode (NegativePrompt) ───────────────────────────────────────
    print(f"[CLIPTextEncode] Encoding negative prompt …")
    negative_cond = _clip_text_encode(pipe, negative_prompt)

    # ── EmptyLatentImage ──────────────────────────────────────────────────────
    latent_image = _empty_latent_image(pipe, width, height, batch_size)

    # ── KSampler ──────────────────────────────────────────────────────────────
    print(f"[KSampler] {steps} steps, cfg={cfg}, seed={seed} …")
    latent = _ksampler(
        pipe,
        positive_cond,
        negative_cond,
        latent_image,
        seed=seed,
        steps=steps,
        cfg=cfg,
        denoise=denoise,
    )

    # ── VAEDecode ─────────────────────────────────────────────────────────────
    print("[VAEDecode] Decoding latent …")
    image = _vae_decode(pipe, latent)

    # ── SaveImage ─────────────────────────────────────────────────────────────
    print("[SaveImage] Encoding PNG …")
    return _save_image(image)


# ── Local entrypoint ─────────────────────────────────────────────────────────

@app.local_entrypoint()
def main():
    """
    Invokes generate() on Modal and saves the returned PNG locally.
    Run with:  modal run python/compiled_modal/ksampler_demo.py
    """
    import os

    print("Submitting graph to Modal …")
    png_bytes = generate.remote()

    output_dir = "./output"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "ksampler_demo.png")

    with open(out_path, "wb") as f:
        f.write(png_bytes)

    print(f"Image saved → {out_path}")
