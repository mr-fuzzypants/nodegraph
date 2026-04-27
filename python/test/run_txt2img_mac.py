#!/usr/bin/env python3
"""
run_txt2img_mac.py — end-to-end txt2img smoke-test on macOS.

Runs a minimal Stable Diffusion txt2img pipeline entirely through the
NodeGraph imaging nodes using SafetensorsBackend with MPS acceleration.

Usage
-----
    # With a local .safetensors file:
    python python/test/run_txt2img_mac.py --model /path/to/model.safetensors

    # With a local diffusers-format directory:
    python python/test/run_txt2img_mac.py --model /path/to/sd-v1-5/

    # With a HuggingFace Hub model ID (downloads on first run):
    python python/test/run_txt2img_mac.py --model runwayml/stable-diffusion-v1-5

    # Full options:
    python python/test/run_txt2img_mac.py \\
        --model  runwayml/stable-diffusion-v1-5 \\
        --prompt "a photo of a shiba inu on a snowy mountain" \\
        --negative "blurry, low quality, watermark" \\
        --steps  20 \\
        --cfg    7.5 \\
        --width  512 \\
        --height 512 \\
        --seed   42 \\
        --out    ./output \\
        --dtype  float16

Prerequisites
-------------
    pip install torch diffusers transformers accelerate safetensors Pillow numpy

For MPS (Apple Silicon) torch must be >= 2.0:
    pip install --upgrade torch
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

# ── Make the workspace importable from any cwd ───────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# ── Register imaging nodes ───────────────────────────────────────────────────
import nodegraph.python.noderegistry.imaging  # noqa: F401


def _detect_device(requested: str | None) -> str:
    """Pick the best available device, preferring MPS on Apple Silicon."""
    try:
        import torch  # type: ignore
    except ImportError:
        raise SystemExit("torch is not installed. Run: pip install torch")

    if requested:
        return requested

    if torch.backends.mps.is_available():
        print("[device] Apple MPS (Metal) detected — using GPU acceleration.")
        return "mps"
    if torch.cuda.is_available():
        print("[device] CUDA detected.")
        return "cuda"
    print("[device] No GPU found — running on CPU (will be slow).")
    return "cpu"


def _safe_dtype(device: str, requested: str) -> str:
    """
    float16 is generally fine on MPS with PyTorch >= 2.1.
    Fall back to float32 on CPU to avoid precision issues.
    """
    if device == "cpu" and requested == "float16":
        print("[dtype] CPU detected — overriding float16 → float32.")
        return "float32"
    return requested


class _Ctx:
    """Minimal execution context carrying the backend."""
    def __init__(self, backend):
        self.backend = backend


async def run(args: argparse.Namespace) -> None:
    from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend
    from nodegraph.python.core.Node import Node

    device = _detect_device(args.device)
    dtype  = _safe_dtype(device, args.dtype)

    print(f"[config] device={device}  dtype={dtype}  steps={args.steps}  "
          f"cfg={args.cfg}  seed={args.seed}  size={args.width}×{args.height}")

    backend = SafetensorsBackend(
        device=device,
        dtype=dtype,
        scheduler_config={"use_karras_sigmas": True} if args.karras else {},
    )
    ctx = _Ctx(backend)

    # ── 1. Load checkpoint ────────────────────────────────────────────────────
    print(f"\n[1/6] Loading checkpoint: {args.model}")
    t0 = time.perf_counter()
    loader = Node.create_node("loader", "CheckpointLoader")
    loader.inputs["ckpt_path"].value = args.model
    result = await loader.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] CheckpointLoader failed: {loader.outputs['error'].value}")
    print(f"      done in {time.perf_counter() - t0:.1f}s")

    model_handle = loader.outputs["MODEL"].value
    clip_handle  = loader.outputs["CLIP"].value
    vae_handle   = loader.outputs["VAE"].value

    # ── 2. Encode positive prompt ─────────────────────────────────────────────
    print(f"\n[2/6] Encoding prompts …")
    pos_enc = Node.create_node("pos_enc", "CLIPTextEncode")
    pos_enc.inputs["CLIP"].value = clip_handle
    pos_enc.inputs["text"].value = args.prompt
    result = await pos_enc.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] CLIPTextEncode (positive) failed: {pos_enc.outputs['error'].value}")

    neg_enc = Node.create_node("neg_enc", "CLIPTextEncode")
    neg_enc.inputs["CLIP"].value = clip_handle
    neg_enc.inputs["text"].value = args.negative
    result = await neg_enc.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] CLIPTextEncode (negative) failed: {neg_enc.outputs['error'].value}")

    positive    = pos_enc.outputs["CONDITIONING"].value
    negative    = neg_enc.outputs["CONDITIONING"].value

    # ── 3. Empty latent ───────────────────────────────────────────────────────
    print(f"\n[3/6] Creating empty latent ({args.width}×{args.height}) …")
    latent_node = Node.create_node("latent", "EmptyLatentImage")
    latent_node.inputs["width"].value      = args.width
    latent_node.inputs["height"].value     = args.height
    latent_node.inputs["batch_size"].value = 1
    result = await latent_node.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] EmptyLatentImage failed: {latent_node.outputs['error'].value}")

    latent = latent_node.outputs["LATENT"].value

    # ── 4. KSampler ───────────────────────────────────────────────────────────
    print(f"\n[4/6] Sampling ({args.steps} steps, sampler={args.sampler}, "
          f"scheduler={'karras' if args.karras else 'normal'}) …")
    t0 = time.perf_counter()
    sampler = Node.create_node("sampler", "KSampler")
    sampler.inputs["MODEL"].value        = model_handle
    sampler.inputs["positive"].value     = positive
    sampler.inputs["negative"].value     = negative
    sampler.inputs["latent_image"].value = latent
    sampler.inputs["seed"].value         = args.seed
    sampler.inputs["steps"].value        = args.steps
    sampler.inputs["cfg"].value          = args.cfg
    sampler.inputs["sampler_name"].value = args.sampler
    sampler.inputs["scheduler"].value    = "karras" if args.karras else "normal"
    sampler.inputs["denoise"].value      = 1.0
    result = await sampler.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] KSampler failed: {sampler.outputs['error'].value}")
    print(f"      done in {time.perf_counter() - t0:.1f}s")

    sampled_latent = sampler.outputs["LATENT"].value

    # ── 5. VAE decode ─────────────────────────────────────────────────────────
    print(f"\n[5/6] Decoding latent …")
    t0 = time.perf_counter()
    decoder = Node.create_node("decoder", "VAEDecode")
    decoder.inputs["VAE"].value     = vae_handle
    decoder.inputs["samples"].value = sampled_latent
    result = await decoder.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] VAEDecode failed: {decoder.outputs['error'].value}")
    print(f"      done in {time.perf_counter() - t0:.1f}s")

    image = decoder.outputs["IMAGE"].value

    # ── 6. Save ───────────────────────────────────────────────────────────────
    print(f"\n[6/6] Saving image …")
    saver = Node.create_node("saver", "SaveImage")
    saver.inputs["images"].value          = image
    saver.inputs["filename_prefix"].value = args.prefix
    saver.inputs["output_dir"].value      = args.out
    result = await saver.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(f"[ERROR] SaveImage failed: {saver.outputs['error'].value}")

    saved_path = saver.outputs["saved_path"].value
    print(f"\n✓ Image saved to: {saved_path}")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="txt2img smoke-test via NodeGraph imaging nodes")
    p.add_argument("--model",    required=True,
                   help="Path to .safetensors/.ckpt file, diffusers directory, or HF Hub ID")
    p.add_argument("--prompt",   default="a photo of a shiba inu on a snowy mountain, "
                                         "high quality, detailed, 8k",
                   help="Positive prompt")
    p.add_argument("--negative", default="blurry, low quality, watermark, ugly, deformed",
                   help="Negative prompt")
    p.add_argument("--steps",    type=int,   default=20)
    p.add_argument("--cfg",      type=float, default=7.5)
    p.add_argument("--width",    type=int,   default=512)
    p.add_argument("--height",   type=int,   default=512)
    p.add_argument("--seed",     type=int,   default=42)
    p.add_argument("--sampler",  default="euler",
                   choices=["euler", "euler_ancestral", "heun", "dpm_2",
                            "dpm_2_ancestral", "lms", "dpmpp_2m",
                            "dpmpp_sde", "ddim", "pndm"])
    p.add_argument("--karras",   action="store_true",
                   help="Enable Karras sigmas for the scheduler")
    p.add_argument("--dtype",    default="float16", choices=["float32", "float16"])
    p.add_argument("--device",   default=None,
                   help="Force device: cpu | cuda | mps (auto-detected if omitted)")
    p.add_argument("--out",      default="./output", help="Output directory")
    p.add_argument("--prefix",   default="txt2img",  help="Filename prefix")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()
    asyncio.run(run(args))
