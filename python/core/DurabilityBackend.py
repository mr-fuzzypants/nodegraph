"""
DurabilityBackend — pluggable execution backends for the Executor.

The Executor calls ``backend.execute_node(...)`` for any node whose
``is_durable_step`` flag is True, delegating the actual invocation strategy
to the backend.  Three concrete backends are provided:

NullBackend (default)
    Runs ``compute_fn`` directly in-process with no persistence.
    Used for tests and local development — no DBOS or filesystem required.

FileBackend
    Persists each step result to a JSON sidecar file after the first run.
    Subsequent calls for the same ``(run_id, node_id)`` pair return the
    cached result immediately, enabling simple local replay without a DB.

DBOSBackend
    Delegates to a DBOS ``@step``-decorated function so DBOS can persist
    the result to Postgres and replay it exactly-once after a process restart.
    The ``compute_fn`` argument is ignored — the DBOS step re-executes the
    node by looking it up from ``graph_state.active_executors``.

Usage in tests
--------------
    # No DBOS needed — NullBackend is the default
    executor = Executor(graph)          # already has NullBackend
    await executor.cook_flow_control_nodes(start_node)

    # Explicit unit-testing of replay semantics
    backend = FileBackend("/tmp/checkpoints")
    executor.backend = backend

    # Production: swap in DBOS for exactly-once durability
    executor.backend = DBOSBackend(step_fn=_execute_node_step)
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Coroutine, Optional


# ---------------------------------------------------------------------------
# NullBackend
# ---------------------------------------------------------------------------

class NullBackend:
    """
    Transparent backend — calls ``compute_fn`` directly.

    This is the default backend so all existing code that never sets
    ``executor.backend`` continues to work unchanged, including the full
    pre-existing test suite.
    """

    async def execute_node(
        self,
        run_id: Optional[str],
        node_id: str,
        context: dict,
        compute_fn: Callable[..., Coroutine[Any, Any, Any]],
    ) -> dict:
        result = await compute_fn(executionContext=context)
        return {
            "command":         result.command.name,
            "data_outputs":    result.data_outputs,
            "control_outputs": result.control_outputs,
        }


# ---------------------------------------------------------------------------
# FileBackend
# ---------------------------------------------------------------------------

class FileBackend:
    """
    Write-once, read-many file cache for step results.

    The first call for a given ``(run_id, node_id)`` pair runs the node
    normally and persists the result dict as JSON.  Subsequent calls read
    the cached file and return immediately — mimicking DBOS step replay
    without requiring a running database.

    Useful for:
    * Local integration tests that verify replay semantics.
    * Offline debugging when you want to re-run a graph without re-hitting
      expensive LLM / external-API nodes.
    """

    def __init__(self, checkpoint_dir: str) -> None:
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)
        self._memory: dict[str, dict] = {}

    # ── helpers ──────────────────────────────────────────────────────────────

    def _key(self, run_id: Optional[str], node_id: str) -> str:
        return f"{run_id or 'local'}::{node_id}"

    def _path(self, run_id: Optional[str], node_id: str) -> str:
        safe_run = (run_id or "local").replace("/", "_").replace(":", "_")
        safe_node = node_id.replace("/", "_").replace(":", "_")
        return os.path.join(self.checkpoint_dir, f"{safe_run}__{safe_node}.json")

    def clear(self, run_id: Optional[str] = None) -> None:
        """Remove cached results — optionally filtered to a single run."""
        keys_to_drop = [
            k for k in list(self._memory)
            if run_id is None or k.startswith(f"{run_id or 'local'}::")
        ]
        for k in keys_to_drop:
            del self._memory[k]

    # ── main interface ────────────────────────────────────────────────────────

    async def execute_node(
        self,
        run_id: Optional[str],
        node_id: str,
        context: dict,
        compute_fn: Callable[..., Coroutine[Any, Any, Any]],
    ) -> dict:
        key  = self._key(run_id, node_id)
        path = self._path(run_id, node_id)

        # 1. In-memory cache hit
        if key in self._memory:
            return self._memory[key]

        # 2. Filesystem cache hit
        if os.path.exists(path):
            with open(path) as fh:
                result = json.load(fh)
            self._memory[key] = result
            return result

        # 3. Cache miss — execute and persist
        raw = await NullBackend().execute_node(run_id, node_id, context, compute_fn)
        with open(path, "w") as fh:
            json.dump(raw, fh)
        self._memory[key] = raw
        return raw


# ---------------------------------------------------------------------------
# DBOSBackend
# ---------------------------------------------------------------------------

class DBOSBackend:
    """
    Delegates to a DBOS ``@DBOS.step``-decorated function.

    ``compute_fn`` is intentionally ignored — the DBOS step function re-
    invokes the node's ``compute()`` by looking it up via
    ``graph_state.active_executors[run_id]``.  DBOS intercepts the call,
    persists the return value, and on process restart replays the result
    without re-executing the node, giving exactly-once semantics.

    Parameters
    ----------
    step_fn : async callable
        The ``@DBOS.step``-decorated function with signature
        ``(run_id: str, node_id: str, context: dict) -> dict``.
    """

    def __init__(self, step_fn: Any) -> None:
        self.step_fn = step_fn

    async def execute_node(
        self,
        run_id: Optional[str],
        node_id: str,
        context: dict,
        compute_fn: Callable[..., Coroutine[Any, Any, Any]],
    ) -> dict:
        # compute_fn is ignored; the DBOS step handles execution internally.
        return await self.step_fn(run_id, node_id, context)
