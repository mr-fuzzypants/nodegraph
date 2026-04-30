#!/usr/bin/env python3
"""
run_img2img_reference_mac.py — reference-guided img2img example.

Pipeline overview
-----------------
This script demonstrates the three new imaging nodes in a single workflow:

    LoadImage ──► ResizeImage ──► VAEEncode ──► ReferenceLatent
                                                      │
    CheckpointLoader ──CLIP──► CLIPTextEncode (pos)   │
                     ──CLIP──► CLIPTextEncode (neg)   │
                     ──MODEL──────────────────────────┼──► KSampler
                     ──VAE──► VAEEncode               │
                                                      ▼
    EmptyLatentImage ──────────────────────────► KSampler ──► VAEDecode ──► SaveImage

Step-by-step:
    1.  Load a reference image from disk (LoadImage).
    2.  Resize it to match the target latent resolution (ResizeImage).
    3.  Encode the resized reference into latent space (VAEEncode).
    4.  Annotate the positive CLIP conditioning with the reference latent
        (ReferenceLatent) so the sampler can use it for guidance.
    5.  Sample from an empty latent, guided by both text prompt and
        reference-latent conditioning (KSampler).
    6.  Decode the output latent to a pixel image (VAEDecode).
    7.  Save the result to disk (SaveImage).

Usage
-----
    python python/test/run_img2img_reference_mac.py \\
        --model  /path/to/model.safetensors \\
        --image  /path/to/reference.png \\
        --prompt "a futuristic city at sunset, cinematic lighting" \\
        --negative "blurry, watermark, low quality" \\
        --width  512 --height 512 \\
        --steps  25 --cfg 7.5 --seed 42 \\
        --interpolation lanczos \\
        --out ./output

Prerequisites
-------------
    pip install torch diffusers transformers accelerate safetensors Pillow numpy

For MPS (Apple Silicon) torch must be >= 2.0:
    pip install --upgrade torch

License
-------
This file is original work released under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

# ── Make the workspace importable from any cwd ───────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# ── Register all imaging nodes (including the new ones) ─────────────────────
import nodegraph.python.noderegistry.imaging  # noqa: F401  — side-effect: registers nodes


# ── Device / dtype helpers ───────────────────────────────────────────────────

def _detect_device(requested: str | None) -> str:
    """Return the best available torch device, preferring MPS on Apple Silicon."""
    try:
        import torch  # type: ignore
    except ImportError:
        raise SystemExit("torch is not installed.  Run: pip install torch")

    if requested:
        return requested

    if torch.backends.mps.is_available():
        print("[device] Apple MPS (Metal) — using GPU acceleration.")
        return "mps"
    if torch.cuda.is_available():
        print("[device] CUDA detected.")
        return "cuda"
    print("[device] No GPU — running on CPU (will be slow).")
    return "cpu"


def _safe_dtype(device: str, requested: str) -> str:
    """Downgrade float16 to float32 on CPU to avoid precision artefacts."""
    if device == "cpu" and requested == "float16":
        print("[dtype] CPU detected — overriding float16 → float32.")
        return "float32"
    return requested


# ── Minimal execution context ────────────────────────────────────────────────

class _Ctx:
    """
    Lightweight stand-in for a full NodeGraph ExecutionContext.

    Carries only the backend handle that imaging nodes read via
    ``executionContext.env.backend`` (Option-B architecture).
    The ``env`` attribute is ``self`` so that nodes using either
    ``env.backend`` or ``executionContext.env.backend`` both work.
    """

    def __init__(self, backend):
        self.backend = backend
        self.env     = self   # nodes access either ctx.backend or ctx.env.backend

    async def report_detail(self, detail: dict) -> None:
        """
        Receive preview payloads from nodes.

        In a real server this would push the data-URL over a WebSocket.
        Here we just note when a preview is available so the user can see
        the pipeline is working.
        """
        url = detail.get("url")
        if url:
            print(f"      [preview] inline PNG ready ({len(url)} bytes)")


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> None:
    from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend
    from nodegraph.python.core.Node import Node

    device = _detect_device(args.device)
    dtype  = _safe_dtype(device, args.dtype)

    print(
        f"[config] device={device}  dtype={dtype}  "
        f"steps={args.steps}  cfg={args.cfg}  seed={args.seed}  "
        f"size={args.width}×{args.height}  interp={args.interpolation}"
    )

    # Build the backend — SafetensorsBackend never constructs a full
    # StableDiffusionPipeline; each component is loaded individually.
    backend = SafetensorsBackend(
        device=device,
        dtype=dtype,
        scheduler_config={"use_karras_sigmas": True} if args.karras else {},
    )
    ctx = _Ctx(backend)

    # ── Step 1 · Load reference image ────────────────────────────────────────
    print(f"\n[1/8] Loading reference image: {args.image}")
    loader = Node.create_node("ref_loader", "LoadImage")
    loader.inputs["image_path"].value = args.image
    result = await loader.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] LoadImage failed: {loader.outputs['error'].value}"
        )
    ref_image = loader.outputs["IMAGE"].value
    print(f"      loaded  (preview emitted ↑)")

    # ── Step 2 · Resize reference to match target resolution ─────────────────
    # The reference must be the same spatial size as the target latent so that
    # VAEEncode produces a latent with the correct shape for KSampler.
    print(f"\n[2/8] Resizing reference to {args.width}×{args.height} "
          f"(filter: {args.interpolation}) …")
    resizer = Node.create_node("resizer", "ResizeImage")
    resizer.inputs["image"].value         = ref_image
    resizer.inputs["width"].value         = args.width
    resizer.inputs["height"].value        = args.height
    resizer.inputs["interpolation"].value = args.interpolation
    result = await resizer.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] ResizeImage failed: {resizer.outputs['error'].value}"
        )
    resized_ref = resizer.outputs["IMAGE"].value
    print(f"      resized (preview emitted ↑)")

    # ── Step 3 · Load model checkpoint ───────────────────────────────────────
    print(f"\n[3/8] Loading checkpoint: {args.model}")
    t0 = time.perf_counter()
    ckpt_loader = Node.create_node("ckpt", "CheckpointLoader")
    ckpt_loader.inputs["ckpt_path"].value = args.model
    result = await ckpt_loader.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] CheckpointLoader failed: {ckpt_loader.outputs['error'].value}"
        )
    print(f"      done in {time.perf_counter() - t0:.1f}s")

    model_handle = ckpt_loader.outputs["MODEL"].value
    clip_handle  = ckpt_loader.outputs["CLIP"].value
    vae_handle   = ckpt_loader.outputs["VAE"].value

    # ── Step 4 · Encode reference image into latent space ────────────────────
    # This gives the ReferenceLatent node the latent it will inject into the
    # conditioning so the sampler can use it as a structural/style reference.
    print(f"\n[4/8] Encoding reference image into latent space …")
    t0 = time.perf_counter()
    vae_enc = Node.create_node("vae_enc", "VAEEncode")
    vae_enc.inputs["VAE"].value    = vae_handle
    vae_enc.inputs["pixels"].value = resized_ref
    result = await vae_enc.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] VAEEncode failed: {vae_enc.outputs['error'].value}"
        )
    ref_latent = vae_enc.outputs["LATENT"].value
    print(f"      done in {time.perf_counter() - t0:.1f}s")

    # ── Step 5 · Encode text prompts ─────────────────────────────────────────
    print(f"\n[5/8] Encoding prompts …")
    print(f"      positive: {args.prompt}")
    print(f"      negative: {args.negative}")

    pos_enc = Node.create_node("pos_enc", "CLIPTextEncode")
    pos_enc.inputs["CLIP"].value = clip_handle
    pos_enc.inputs["text"].value = args.prompt
    result = await pos_enc.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] CLIPTextEncode (positive) failed: {pos_enc.outputs['error'].value}"
        )
    positive_cond = pos_enc.outputs["CONDITIONING"].value

    neg_enc = Node.create_node("neg_enc", "CLIPTextEncode")
    neg_enc.inputs["CLIP"].value = clip_handle
    neg_enc.inputs["text"].value = args.negative
    result = await neg_enc.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] CLIPTextEncode (negative) failed: {neg_enc.outputs['error'].value}"
        )
    negative_cond = neg_enc.outputs["CONDITIONING"].value

    # ── Step 6 · Annotate positive conditioning with reference latent ─────────
    # ReferenceLatent injects {"reference_latent": ref_latent} into every
    # conditioning entry's extras dict.  Backends that support reference-only
    # attention will read this key during the UNet forward pass.
    print(f"\n[6/8] Injecting reference latent into conditioning …")
    ref_node = Node.create_node("ref_latent", "ReferenceLatent")
    ref_node.inputs["conditioning"].value = positive_cond
    ref_node.inputs["latent"].value       = ref_latent
    result = await ref_node.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] ReferenceLatent failed: {ref_node.outputs['error'].value}"
        )
    # Use the annotated conditioning as the positive input for sampling.
    positive_with_ref = ref_node.outputs["CONDITIONING"].value
    print(f"      conditioning annotated with reference_latent key")

    # ── Step 7 · Create empty latent and sample ───────────────────────────────
    # We start from an empty (Gaussian noise) latent rather than from the
    # reference latent directly, so the output is a new image *influenced by*
    # the reference rather than a noisy reconstruction of it.
    print(f"\n[7/8] Creating empty latent and sampling "
          f"({args.steps} steps, cfg={args.cfg}, seed={args.seed}) …")
    latent_node = Node.create_node("empty_lat", "EmptyLatentImage")
    latent_node.inputs["width"].value      = args.width
    latent_node.inputs["height"].value     = args.height
    latent_node.inputs["batch_size"].value = 1
    result = await latent_node.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] EmptyLatentImage failed: {latent_node.outputs['error'].value}"
        )
    empty_latent = latent_node.outputs["LATENT"].value

    t0 = time.perf_counter()
    sampler = Node.create_node("sampler", "KSampler")
    sampler.inputs["MODEL"].value        = model_handle
    sampler.inputs["positive"].value     = positive_with_ref   # ← reference-annotated
    sampler.inputs["negative"].value     = negative_cond
    sampler.inputs["latent_image"].value = empty_latent
    sampler.inputs["seed"].value         = args.seed
    sampler.inputs["steps"].value        = args.steps
    sampler.inputs["cfg"].value          = args.cfg
    sampler.inputs["sampler_name"].value = args.sampler
    sampler.inputs["scheduler"].value    = "karras" if args.karras else "normal"
    sampler.inputs["denoise"].value      = 1.0
    result = await sampler.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] KSampler failed: {sampler.outputs['error'].value}"
        )
    print(f"      done in {time.perf_counter() - t0:.1f}s")
    sampled_latent = sampler.outputs["LATENT"].value

    # ── Step 8 · Decode and save ──────────────────────────────────────────────
    print(f"\n[8/8] Decoding latent and saving …")
    t0 = time.perf_counter()
    decoder = Node.create_node("decoder", "VAEDecode")
    decoder.inputs["VAE"].value     = vae_handle
    decoder.inputs["samples"].value = sampled_latent
    result = await decoder.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] VAEDecode failed: {decoder.outputs['error'].value}"
        )
    print(f"      decoded in {time.perf_counter() - t0:.1f}s  (preview emitted ↑)")

    output_image = decoder.outputs["IMAGE"].value

    saver = Node.create_node("saver", "SaveImage")
    saver.inputs["images"].value          = output_image
    saver.inputs["filename_prefix"].value = args.prefix
    saver.inputs["output_dir"].value      = args.out
    result = await saver.compute(ctx)
    if result.control_outputs.get("failed"):
        raise SystemExit(
            f"[ERROR] SaveImage failed: {saver.outputs['error'].value}"
        )

    saved_path = saver.outputs["saved_path"].value
    print(f"\n✓ Image saved to: {saved_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Reference-guided txt2img using LoadImage + ResizeImage + "
            "ReferenceLatent nodes."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Required
    p.add_argument("--model",  required=True,
                   help="Path to .safetensors/.ckpt or diffusers directory / HF Hub ID.")
    p.add_argument("--image",  required=True,
                   help="Path to the reference image (PNG, JPEG, WEBP, …).")

    # Prompt
    p.add_argument("--prompt",   default="a beautiful landscape, high detail, 8k",
                   help="Positive text prompt.")
    p.add_argument("--negative", default="blurry, low quality, watermark, distorted",
                   help="Negative text prompt.")

    # Resolution
    p.add_argument("--width",  type=int, default=512, help="Output width in pixels.")
    p.add_argument("--height", type=int, default=512, help="Output height in pixels.")

    # Resize interpolation for the reference image
    p.add_argument(
        "--interpolation",
        default="lanczos",
        choices=["none", "nearest", "bilinear", "bicubic", "lanczos", "box", "hamming"],
        help="Resampling filter used to resize the reference image.",
    )

    # Sampler
    p.add_argument("--steps",   type=int,   default=25,      help="Denoising steps.")
    p.add_argument("--cfg",     type=float, default=7.5,     help="Classifier-free guidance scale.")
    p.add_argument("--seed",    type=int,   default=42,      help="Random seed.")
    p.add_argument("--sampler", default="euler",
                   choices=["euler", "euler_ancestral", "heun", "dpm_2",
                            "dpm_2_ancestral", "lms", "dpmpp_2m",
                            "dpmpp_sde", "ddim", "pndm"],
                   help="Sampling algorithm.")
    p.add_argument("--karras",  action="store_true",
                   help="Enable Karras sigma schedule.")

    # Hardware
    p.add_argument("--device", default=None,
                   help="Force a specific torch device (cuda / mps / cpu).")
    p.add_argument("--dtype",  default="float16",
                   choices=["float32", "float16"],
                   help="Tensor dtype (float16 recommended on GPU/MPS).")

    # Output
    p.add_argument("--out",    default="./output",   help="Output directory.")
    p.add_argument("--prefix", default="ref_guided", help="Filename prefix for saved images.")

    return p


if __name__ == "__main__":
    parser = _build_parser()
    args   = parser.parse_args()
    asyncio.run(run(args))
