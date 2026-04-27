"""
NodeContext and NodeEnvironment — structured execution context for node compute().

This module replaces the plain ``dict`` that Executor previously passed as
``executionContext``.  There are two separate objects:

  NodeContext
      Serialisable snapshot of a node's identity and input values at the moment
      it is about to be cooked.  Can be written to JSON / sent over a wire.

  NodeEnvironment
      Process-local, non-serialisable resources shared across all nodes in a
      run: the diffusion-inference backend, the TensorStore for opaque values,
      trace IDs, etc.  Never persisted.

Serialisation — tagged envelope ("Approach 1")
-----------------------------------------------
Port values can be arbitrary Python objects (torch tensors, PIL Images, model
handles …) that are not JSON-serialisable.  We use a *tagged envelope* so the
decoder knows how to reconstruct each value:

  Primitive (str / int / float / bool / None / list / dict of primitives)
      {"$": "v", "value": <the raw value>}

  Everything else (tensor, model handle, PIL image, CONDITIONING tuple …)
      {"$": "ref", "id": "<uuid>", "hint": "<type name>"}
      The actual object is stored in a TensorStore keyed by that id.

This keeps the wire format compact (no base64 blobs) while remaining
forward-compatible: future tags such as ``"ndarray"`` (inline float32 array for
small tensors) can be added without breaking decoders that handle unknown tags
by falling back to a ref-store lookup.

TODO (Pydantic migration)
-------------------------
  Currently NodeContext is a plain dataclass.  When we expose the execution
  context over a public REST/gRPC API we should migrate to Pydantic v2:

    class NodeContext(BaseModel):
        uuid: str
        node_id: str
        ...

  Reasons to migrate:
  * ``model_json_schema()`` produces a JSON Schema document for free, enabling
    OpenAPI doc generation without hand-writing schemas.
  * Field-level validators (e.g. node_id must be non-empty) are declared
    inline and are enforced on both construction and deserialization.
  * IDE auto-complete works through the Pydantic plugin for VS Code / PyCharm.
  * ``model_validate_json()`` is significantly faster than ``json.loads`` +
    manual construction for large payloads (Pydantic v2 uses Rust internally).

  Why we haven't migrated yet:
  * Pydantic v2 is an additional dependency (~5 MB wheel).  We keep the core
    library dependency-free so it can be used in constrained environments.
  * The dataclass approach is simpler and already sufficient for in-process
    use.  Only add Pydantic when the *external API surface* is stable enough
    to warrant the overhead.

TensorStore (pluggable storage for opaque values)
-------------------------------------------------
  The default DictTensorStore is an in-process dict — fast, zero overhead.
  For multi-process or distributed execution, swap in SharedMemoryStore or
  a RedisStore that serialises tensors to shared memory / a remote cache.

  Protocol
  --------
  Any object with these two methods qualifies:

    def put(self, ref_id: str, value: Any) -> None
    def get(self, ref_id: str) -> Any

  DictTensorStore is the reference implementation.
"""

from __future__ import annotations

import json
import time
import uuid as _uuid_mod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    # Imported only for type-checkers; no runtime circular dependency.
    from nodegraph.python.core.event_bus import EventBus


# ---------------------------------------------------------------------------
# TensorStore — pluggable storage for opaque (non-JSON-serialisable) values
# ---------------------------------------------------------------------------

@runtime_checkable
class TensorStore(Protocol):
    """
    Minimal key-value store for opaque values that cannot be inlined in JSON.

    Implementations must be thread-safe if nodes run concurrently.
    """

    def put(self, ref_id: str, value: Any) -> None:
        """Store *value* under *ref_id*.  Raises on duplicate only if desired."""
        ...

    def get(self, ref_id: str) -> Any:
        """Retrieve the value for *ref_id*.  Raises KeyError if absent."""
        ...


class DictTensorStore:
    """
    In-process dict-backed TensorStore.

    This is the default store for local / single-process execution.
    Replace with SharedMemoryStore or RedisStore for multi-process graphs.

    TODO: for a distributed or multi-process runtime, swap this out for a
    store backed by shared memory (multiprocessing.shared_memory) or an
    external cache (Redis, Memcached).  The TensorStore Protocol means no
    call-site changes are needed — just pass a different store instance to
    NodeEnvironment.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    def put(self, ref_id: str, value: Any) -> None:
        self._store[ref_id] = value

    def get(self, ref_id: str) -> Any:
        return self._store[ref_id]


# ---------------------------------------------------------------------------
# Tagged-envelope encode / decode
# ---------------------------------------------------------------------------

# Types that can safely be inlined in JSON without any transformation.
_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def _is_primitive(value: Any) -> bool:
    """Return True if *value* can be round-tripped through JSON as-is."""
    if isinstance(value, _PRIMITIVE_TYPES):
        return True
    if isinstance(value, list):
        return all(_is_primitive(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_primitive(v) for k, v in value.items())
    return False


def _encode(value: Any, store: Optional[TensorStore]) -> Dict[str, Any]:
    """
    Encode *value* into a tagged envelope.

    If *store* is None the function still works but will raise a TypeError
    for non-primitive values (useful for strict serialisation contexts that
    must not emit refs without a backing store).
    """
    if _is_primitive(value):
        return {"$": "v", "value": value}

    # Everything non-primitive → store it and emit a ref tag.
    # Future optimisation: add an "$": "ndarray" tag for small float32 arrays
    # to avoid round-tripping through the store.  Only do this after profiling
    # shows the store overhead is significant.
    ref_id = str(_uuid_mod.uuid4())
    hint = type(value).__name__
    if store is None:
        raise TypeError(
            f"Cannot encode non-primitive value of type {hint!r} without a TensorStore. "
            "Pass a DictTensorStore() instance to NodeEnvironment."
        )
    store.put(ref_id, value)
    return {"$": "ref", "id": ref_id, "hint": hint}


def _decode(envelope: Any, store: Optional[TensorStore]) -> Any:
    """
    Decode a tagged envelope back to the original value.

    Tolerates bare (un-enveloped) values for backward compatibility with
    code that serialised raw dicts before this module existed.
    """
    # Handle legacy bare values (not yet tagged envelopes) gracefully.
    if not isinstance(envelope, dict) or "$" not in envelope:
        return envelope

    tag = envelope["$"]
    if tag == "v":
        return envelope["value"]
    if tag == "ref":
        if store is None:
            raise TypeError(
                f"Cannot decode ref envelope without a TensorStore (ref id={envelope.get('id')!r})."
            )
        return store.get(envelope["id"])

    # Unknown future tag — fail loudly so callers know the format has evolved.
    raise ValueError(f"Unknown envelope tag: {tag!r}")


# ---------------------------------------------------------------------------
# NodeContext
# ---------------------------------------------------------------------------

class NodeContext:
    """
    Serialisable snapshot of a node's execution inputs.

    Passed to ``node.compute(executionContext=ctx)`` in place of the old
    plain ``dict``.  Implements ``__getitem__`` so that existing nodes that
    do ``executionContext["node_id"]`` continue to work without modification.

    Backward-compatibility contract
    --------------------------------
    The following dict-style accesses are supported:

      ctx["uuid"]           → self.uuid
      ctx["node_id"]        → self.node_id
      ctx["network_id"]     → self.network_id
      ctx["node_path"]      → self.node_path
      ctx["data_inputs"]    → self.data_inputs   (live dict of decoded values)
      ctx["control_inputs"] → self.control_inputs

    All accesses beyond these top-level keys raise KeyError, exactly as a
    plain dict would.

    Runtime-only field: ``env``
    ---------------------------
    ``ctx.env`` carries the process-local :class:`NodeEnvironment` so that
    nodes can reach ``ctx.env.backend`` without a separate ``env=`` kwarg in
    their ``compute()`` signature.  This keeps the existing single-argument
    ``compute(self, executionContext=None)`` contract valid for all 60+
    existing node implementations that don't need env at all.

    ``env`` is intentionally excluded from ``to_wire()`` / serialisation —
    it holds non-serialisable ML objects and must never be transmitted over
    the wire.

    Design alternatives considered
    --------------------------------
    Option A: embed ``backend`` directly inside ``NodeContext``.
      Rejected — ``NodeContext`` is the serialisable half of the split.
      Mixing in non-serialisable references defeats the purpose and makes
      wire-format encoding brittle.

    Option B (this class): attach ``NodeEnvironment`` to ``NodeContext`` as a
      non-serialised runtime field.  Nodes access ``executionContext.env.backend``.
      Simple, zero new call-site changes for nodes that don't need env.

    Option C: add ``env=None`` as a second keyword argument to every
      ``compute()`` override.
      Rejected for now — would require touching ~67 existing node
      implementations that don't need env at all.

    TODO (Pydantic): when migrating, inherit from pydantic.BaseModel and
    annotate fields with the correct types.  ``__getitem__`` can remain as a
    compatibility shim or be deprecated once all call-sites are updated.
    """

    # Keys exposed via the dict-style backward-compat interface.
    _TOP_LEVEL_KEYS = frozenset(
        {"uuid", "node_id", "network_id", "node_path", "data_inputs", "control_inputs"}
    )

    def __init__(
        self,
        uuid: str,
        node_id: str,
        network_id: str,
        node_path: str,
        data_inputs: Dict[str, Any],
        control_inputs: Dict[str, Any],
        env: Optional["NodeEnvironment"] = None,
    ) -> None:
        self.uuid = uuid
        self.node_id = node_id
        self.network_id = network_id
        self.node_path = node_path
        self.data_inputs = data_inputs
        self.control_inputs = control_inputs
        # Runtime-only: not serialised.  Carries NodeEnvironment so nodes can
        # do ``executionContext.env.backend`` without a second compute() arg.
        self.env: Optional["NodeEnvironment"] = env

    # ── Backward-compat dict-style access ────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        """Support legacy ``executionContext["node_id"]`` style access."""
        if key in self._TOP_LEVEL_KEYS:
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Support ``executionContext.get("key", default)`` access."""
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return key in self._TOP_LEVEL_KEYS

    # ── Construction helpers ──────────────────────────────────────────────────

    @classmethod
    def from_execution_context(cls, execution_context: Any, store: Optional[TensorStore] = None, env: Optional["NodeEnvironment"] = None) -> "NodeContext":
        """
        Build a NodeContext from a legacy Executor.ExecutionContext object.

        *store* is the TensorStore used to stash non-primitive port values.
        If None, non-primitive values are stored as-is (no ref encoding).
        *env* is the NodeEnvironment to attach as a runtime-only field.
        """
        raw = execution_context.to_dict()
        return cls.from_dict(raw, store=store, env=env)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], store: Optional[TensorStore] = None, env: Optional["NodeEnvironment"] = None) -> "NodeContext":
        """
        Build a NodeContext from the plain dict produced by
        ``ExecutionContext.to_dict()``.

        Values are decoded from tagged envelopes if present; raw values
        (from legacy code that never encoded them) are kept as-is.
        """
        def _decode_port_map(port_map: Dict[str, Any]) -> Dict[str, Any]:
            return {
                name: _decode(envelope, store)
                for name, envelope in port_map.items()
            }

        return cls(
            uuid=raw.get("uuid", ""),
            node_id=raw.get("node_id", ""),
            network_id=raw.get("network_id", ""),
            node_path=raw.get("node_path", ""),
            data_inputs=_decode_port_map(raw.get("data_inputs", {})),
            control_inputs=_decode_port_map(raw.get("control_inputs", {})),
            env=env,
        )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_wire(self, store: Optional[TensorStore] = None) -> Dict[str, Any]:
        """
        Encode this context for transport (JSON, IPC, etc.) using tagged
        envelopes.  Non-primitive values are pushed into *store* and replaced
        with ref tags.

        TODO (Pydantic): replace with ``model_dump(mode="json")`` + custom
        serialiser for the ref tags once we migrate to BaseModel.
        """
        def _encode_port_map(port_map: Dict[str, Any]) -> Dict[str, Any]:
            return {
                name: _encode(value, store)
                for name, value in port_map.items()
            }

        return {
            "uuid":           self.uuid,
            "node_id":        self.node_id,
            "network_id":     self.network_id,
            "node_path":      self.node_path,
            "data_inputs":    _encode_port_map(self.data_inputs),
            "control_inputs": _encode_port_map(self.control_inputs),
        }

    def to_json(self, store: Optional[TensorStore] = None) -> str:
        """Convenience wrapper: serialize to a JSON string."""
        return json.dumps(self.to_wire(store=store))

    @classmethod
    def from_json(cls, s: str, store: Optional[TensorStore] = None) -> "NodeContext":
        """Convenience wrapper: deserialize from a JSON string."""
        return cls.from_dict(json.loads(s), store=store)

    # ── Progress reporting ────────────────────────────────────────────────────

    async def report_progress(self, progress: float, message: str = "") -> None:
        """Publish a NODE_PROGRESS event for this node.

        Parameters
        ----------
        progress : float
            Fraction of work completed in the range [0.0, 1.0].  Values
            outside this range are clamped silently.
        message : str
            Optional human-readable status string shown in the UI beneath the
            progress bar.  May be empty.

        Example
        -------
        Nodes can stream their progress from inside ``compute()`` without any
        knowledge of the underlying transport::

            async def compute(self, executionContext=None):
                for i, item in enumerate(items):
                    await executionContext.report_progress(i / len(items), f"step {i}")
                    process(item)
        """
        if self.env is None:
            return
        clamped = max(0.0, min(1.0, float(progress)))
        await self.env.event_bus.publish({
            "type":     "NODE_PROGRESS",
            "nodeId":   self.node_id,
            "progress": clamped,
            "message":  message,
            "ts":       int(time.time() * 1000),
        })

    async def report_status(self, status: str) -> None:
        """Publish a NODE_STATUS event (arbitrary status text, no percentage).

        Use this for phase labels like "Loading weights", "Warming cache", etc.
        """
        if self.env is None:
            return
        await self.env.event_bus.publish({
            "type":   "NODE_STATUS",
            "nodeId": self.node_id,
            "status": status,
            "ts":     int(time.time() * 1000),
        })

    async def report_detail(self, detail: Dict[str, Any]) -> None:
        """Publish a NODE_DETAIL event for UI-only metadata.

        This is intentionally separate from port values: callers can attach
        preview URLs, token counts, dimensions, or other display metadata
        without changing the runtime value carried by the node's outputs.
        """
        if self.env is None:
            return
        await self.env.event_bus.publish({
            "type":   "NODE_DETAIL",
            "nodeId": self.node_id,
            "detail": detail,
            "ts":     int(time.time() * 1000),
        })

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"NodeContext(node_id={self.node_id!r}, uuid={self.uuid!r}, "
            f"data_inputs={list(self.data_inputs)!r})"
        )


# ---------------------------------------------------------------------------
# NodeEnvironment
# ---------------------------------------------------------------------------

@dataclass
class NodeEnvironment:
    """
    Process-local, non-serialisable runtime resources shared across all nodes
    in a single execution run.

    This object is never persisted or sent over the wire.  It is created once
    by the Executor (or WorkflowManager for production runs) and passed
    alongside NodeContext to each node's compute() call.

    Fields
    ------
    backend : Any
        The diffusion-inference backend (e.g. SafetensorsBackend, DiffusersBackend).
        Nodes access this via ``env.backend`` to load checkpoints / run sampling.
        Defaults to None — imaging nodes will raise a clear error if they are
        executed without a backend rather than getting a confusing AttributeError
        on a dict.

    tensor_store : TensorStore
        Shared key-value store for large / opaque objects that cannot be inlined
        in the NodeContext wire format.  Each execution run gets its own store so
        refs from one run don't bleed into another.

    trace_id : str | None
        Optional correlation ID propagated from the HTTP request / workflow run
        for distributed tracing.

    TODO (Pydantic): NodeEnvironment intentionally does NOT migrate to Pydantic
    because it holds non-serialisable objects (torch models, PIL image handles).
    A Pydantic model would need ``model_config = ConfigDict(arbitrary_types_allowed=True)``
    which defeats most of the value Pydantic provides.  Keep this as a plain
    dataclass.
    """

    backend: Any = None
    tensor_store: TensorStore = field(default_factory=DictTensorStore)
    trace_id: Optional[str] = None
    # Pluggable async publish/subscribe transport.  Defaults to NullEventBus
    # (no-op) so nodes that don't emit progress work without any configuration.
    # WorkflowManager injects a real bus (SocketIOEventBus, CompositeEventBus)
    # at the start of each execution run.
    event_bus: Any = field(default_factory=lambda: _get_null_event_bus())


# ---------------------------------------------------------------------------
# Lazy NullEventBus factory
# ---------------------------------------------------------------------------
# Defined after NodeEnvironment to avoid a forward-reference problem.
# The lambda in field(default_factory=...) is evaluated at instance-creation
# time, so this function is available by then.

def _get_null_event_bus() -> Any:
    """Return a NullEventBus instance without importing at module load time.

    This defers the import of event_bus so that node_context remains usable
    in environments where event_bus hasn't been installed yet (e.g. minimal
    test setups), and avoids any potential circular-import issues.
    """
    from nodegraph.python.core.event_bus import NullEventBus  # local import
    return NullEventBus()
