"""
System resource routes — framework-agnostic memory stats and cache control.

Probe order:
  1. torch.mps  (Apple Silicon / Metal)
  2. torch.cuda (NVIDIA)
  3. fallback → 0

All torch imports are guarded so the server starts cleanly even when PyTorch
is not installed or the target backend is absent.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


def _get_allocated_bytes() -> tuple[int, int]:
    """Return ``(allocated_bytes, reserved_bytes)`` for the active compute backend."""
    try:
        import torch  # noqa: PLC0415
        if torch.backends.mps.is_available():
            allocated = torch.mps.current_allocated_memory()
            # MPS does not expose a separate "reserved" figure; report the same value.
            return allocated, allocated
    except Exception:
        pass

    try:
        import torch  # noqa: PLC0415
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated()
            reserved = torch.cuda.memory_reserved()
            return allocated, reserved
    except Exception:
        pass

    return 0, 0


def _clear_cache() -> str:
    """Empty the allocator cache of the active compute backend. Returns a label."""
    try:
        import torch  # noqa: PLC0415
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
            return "cleared: mps"
    except Exception:
        pass

    try:
        import torch  # noqa: PLC0415
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            return "cleared: cuda"
    except Exception:
        pass

    return "no-op: no supported backend found"


@router.get("/system/memory")
def get_memory() -> dict:
    """Return current memory usage for the active compute backend."""
    allocated, reserved = _get_allocated_bytes()
    return {"allocatedBytes": allocated, "reservedBytes": reserved}


@router.post("/system/clear-cache")
def clear_cache() -> dict:
    """Empty the compute-backend allocator cache and return updated memory stats."""
    result = _clear_cache()
    allocated, reserved = _get_allocated_bytes()
    return {"ok": True, "result": result, "allocatedBytes": allocated, "reservedBytes": reserved}
