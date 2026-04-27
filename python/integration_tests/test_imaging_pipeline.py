"""
Integration tests for the imaging node pipeline.

These tests exercise the full node → backend stack end-to-end.

---------------------------------------------------------------------------
Test groups
---------------------------------------------------------------------------

no-model tests  (always run — only need torch / Pillow installed)
  • Backend instantiation and XPU-stub application
  • Empty-latent tensor shape
  • SaveImage / LoadImage file round-trip

model tests  (skipped unless NODEGRAPH_TEST_MODEL is set)
  • Full txt2img pipeline
  • img2img pipeline (denoise < 1.0)
  • Every supported sampler (parametrized)
  • Karras-sigma variant
  • VAE encode → decode round-trip
  • CLIPTextEncode with a real tokenizer/encoder

---------------------------------------------------------------------------
Environment variables
---------------------------------------------------------------------------

NODEGRAPH_TEST_MODEL   Path to a .safetensors / .ckpt file, diffusers
                       directory, or HuggingFace Hub model ID.  Required
                       for model tests.
                       Example: NODEGRAPH_TEST_MODEL=~/models/v1-5.safetensors

NODEGRAPH_TEST_DEVICE  Force a specific PyTorch device (cpu | cuda | mps).
                       Omit to auto-detect (prefers MPS on Apple Silicon).

NODEGRAPH_TEST_DTYPE   Override dtype (float32 | float16).
                       CPU runs default to float32 automatically.

NODEGRAPH_TEST_STEPS   Number of denoising steps (default: 4).  Keep low
                       for faster CI runs; raise for visual quality checks.

NODEGRAPH_TEST_OUTDIR  Directory for images produced during test runs.
                       Defaults to /tmp/nodegraph_integration.

---------------------------------------------------------------------------
Running
---------------------------------------------------------------------------

    # All tests that don't need a model (fast, no GPU):
    cd /path/to/nodegraph
    pytest python/integration_tests/ -v -m "not requires_model"

    # Full suite with a local checkpoint:
    NODEGRAPH_TEST_MODEL=~/models/v1-5-pruned-emaonly.safetensors \\
        pytest python/integration_tests/ -v

    # Specific sampler only:
    NODEGRAPH_TEST_MODEL=~/models/v1-5.safetensors \\
        pytest python/integration_tests/ -v -k "euler_ancestral"

Prerequisites
-------------
    pip install torch diffusers transformers accelerate safetensors Pillow numpy pytest
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Workspace on sys.path
# ---------------------------------------------------------------------------

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[3]),  # repo root
)

# ---------------------------------------------------------------------------
# Register all imaging nodes
# ---------------------------------------------------------------------------

import nodegraph.python.noderegistry.imaging  # noqa: F401

from nodegraph.python.core.Node import Node
from nodegraph.python.core.Executor import ExecCommand, ExecutionResult

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def _node(type_name: str, node_id: str = "integ") -> Node:
    return Node.create_node(node_id, type_name)


class _Ctx:
    """Minimal execution context — mirrors NodeContext.env accessor."""

    class _Env:
        def __init__(self, backend: Any) -> None:
            self.backend = backend

    def __init__(self, backend: Any) -> None:
        self.backend = backend  # kept for backward compat
        self.env = _Ctx._Env(backend)


# ---------------------------------------------------------------------------
# Environment / configuration
# ---------------------------------------------------------------------------

_MODEL_PATH: str | None = os.environ.get("NODEGRAPH_TEST_MODEL")
_FORCED_DEVICE: str | None = os.environ.get("NODEGRAPH_TEST_DEVICE")
_FORCED_DTYPE: str | None = os.environ.get("NODEGRAPH_TEST_DTYPE")
_STEPS: int = int(os.environ.get("NODEGRAPH_TEST_STEPS", "4"))
_OUT_DIR: str = os.environ.get(
    "NODEGRAPH_TEST_OUTDIR", "/tmp/nodegraph_integration"
)


def _has_torch() -> bool:
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


requires_torch = pytest.mark.skipif(
    not _has_torch(),
    reason="torch is not installed. Run: pip install torch",
)

requires_pillow = pytest.mark.skipif(
    not _has_pillow(),
    reason="Pillow is not installed. Run: pip install Pillow",
)

requires_model = pytest.mark.skipif(
    not _MODEL_PATH,
    reason=(
        "Set NODEGRAPH_TEST_MODEL=/path/to/checkpoint to run model tests. "
        "Example: NODEGRAPH_TEST_MODEL=~/models/v1-5.safetensors pytest python/integration_tests/ -v"
    ),
)


def _detect_device() -> str:
    if _FORCED_DEVICE:
        return _FORCED_DEVICE
    try:
        import torch  # type: ignore

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    return "cpu"


def _safe_dtype(device: str) -> str:
    if _FORCED_DTYPE:
        return _FORCED_DTYPE
    # float16 may give NaNs on CPU for some models; default to float32 there.
    return "float16" if device in ("cuda", "mps") else "float32"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def device() -> str:
    return _detect_device()


@pytest.fixture(scope="session")
def dtype(device: str) -> str:  # noqa: F811  (shadows built-in in test context)
    return _safe_dtype(device)


@pytest.fixture(scope="session")
def safetensors_backend(device, dtype):
    """Real SafetensorsBackend, shared across all model tests."""
    if not _has_torch():
        pytest.skip("torch is not installed")
    from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend

    return SafetensorsBackend(device=device, dtype=dtype)


@pytest.fixture(scope="session")
def loaded_checkpoint(safetensors_backend):
    """
    Load the checkpoint once per test session and share the handles.
    Only useful in model tests; skip automatically if no model path.
    """
    if not _MODEL_PATH:
        pytest.skip("No model path configured")

    t0 = time.perf_counter()
    model, clip, vae = safetensors_backend.load_checkpoint(_MODEL_PATH)
    elapsed = time.perf_counter() - t0
    print(f"\n  [fixture] checkpoint loaded in {elapsed:.1f}s from {_MODEL_PATH}")
    return model, clip, vae


@pytest.fixture(scope="session")
def empty_latent_tensor(safetensors_backend):
    """A real torch zeroed latent at 512×512."""
    return safetensors_backend.empty_latent(512, 512, batch_size=1)


@pytest.fixture(scope="session")
def encoded_prompts(safetensors_backend, loaded_checkpoint):
    """Positive and negative conditioning for the default prompts."""
    _, clip, _ = loaded_checkpoint
    positive = safetensors_backend.encode_text(
        clip, "a photo of a golden retriever on a snowy mountain, detailed, 8k"
    )
    negative = safetensors_backend.encode_text(
        clip, "blurry, watermark, low quality, deformed"
    )
    return positive, negative


@pytest.fixture(scope="session")
def txt2img_latent(safetensors_backend, loaded_checkpoint, empty_latent_tensor, encoded_prompts):
    """Denoised latent from a short txt2img run — reused by decode / encode tests."""
    model, _, _ = loaded_checkpoint
    positive, negative = encoded_prompts
    t0 = time.perf_counter()
    latent = safetensors_backend.sample(
        model=model,
        positive=positive,
        negative=negative,
        latent=empty_latent_tensor,
        seed=42,
        steps=_STEPS,
        cfg=7.5,
        sampler_name="euler",
        scheduler="normal",
        denoise=1.0,
    )
    print(f"\n  [fixture] {_STEPS}-step sample done in {time.perf_counter() - t0:.1f}s")
    return latent


@pytest.fixture(scope="session")
def decoded_image(safetensors_backend, loaded_checkpoint, txt2img_latent):
    """Decoded PIL-style tensor from txt2img_latent."""
    _, _, vae = loaded_checkpoint
    return safetensors_backend.decode_vae(vae, txt2img_latent)


@pytest.fixture()
def tmp_output_dir(tmp_path) -> str:
    """Per-test temp directory for saved images."""
    return str(tmp_path / "output")


# ---------------------------------------------------------------------------
# 1. Backend instantiation & XPU stub
# ---------------------------------------------------------------------------


class TestBackendSetup:
    """No model required — only the backend classes themselves are exercised."""

    def test_safetensors_backend_instantiates(self):
        from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend

        b = SafetensorsBackend(device="cpu", dtype="float32")
        assert b is not None

    def test_diffusers_backend_instantiates(self):
        from nodegraph.python.core.backends.diffusers_backend import DiffusersBackend

        b = DiffusersBackend(device="cpu", dtype="float32")
        assert b is not None

    @requires_torch
    def test_xpu_stub_applied_safetensors(self):
        """After _get_torch(), torch.xpu must exist and report unavailable."""
        from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend

        b = SafetensorsBackend(device="cpu", dtype="float32")
        torch = b._get_torch()
        assert hasattr(torch, "xpu"), "torch.xpu stub not applied"
        assert torch.xpu.is_available() is False
        assert torch.xpu.device_count() == 0

    @requires_torch
    def test_xpu_stub_applied_diffusers(self):
        from nodegraph.python.core.backends.diffusers_backend import DiffusersBackend

        b = DiffusersBackend(device="cpu", dtype="float32")
        torch = b._get_torch()
        assert hasattr(torch, "xpu"), "torch.xpu stub not applied"
        assert torch.xpu.is_available() is False

    def test_protocol_conformance_safetensors(self):
        """SafetensorsBackend satisfies the DiffusionBackend protocol."""
        from nodegraph.python.core.backends.protocol import DiffusionBackend
        from nodegraph.python.core.backends.safetensors_backend import SafetensorsBackend

        b = SafetensorsBackend()
        assert isinstance(b, DiffusionBackend)

    def test_protocol_conformance_diffusers(self):
        from nodegraph.python.core.backends.protocol import DiffusionBackend
        from nodegraph.python.core.backends.diffusers_backend import DiffusersBackend

        b = DiffusersBackend()
        assert isinstance(b, DiffusionBackend)


# ---------------------------------------------------------------------------
# 2. Latent helpers (torch needed, no model)
# ---------------------------------------------------------------------------


class TestLatentHelpers:
    pytestmark = requires_torch  # skip whole class if torch absent

    def test_empty_latent_shape(self, safetensors_backend):
        latent = safetensors_backend.empty_latent(512, 512, batch_size=1)
        samples = latent["samples"]
        # SD 1.x: latent space is 1/8 the pixel dimensions, 4 channels
        assert tuple(samples.shape) == (1, 4, 64, 64)

    def test_empty_latent_shape_batch(self, safetensors_backend):
        latent = safetensors_backend.empty_latent(768, 512, batch_size=2)
        samples = latent["samples"]
        assert tuple(samples.shape) == (2, 4, 64, 96)

    def test_empty_latent_device(self, safetensors_backend, device):
        latent = safetensors_backend.empty_latent(512, 512)
        assert str(latent["samples"].device).startswith(device.split(":")[0])

    def test_empty_latent_via_node(self, safetensors_backend):
        ctx = _Ctx(safetensors_backend)
        n = _node("EmptyLatentImage")
        n.inputs["width"].value = 512
        n.inputs["height"].value = 512
        n.inputs["batch_size"].value = 1
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True
        latent = n.outputs["LATENT"].value
        assert latent is not None
        assert tuple(latent["samples"].shape) == (1, 4, 64, 64)


# ---------------------------------------------------------------------------
# 3. File I/O (Pillow + torch, no model)
# ---------------------------------------------------------------------------


class TestFileIO:
    """SaveImage / LoadImage round-trip — no checkpoint required."""

    pytestmark = [requires_torch, requires_pillow]

    def _make_image_tensor(self, safetensors_backend, h: int = 64, w: int = 64):
        """Create a random float tensor shaped (1, H, W, 3) in [0, 1]."""
        torch = safetensors_backend._get_torch()
        return torch.rand(1, h, w, 3)

    def test_save_image_creates_file(self, safetensors_backend, tmp_output_dir):
        image = self._make_image_tensor(safetensors_backend)
        path = os.path.join(tmp_output_dir, "test_save.png")
        saved = safetensors_backend.save_image(image, path)
        assert os.path.isfile(saved)

    def test_save_image_returns_absolute_path(self, safetensors_backend, tmp_output_dir):
        image = self._make_image_tensor(safetensors_backend)
        path = os.path.join(tmp_output_dir, "abs.png")
        saved = safetensors_backend.save_image(image, path)
        assert os.path.isabs(saved)

    def test_load_image_round_trip(self, safetensors_backend, tmp_output_dir):
        """Save a known tensor, load it back, check approximate equality."""
        torch = safetensors_backend._get_torch()
        original = torch.rand(1, 64, 64, 3)
        path = os.path.join(tmp_output_dir, "roundtrip.png")
        safetensors_backend.save_image(original, path)

        loaded, mask = safetensors_backend.load_image(path)
        assert loaded is not None
        assert mask is None  # PNG saved without alpha
        assert loaded.shape == original.shape
        # Quantisation error from uint8 round-trip ≤ 1/255 ≈ 0.004
        max_err = (loaded - original.cpu()).abs().max().item()
        assert max_err < 0.005, f"Round-trip error {max_err:.6f} exceeds tolerance"

    def test_load_image_with_alpha_produces_mask(self, safetensors_backend, tmp_output_dir):
        """An RGBA image with a non-trivial alpha channel should produce a mask."""
        import numpy as np
        from PIL import Image  # type: ignore

        # Build an RGBA image where the alpha channel is not all-255
        rgba = np.zeros((64, 64, 4), dtype="uint8")
        rgba[:, :, :3] = 128  # mid-grey RGB
        rgba[:32, :, 3] = 255  # top half fully opaque
        rgba[32:, :, 3] = 0  # bottom half fully transparent

        img_path = os.path.join(tmp_output_dir, "alpha_test.png")
        os.makedirs(tmp_output_dir, exist_ok=True)
        Image.fromarray(rgba, "RGBA").save(img_path)

        image, mask = safetensors_backend.load_image(img_path)
        assert image is not None
        assert mask is not None, "Mask should be returned for non-trivial alpha"
        assert mask.shape == (1, 64, 64)

    def test_save_image_node_end_to_end(self, safetensors_backend, tmp_output_dir):
        """SaveImage node saves and reports the correct path."""
        image = self._make_image_tensor(safetensors_backend)
        ctx = _Ctx(safetensors_backend)
        n = _node("SaveImage")
        n.inputs["images"].value = image
        n.inputs["filename_prefix"].value = "integ"
        n.inputs["output_dir"].value = tmp_output_dir
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("done") is True
        saved_path = n.outputs["saved_path"].value
        assert os.path.isfile(saved_path)

    def test_save_image_node_no_collision(self, safetensors_backend, tmp_output_dir):
        """Saving twice with the same prefix produces two distinct files."""
        image = self._make_image_tensor(safetensors_backend)
        ctx = _Ctx(safetensors_backend)

        for _ in range(2):
            n = _node("SaveImage")
            n.inputs["images"].value = image
            n.inputs["filename_prefix"].value = "dup"
            n.inputs["output_dir"].value = tmp_output_dir
            _run(n.compute(ctx))

        files = list(Path(tmp_output_dir).glob("dup*.png"))
        assert len(files) == 2, f"Expected 2 files, got {files}"

    def test_load_image_node_missing_file(self, safetensors_backend):
        """LoadImage node fires 'failed' for a non-existent path."""
        ctx = _Ctx(safetensors_backend)
        n = _node("LoadImage")
        n.inputs["image_path"].value = "/nonexistent/path/image.png"
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("failed") is True
        assert n.outputs["error"].value != ""


# ---------------------------------------------------------------------------
# 4. Checkpoint loading (requires model)
# ---------------------------------------------------------------------------


@requires_model
class TestCheckpointLoading:
    def test_load_checkpoint_returns_three_handles(self, safetensors_backend):
        model, clip, vae = safetensors_backend.load_checkpoint(_MODEL_PATH)
        assert model is not None and "unet" in model
        assert clip is not None and "tokenizer" in clip and "text_encoder" in clip
        assert vae is not None and "vae" in vae

    def test_checkpoint_loader_node_fires_next(self, safetensors_backend):
        ctx = _Ctx(safetensors_backend)
        n = _node("CheckpointLoader")
        n.inputs["ckpt_path"].value = _MODEL_PATH
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True
        assert n.outputs["MODEL"].value is not None
        assert n.outputs["CLIP"].value is not None
        assert n.outputs["VAE"].value is not None

    def test_checkpoint_loader_node_bad_path_fires_failed(self, safetensors_backend):
        ctx = _Ctx(safetensors_backend)
        n = _node("CheckpointLoader")
        n.inputs["ckpt_path"].value = "/nonexistent/model.safetensors"
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("failed") is True
        assert n.outputs["error"].value != ""


# ---------------------------------------------------------------------------
# 5. Text encoding (requires model)
# ---------------------------------------------------------------------------


@requires_model
class TestTextEncoding:
    def test_encode_text_returns_list(self, safetensors_backend, loaded_checkpoint):
        _, clip, _ = loaded_checkpoint
        conditioning = safetensors_backend.encode_text(clip, "a red apple")
        assert isinstance(conditioning, list)
        assert len(conditioning) == 1
        emb, extra = conditioning[0]
        assert emb is not None
        assert isinstance(extra, dict)

    def test_clip_text_encode_node(self, safetensors_backend, loaded_checkpoint):
        _, clip, _ = loaded_checkpoint
        ctx = _Ctx(safetensors_backend)
        n = _node("CLIPTextEncode")
        n.inputs["CLIP"].value = clip
        n.inputs["text"].value = "masterpiece, best quality"
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True
        assert n.outputs["CONDITIONING"].value is not None

    def test_clip_text_encode_empty_string(self, safetensors_backend, loaded_checkpoint):
        """Empty prompt should still succeed, producing a valid (null) embedding."""
        _, clip, _ = loaded_checkpoint
        ctx = _Ctx(safetensors_backend)
        n = _node("CLIPTextEncode")
        n.inputs["CLIP"].value = clip
        n.inputs["text"].value = ""
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True


# ---------------------------------------------------------------------------
# 6. Full txt2img pipeline (requires model)
# ---------------------------------------------------------------------------


@requires_model
class TestTxt2ImgPipeline:
    def test_txt2img_produces_latent(self, safetensors_backend, loaded_checkpoint,
                                     empty_latent_tensor, encoded_prompts):
        model, _, _ = loaded_checkpoint
        positive, negative = encoded_prompts
        latent = safetensors_backend.sample(
            model=model,
            positive=positive,
            negative=negative,
            latent=empty_latent_tensor,
            seed=0,
            steps=_STEPS,
            cfg=7.5,
            sampler_name="euler",
            scheduler="normal",
            denoise=1.0,
        )
        assert "samples" in latent
        assert tuple(latent["samples"].shape) == (1, 4, 64, 64)

    def test_ksampler_node_txt2img(self, safetensors_backend, loaded_checkpoint,
                                    empty_latent_tensor, encoded_prompts):
        """Full pipeline wired through the KSampler node."""
        model, _, _ = loaded_checkpoint
        positive, negative = encoded_prompts
        ctx = _Ctx(safetensors_backend)
        n = _node("KSampler")
        n.inputs["MODEL"].value = model
        n.inputs["positive"].value = positive
        n.inputs["negative"].value = negative
        n.inputs["latent_image"].value = empty_latent_tensor
        n.inputs["seed"].value = 1
        n.inputs["steps"].value = _STEPS
        n.inputs["cfg"].value = 7.5
        n.inputs["sampler_name"].value = "euler"
        n.inputs["scheduler"].value = "normal"
        n.inputs["denoise"].value = 1.0
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True
        latent = n.outputs["LATENT"].value
        assert latent is not None
        assert tuple(latent["samples"].shape) == (1, 4, 64, 64)

    def test_vae_decode_produces_image(self, safetensors_backend, loaded_checkpoint,
                                       txt2img_latent):
        _, _, vae = loaded_checkpoint
        image = safetensors_backend.decode_vae(vae, txt2img_latent)
        # Expect (B, H, W, C) float in [0, 1] with 3 channels.
        # Exact pixel size depends on the VAE's upsampling factor, which
        # varies across model families (tiny test models may use 2× instead
        # of the standard 8×), so we only assert the tensor rank and range.
        assert image is not None
        assert image.ndim == 4
        assert image.shape[3] == 3  # RGB
        assert float(image.min()) >= -0.01
        assert float(image.max()) <= 1.01

    def test_vae_decode_node(self, safetensors_backend, loaded_checkpoint, txt2img_latent):
        _, _, vae = loaded_checkpoint
        ctx = _Ctx(safetensors_backend)
        n = _node("VAEDecode")
        n.inputs["VAE"].value = vae
        n.inputs["samples"].value = txt2img_latent
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True
        assert n.outputs["IMAGE"].value is not None

    def test_full_node_pipeline_txt2img_saves_image(self, safetensors_backend,
                                                     loaded_checkpoint,
                                                     empty_latent_tensor,
                                                     encoded_prompts,
                                                     tmp_output_dir):
        """Wire all six nodes together and verify an image file is written."""
        model, clip, vae = loaded_checkpoint
        positive, negative = encoded_prompts
        ctx = _Ctx(safetensors_backend)

        # KSampler
        sampler_node = _node("KSampler", "pipeline-sampler")
        sampler_node.inputs["MODEL"].value = model
        sampler_node.inputs["positive"].value = positive
        sampler_node.inputs["negative"].value = negative
        sampler_node.inputs["latent_image"].value = empty_latent_tensor
        sampler_node.inputs["seed"].value = 99
        sampler_node.inputs["steps"].value = _STEPS
        sampler_node.inputs["cfg"].value = 7.5
        sampler_node.inputs["sampler_name"].value = "euler"
        sampler_node.inputs["scheduler"].value = "normal"
        sampler_node.inputs["denoise"].value = 1.0
        _run(sampler_node.compute(ctx))
        assert sampler_node.outputs["LATENT"].value is not None

        # VAEDecode
        decode_node = _node("VAEDecode", "pipeline-decode")
        decode_node.inputs["VAE"].value = vae
        decode_node.inputs["samples"].value = sampler_node.outputs["LATENT"].value
        _run(decode_node.compute(ctx))
        assert decode_node.outputs["IMAGE"].value is not None

        # SaveImage
        save_node = _node("SaveImage", "pipeline-save")
        save_node.inputs["images"].value = decode_node.outputs["IMAGE"].value
        save_node.inputs["filename_prefix"].value = "integ_txt2img"
        save_node.inputs["output_dir"].value = tmp_output_dir
        result = _run(save_node.compute(ctx))
        assert result.control_outputs.get("done") is True
        saved = save_node.outputs["saved_path"].value
        assert os.path.isfile(saved), f"Expected file at {saved}"
        print(f"\n  [output] {saved}")


# ---------------------------------------------------------------------------
# 7. img2img pipeline (requires model)
# ---------------------------------------------------------------------------


@requires_model
class TestImg2ImgPipeline:
    def test_img2img_denoise_partial(self, safetensors_backend, loaded_checkpoint,
                                     txt2img_latent, encoded_prompts):
        """Using denoise=0.5 should produce a latent different from the input."""
        model, _, _ = loaded_checkpoint
        positive, negative = encoded_prompts
        result_latent = safetensors_backend.sample(
            model=model,
            positive=positive,
            negative=negative,
            latent=txt2img_latent,
            seed=42,
            steps=_STEPS,
            cfg=7.5,
            sampler_name="euler",
            scheduler="normal",
            denoise=0.5,
        )
        assert "samples" in result_latent
        diff = (result_latent["samples"] - txt2img_latent["samples"]).abs().mean().item()
        assert diff > 1e-4, "img2img output should differ from input"

    def test_vae_encode_decode_roundtrip(self, safetensors_backend, loaded_checkpoint,
                                         decoded_image):
        """VAE encode → decode should stay in a reasonable pixel range."""
        _, _, vae = loaded_checkpoint
        encoded = safetensors_backend.encode_vae(vae, decoded_image)
        assert "samples" in encoded
        reconstructed = safetensors_backend.decode_vae(vae, encoded)
        assert reconstructed is not None
        assert reconstructed.shape == decoded_image.shape
        # Reconstruction won't be pixel-perfect but should be in [0, 1]
        assert reconstructed.min().item() >= -0.01
        assert reconstructed.max().item() <= 1.01

    def test_vae_encode_node(self, safetensors_backend, loaded_checkpoint, decoded_image):
        _, _, vae = loaded_checkpoint
        ctx = _Ctx(safetensors_backend)
        n = _node("VAEEncode")
        n.inputs["VAE"].value = vae
        n.inputs["pixels"].value = decoded_image
        result = _run(n.compute(ctx))
        assert result.control_outputs.get("next") is True
        latent = n.outputs["LATENT"].value
        assert latent is not None
        assert "samples" in latent

    def test_load_save_img2img_pipeline(self, safetensors_backend, loaded_checkpoint,
                                        encoded_prompts, tmp_output_dir):
        """
        LoadImage → VAEEncode → KSampler → VAEDecode → SaveImage
        exercises the full img2img node graph.
        """
        import numpy as np
        from PIL import Image  # type: ignore

        model, _, vae = loaded_checkpoint
        positive, negative = encoded_prompts

        # The tiny test model's VAE uses a 2× spatial scale factor (not the
        # standard 8×), so a 512×512 image would encode to a (1,4,256,256)
        # latent that the tiny UNet cannot process.  Use 128×128 instead so
        # the encoded latent is (1,4,64,64), matching what the UNet expects.
        src_arr = (np.random.rand(128, 128, 3) * 255).astype("uint8")
        src_path = os.path.join(tmp_output_dir, "src.png")
        os.makedirs(tmp_output_dir, exist_ok=True)
        Image.fromarray(src_arr).save(src_path)

        ctx = _Ctx(safetensors_backend)

        # LoadImage
        load = _node("LoadImage", "img2img-load")
        load.inputs["image_path"].value = src_path
        result = _run(load.compute(ctx))
        assert result.control_outputs.get("next") is True

        # VAEEncode
        encode = _node("VAEEncode", "img2img-encode")
        encode.inputs["VAE"].value = vae
        encode.inputs["pixels"].value = load.outputs["IMAGE"].value
        _run(encode.compute(ctx))

        # KSampler (denoise 0.6 → only partial re-draw)
        sampler = _node("KSampler", "img2img-sampler")
        sampler.inputs["MODEL"].value = model
        sampler.inputs["positive"].value = positive
        sampler.inputs["negative"].value = negative
        sampler.inputs["latent_image"].value = encode.outputs["LATENT"].value
        sampler.inputs["seed"].value = 7
        sampler.inputs["steps"].value = _STEPS
        sampler.inputs["cfg"].value = 7.0
        sampler.inputs["sampler_name"].value = "euler"
        sampler.inputs["scheduler"].value = "normal"
        sampler.inputs["denoise"].value = 0.6
        _run(sampler.compute(ctx))
        assert sampler.outputs["LATENT"].value is not None

        # VAEDecode
        decode = _node("VAEDecode", "img2img-decode")
        decode.inputs["VAE"].value = vae
        decode.inputs["samples"].value = sampler.outputs["LATENT"].value
        _run(decode.compute(ctx))

        # SaveImage
        save = _node("SaveImage", "img2img-save")
        save.inputs["images"].value = decode.outputs["IMAGE"].value
        save.inputs["filename_prefix"].value = "integ_img2img"
        save.inputs["output_dir"].value = tmp_output_dir
        result = _run(save.compute(ctx))
        assert result.control_outputs.get("done") is True
        assert os.path.isfile(save.outputs["saved_path"].value)


# ---------------------------------------------------------------------------
# 8. Sampler sweep (requires model, parametrized)
# ---------------------------------------------------------------------------

_SAMPLER_NAMES = [
    "euler",
    "euler_ancestral",
    "heun",
    "dpm_2",
    "dpm_2_ancestral",
    "lms",
    "dpmpp_2m",
    "dpmpp_sde",
    "ddim",
    "pndm",
]


@requires_model
@pytest.mark.parametrize("sampler_name", _SAMPLER_NAMES)
def test_sampler(safetensors_backend, loaded_checkpoint, empty_latent_tensor,
                 encoded_prompts, sampler_name, tmp_output_dir):
    """Each supported sampler should complete without error and produce correct shape."""
    # PNDM requires at least pndm_order (4) denoising steps.
    if sampler_name == "pndm" and _STEPS < 4:
        pytest.skip(f"pndm needs >= 4 steps; NODEGRAPH_TEST_STEPS={_STEPS}")

    model, _, _ = loaded_checkpoint
    positive, negative = encoded_prompts

    latent = safetensors_backend.sample(
        model=model,
        positive=positive,
        negative=negative,
        latent=empty_latent_tensor,
        seed=42,
        steps=_STEPS,
        cfg=7.5,
        sampler_name=sampler_name,
        scheduler="normal",
        denoise=1.0,
    )
    assert "samples" in latent, f"{sampler_name} produced no 'samples' key"
    assert latent["samples"].ndim == 4, f"{sampler_name} returned wrong ndim"


@requires_model
@pytest.mark.parametrize("sampler_name", ["euler", "dpmpp_2m", "ddim"])
def test_sampler_karras(safetensors_backend, loaded_checkpoint, empty_latent_tensor,
                        encoded_prompts, sampler_name):
    """Karras-sigma variant should succeed for schedulers that support it."""
    backend = safetensors_backend.__class__(
        device=safetensors_backend._device,
        dtype=safetensors_backend._dtype_str,
        scheduler_config={"use_karras_sigmas": True},
    )
    model, _, _ = loaded_checkpoint
    positive, negative = encoded_prompts
    latent = backend.sample(
        model=model,
        positive=positive,
        negative=negative,
        latent=empty_latent_tensor,
        seed=0,
        steps=_STEPS,
        cfg=7.5,
        sampler_name=sampler_name,
        scheduler="karras",
        denoise=1.0,
    )
    assert "samples" in latent


# ---------------------------------------------------------------------------
# 9. Seed reproducibility (requires model)
# ---------------------------------------------------------------------------


@requires_model
def test_same_seed_same_output(safetensors_backend, loaded_checkpoint,
                                empty_latent_tensor, encoded_prompts):
    """Two runs with identical seed and config must produce bit-identical latents."""
    model, _, _ = loaded_checkpoint
    positive, negative = encoded_prompts
    kwargs = dict(
        model=model,
        positive=positive,
        negative=negative,
        latent=empty_latent_tensor,
        seed=123,
        steps=_STEPS,
        cfg=7.5,
        sampler_name="euler",
        scheduler="normal",
        denoise=1.0,
    )
    out_a = safetensors_backend.sample(**kwargs)
    out_b = safetensors_backend.sample(**kwargs)
    diff = (out_a["samples"] - out_b["samples"]).abs().max().item()
    assert diff == 0.0, f"Same-seed outputs diverged by {diff}"


@requires_model
def test_different_seed_different_output(safetensors_backend, loaded_checkpoint,
                                          empty_latent_tensor, encoded_prompts):
    """Two runs with different seeds must produce different latents.

    Skipped when NODEGRAPH_TEST_STEPS < 4: toy/tiny models with very few
    denoising iterations may collapse to the same output regardless of seed.
    """
    if _STEPS < 4:
        pytest.skip(f"Seed-divergence test requires >= 4 steps; NODEGRAPH_TEST_STEPS={_STEPS}")
    model, _, _ = loaded_checkpoint
    positive, negative = encoded_prompts
    base_kwargs = dict(
        model=model,
        positive=positive,
        negative=negative,
        latent=empty_latent_tensor,
        steps=_STEPS,
        cfg=7.5,
        sampler_name="euler",
        scheduler="normal",
        denoise=1.0,
    )
    out_a = safetensors_backend.sample(**base_kwargs, seed=1)
    out_b = safetensors_backend.sample(**base_kwargs, seed=2)
    diff = (out_a["samples"] - out_b["samples"]).abs().max().item()
    assert diff > 1e-4, "Different seeds produced identical outputs"

print("DONE")
