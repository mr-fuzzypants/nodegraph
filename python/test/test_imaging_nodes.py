"""
Unit tests for imaging nodes.

These tests use a lightweight mock backend — no torch, diffusers, or
safetensors installation required.  They verify:

  * Correct port construction (types, names, directions)
  * compute() returns the right ExecCommand and fires the right control output
  * Error path (backend raises) fires 'failed' and writes to the error port

Run with:
    cd /Users/robertpringle/development/nodegraph
    pytest python/test/test_imaging_nodes.py -v
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from typing import Any
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# ── Register imaging nodes ────────────────────────────────────────────────────
import nodegraph.python.noderegistry.imaging  # noqa: F401  triggers @Node.register calls

from nodegraph.python.core.Node import Node
from nodegraph.python.core.Executor import ExecCommand, ExecutionResult
from nodegraph.python.core.node_context import NodeContext, NodeEnvironment

# ── Shared helpers ────────────────────────────────────────────────────────────

class _Env:
    """Minimal NodeEnvironment carrying a mock backend (Option B)."""
    def __init__(self, backend: Any):
        self.backend = backend


class _CaptureEventBus:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


def _run(coro):
    return asyncio.run(coro)


def _node(type_name: str) -> Node:
    return Node.create_node("test-id", type_name)


# ─────────────────────────────────────────────────────────────────────────────
# Mock backend — returns plausible stub objects, never touches ML libs
# ─────────────────────────────────────────────────────────────────────────────

class _MockBackend:
    """
    Mock DiffusionBackend.  Returns simple Python objects so every node can
    exercise its compute() method without a GPU or installed ML libraries.
    """

    DUMMY_MODEL = {"unet": object(), "scheduler": object()}
    DUMMY_CLIP  = {"tokenizer": object(), "text_encoder": object()}
    DUMMY_VAE   = {"vae": object()}

    # Latent/image/conditioning use lists so we can inspect them
    DUMMY_LATENT = {"samples": [[[0.0] * 64] * 64] * 4}
    DUMMY_IMAGE  = [[[0.5, 0.5, 0.5]] * 512] * 512  # H×W×C list
    DUMMY_COND   = [([0.0] * 768, {})]

    def load_checkpoint(self, path):
        return self.DUMMY_MODEL, self.DUMMY_CLIP, self.DUMMY_VAE

    def load_vae(self, path):
        return self.DUMMY_VAE

    def load_clip(self, path, clip_type="stable_diffusion"):
        return self.DUMMY_CLIP

    def encode_text(self, clip_handle, text):
        return self.DUMMY_COND

    def empty_latent(self, width, height, batch_size=1):
        return self.DUMMY_LATENT

    def sample(self, model, positive, negative, latent, seed, steps, cfg,
               sampler_name, scheduler, denoise, **kwargs):
        return self.DUMMY_LATENT

    def sample_init(self, model, positive, negative, latent, seed, steps, cfg,
                    sampler_name, scheduler, denoise):
        """Return a minimal state dict with a single dummy timestep."""
        return {
            "latents":         self.DUMMY_LATENT["samples"],
            "timesteps":       [999],
            "step_idx":        0,
            "text_embeddings": self.DUMMY_COND[0][0],
            "sched_obj":       None,
            "unet":            model,
            "cfg":             cfg,
            "generator":       None,
        }

    def sample_step(self, state):
        state["step_idx"] += 1
        is_done = state["step_idx"] >= len(state["timesteps"])
        return self.DUMMY_LATENT, is_done

    def decode_vae(self, vae_handle, latent):
        return self.DUMMY_IMAGE

    def encode_vae(self, vae_handle, image):
        return self.DUMMY_LATENT

    def load_image(self, path):
        return self.DUMMY_IMAGE, None

    def save_image(self, image, path):
        return path


class _FailingBackend(_MockBackend):
    """Same as _MockBackend but every method raises RuntimeError."""

    def _fail(self, *_, **__):
        raise RuntimeError("simulated backend failure")

    load_checkpoint = _fail
    encode_text     = _fail
    empty_latent    = _fail
    sample          = _fail
    sample_init     = _fail
    sample_step     = _fail
    decode_vae      = _fail
    encode_vae      = _fail
    load_image      = _fail
    save_image      = _fail


# ─────────────────────────────────────────────────────────────────────────────
# CheckpointLoaderNode
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckpointLoaderNode:
    def test_ports_exist(self):
        node = _node("CheckpointLoader")
        assert "ckpt_path" in node.inputs
        assert "MODEL"     in node.outputs
        assert "CLIP"      in node.outputs
        assert "VAE"       in node.outputs
        assert "error"     in node.outputs
        assert "exec"      in node.inputs
        assert "next"      in node.outputs
        assert "failed"    in node.outputs

    def test_success(self):
        node = _node("CheckpointLoader")
        node.inputs["ckpt_path"].value = "/fake/model.safetensors"
        env  = _Env(_MockBackend())
        result = _run(node.compute(env=env))
        assert result.command == ExecCommand.CONTINUE
        assert result.control_outputs["next"]   is True
        assert result.control_outputs["failed"] is False
        assert node.outputs["MODEL"].value is _MockBackend.DUMMY_MODEL
        assert node.outputs["error"].value == ""

    def test_failure(self):
        node = _node("CheckpointLoader")
        node.inputs["ckpt_path"].value = "/fake/model.safetensors"
        result = _run(node.compute(env=_Env(_FailingBackend())))
        assert result.control_outputs["failed"] is True
        assert "simulated" in node.outputs["error"].value


# ─────────────────────────────────────────────────────────────────────────────
# CLIPTextEncodeNode
# ─────────────────────────────────────────────────────────────────────────────

class TestCLIPTextEncodeNode:
    def test_ports_exist(self):
        node = _node("CLIPTextEncode")
        assert "CLIP"         in node.inputs
        assert "text"         in node.inputs
        assert "CONDITIONING" in node.outputs

    def test_success(self):
        node = _node("CLIPTextEncode")
        node.inputs["CLIP"].value = _MockBackend.DUMMY_CLIP
        node.inputs["text"].value = "a photo of a cat"
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True
        assert node.outputs["CONDITIONING"].value == _MockBackend.DUMMY_COND

    def test_failure(self):
        node = _node("CLIPTextEncode")
        node.inputs["CLIP"].value = _MockBackend.DUMMY_CLIP
        node.inputs["text"].value = "a photo of a cat"
        result = _run(node.compute(env=_Env(_FailingBackend())))
        assert result.control_outputs["failed"] is True
        assert node.outputs["CONDITIONING"].value == []


# ─────────────────────────────────────────────────────────────────────────────
# EmptyLatentImageNode
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptyLatentImageNode:
    def test_success(self):
        node = _node("EmptyLatentImage")
        node.inputs["width"].value      = 512
        node.inputs["height"].value     = 512
        node.inputs["batch_size"].value = 1
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True
        assert node.outputs["LATENT"].value == _MockBackend.DUMMY_LATENT

    def test_defaults(self):
        """Node should use 512×512, batch=1 when inputs are not set."""
        node = _node("EmptyLatentImage")
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True


# ─────────────────────────────────────────────────────────────────────────────
# KSamplerNode
# ─────────────────────────────────────────────────────────────────────────────

class TestKSamplerNode:
    def _filled_node(self):
        node = _node("KSampler")
        node.inputs["MODEL"].value        = _MockBackend.DUMMY_MODEL
        node.inputs["positive"].value     = _MockBackend.DUMMY_COND
        node.inputs["negative"].value     = _MockBackend.DUMMY_COND
        node.inputs["latent_image"].value = _MockBackend.DUMMY_LATENT
        node.inputs["seed"].value         = 42
        node.inputs["steps"].value        = 20
        node.inputs["cfg"].value          = 7.0
        node.inputs["sampler_name"].value = "euler"
        node.inputs["scheduler"].value    = "karras"
        node.inputs["denoise"].value      = 1.0
        return node

    def test_success(self):
        node   = self._filled_node()
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True
        assert node.outputs["LATENT"].value == _MockBackend.DUMMY_LATENT
        assert node.outputs["error"].value  == ""

    def test_failure(self):
        node   = self._filled_node()
        result = _run(node.compute(env=_Env(_FailingBackend())))
        assert result.control_outputs["failed"] is True
        assert node.outputs["LATENT"].value == {}

    def test_is_durable(self):
        node = _node("KSampler")
        assert node.is_durable_step is True


# ─────────────────────────────────────────────────────────────────────────────
# VAEDecodeNode
# ─────────────────────────────────────────────────────────────────────────────

class TestVAEDecodeNode:
    def test_success(self):
        node = _node("VAEDecode")
        node.inputs["VAE"].value     = _MockBackend.DUMMY_VAE
        node.inputs["samples"].value = _MockBackend.DUMMY_LATENT
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True
        assert node.outputs["IMAGE"].value == _MockBackend.DUMMY_IMAGE

    def test_emits_preview_detail_without_changing_output_tensor(self, monkeypatch):
        node = _node("VAEDecode")
        node.inputs["VAE"].value = _MockBackend.DUMMY_VAE
        node.inputs["samples"].value = _MockBackend.DUMMY_LATENT

        event_bus = _CaptureEventBus()
        env = NodeEnvironment(backend=_MockBackend(), event_bus=event_bus)
        ctx = NodeContext(
            uuid="run-1",
            node_id=node.id,
            network_id="net-1",
            node_path=node.id,
            data_inputs={},
            control_inputs={},
            env=env,
        )

        vae_decode_module = importlib.import_module("nodegraph.python.noderegistry.imaging.VAEDecodeNode")
        monkeypatch.setattr(vae_decode_module, "to_data_url", lambda image: "data:image/png;base64,test-preview")

        result = _run(node.compute(executionContext=ctx))

        assert result.control_outputs["next"] is True
        assert node.outputs["IMAGE"].value == _MockBackend.DUMMY_IMAGE
        assert event_bus.events == [
            {
                "type": "NODE_DETAIL",
                "nodeId": node.id,
                "detail": {"url": None},
                "ts": event_bus.events[0]["ts"],
            },
            {
                "type": "NODE_DETAIL",
                "nodeId": node.id,
                "detail": {"url": "data:image/png;base64,test-preview"},
                "ts": event_bus.events[1]["ts"],
            },
        ]

    def test_failure(self):
        node = _node("VAEDecode")
        node.inputs["VAE"].value     = _MockBackend.DUMMY_VAE
        node.inputs["samples"].value = _MockBackend.DUMMY_LATENT
        result = _run(node.compute(env=_Env(_FailingBackend())))
        assert result.control_outputs["failed"] is True
        assert node.outputs["IMAGE"].value is None


# ─────────────────────────────────────────────────────────────────────────────
# VAEEncodeNode
# ─────────────────────────────────────────────────────────────────────────────

class TestVAEEncodeNode:
    def test_success(self):
        node = _node("VAEEncode")
        node.inputs["VAE"].value    = _MockBackend.DUMMY_VAE
        node.inputs["pixels"].value = _MockBackend.DUMMY_IMAGE
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True
        assert node.outputs["LATENT"].value == _MockBackend.DUMMY_LATENT


# ─────────────────────────────────────────────────────────────────────────────
# LoadImageNode
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadImageNode:
    def test_success(self):
        node = _node("LoadImage")
        node.inputs["image_path"].value = "/fake/input.png"
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["next"] is True
        assert node.outputs["IMAGE"].value == _MockBackend.DUMMY_IMAGE
        assert node.outputs["MASK"].value  is None

    def test_failure(self):
        node = _node("LoadImage")
        node.inputs["image_path"].value = "/fake/input.png"
        result = _run(node.compute(env=_Env(_FailingBackend())))
        assert result.control_outputs["failed"] is True
        assert node.outputs["IMAGE"].value is None


# ─────────────────────────────────────────────────────────────────────────────
# SaveImageNode
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveImageNode:
    def test_success(self, tmp_path):
        node = _node("SaveImage")
        node.inputs["images"].value          = _MockBackend.DUMMY_IMAGE
        node.inputs["filename_prefix"].value = "test_out"
        node.inputs["output_dir"].value      = str(tmp_path)
        result = _run(node.compute(env=_Env(_MockBackend())))
        assert result.control_outputs["done"] is True
        assert node.outputs["error"].value    == ""

    def test_unique_path_no_collision(self, tmp_path):
        """SaveImageNode._unique_path must generate distinct names."""
        from nodegraph.python.noderegistry.imaging.SaveImageNode import SaveImageNode
        p1 = SaveImageNode._unique_path(str(tmp_path), "img")
        # Simulate an existing file
        open(p1, "w").close()
        p2 = SaveImageNode._unique_path(str(tmp_path), "img")
        assert p1 != p2

    def test_failure(self, tmp_path):
        node = _node("SaveImage")
        node.inputs["images"].value          = _MockBackend.DUMMY_IMAGE
        node.inputs["filename_prefix"].value = "test_out"
        node.inputs["output_dir"].value      = str(tmp_path)
        result = _run(node.compute(env=_Env(_FailingBackend())))
        assert result.control_outputs["failed"] is True
        assert "simulated" in node.outputs["error"].value
