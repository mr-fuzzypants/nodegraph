# Core Improvements

> Generated: 2026-02-21  
> Based on: Session analysis of existing architecture, compiler implementation,
> and node ecosystem development.  
> Status: Proposed — none of these changes have been implemented yet.

---

## Summary

Eight improvements identified during development. Low-risk changes (2, 3, 4, 6, 7, 8)
can be implemented in a single session. Architectural changes (1, 5) require careful
planning.

| # | Change | Risk | Value | Effort | Status |
|---|--------|------|-------|--------|--------|
| 1 | `ExecCommand.SUSPEND` | Medium | Very high | Medium | 🔲 Proposed |
| 2 | Schema-driven ports fully wired | Low | High | Low | 🔲 Proposed |
| 3 | `ValueType` additions | Low | Medium | Low | 🔲 Proposed |
| 4 | Typed port defaults + validation | Low | Medium | Low | 🔲 Proposed |
| 5 | Observer pattern on `Executor` | Medium | High | Medium | 🔲 Proposed |
| 6 | `ExecutionResult.trace` field | Low | High | Low | 🔲 Proposed |
| 7 | Cycle detection at edge-add time | Low | Medium | Low | 🔲 Proposed |
| 8 | Node `metadata` block | Low | Low | Low | 🔲 Proposed |

---

## 1. `ExecCommand.SUSPEND` — Human-in-the-Loop

**Files affected:**
- `python/core/Executor.py` — `ExecCommand`, `Executor`
- `python/server/routes/` — new `POST /api/networks/{net_id}/resume/{node_id}` endpoint

**Why:** The single most valuable missing primitive. Everything that needs
human-in-the-loop (HumanReviewNode, IterativeLoopNode, approval gates) depends
on the executor being able to park a branch and wait for an external signal.
Without `SUSPEND`, all such patterns require either polling or restarting graph
execution from scratch.

**What changes:**

```python
# python/core/Executor.py — ⚠️ CORE CHANGE: SUSPEND command
# Date: 2026-02-21
class ExecCommand(Enum):
    CONTINUE   = auto()
    WAIT       = auto()
    LOOP_AGAIN = auto()
    COMPLETED  = auto()
    SUSPEND    = auto()   # NEW — park execution, wait for external signal
```

```python
# python/core/Executor.py — suspension plumbing
class Executor:
    def __init__(self):
        self._suspended:   dict[str, asyncio.Event] = {}
        self._resume_data: dict[str, dict]          = {}

    async def resume_node(self, node_id: str, data: dict) -> None:
        """Called by POST /api/networks/{net_id}/resume/{node_id}"""
        self._resume_data[node_id] = data
        self._suspended[node_id].set()

    async def _handle_suspend(self, node: Node) -> dict:
        """Parks execution at this node until resume_node() is called."""
        event = asyncio.Event()
        self._suspended[node.id] = event
        await event.wait()                        # releases the event loop here
        return self._resume_data.pop(node.id, {})
```

**New REST endpoint:**

```
POST /api/networks/{net_id}/resume/{node_id}
Body: { "decision": "approve" | "revise" | "reject", "feedback": "..." }
```

**Compiler output:** `SUSPEND` compiles to `input()` in Level 3 output —
the compiled script becomes an interactive program with zero framework
dependency.

**Nodes that depend on this:** `HumanReviewNode`, `IterativeLoopNode`,
`ApprovalGateNode`.

---

## 2. Schema-Driven Port Wiring — Fully Connected

**Files affected:**
- `python/core/Node.py`
- `python/server/node_definitions.py`
- `python/compiler3/deserialiser.py`
- `python/compiler3/schema.py`

**Why:** `SchemaLoader.py` and the `/schemas/` directory exist but nothing calls
`apply_schema_ports()` from within node classes. Adding a new node type currently
requires 4 manual updates in 4 different files:

1. `node_definitions.py` — manual port wiring in `create_ports()`
2. `compiler3/deserialiser.py` — hardcoded `PORT_SCHEMA` dict
3. `compiler3/schema.py` — `KNOWN_NODE_TYPES` list
4. `typescript/ui/src/lib/nodeSchemas.ts` — inlined schema objects

With this change, only 2 updates are needed:

1. `schemas/nodes/NewNode.json` — the schema definition
2. `node_definitions.py` — only the `execute()` / `compute()` logic

**What changes:**

```python
# python/core/Node.py — ⚠️ CORE CHANGE: schema-driven port construction
# Date: 2026-02-21
class Node:
    # ...existing code...
    def create_ports_from_schema(self) -> None:
        """Auto-wire ports from /schemas/nodes/{type}.json.
        Falls through silently if no schema exists for this type."""
        from nodegraph.python.core.SchemaLoader import apply_schema_ports, load_schema
        try:
            apply_schema_ports(self, load_schema(self.type))
        except (FileNotFoundError, KeyError):
            pass
```

```python
# python/server/node_definitions.py — before vs after
# Before: 8 lines of manual port wiring
class ForEachNode(Node):
    def create_ports(self):
        self.is_flow_control_node = True
        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.inputs["items"]      = InputDataPort(self.id, "items", ValueType.ANY)
        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"] = OutputControlPort(self.id, "completed")
        self.outputs["item"]      = OutputDataPort(self.id, "item",  ValueType.ANY)
        self.outputs["index"]     = OutputDataPort(self.id, "index", ValueType.INT)
        self.outputs["total"]     = OutputDataPort(self.id, "total", ValueType.INT)

# After: 1 line
class ForEachNode(Node):
    def create_ports(self):
        self.create_ports_from_schema()
```

```python
# python/compiler3/deserialiser.py — replace hardcoded dict
# Before: hardcoded PORT_SCHEMA = { "ForEachNode": {...}, ... }
# After:
from nodegraph.python.core.SchemaLoader import load_schema

def _get_port_spec(type_name: str) -> dict:
    return load_schema(type_name)["ports"]
```

---

## 3. `ValueType` Additions

**Files affected:**
- `python/core/Types.py`

**Why:** Three semantic types are missing. Adding them enables:
- `DICT` — `AnonymizerNode` entities output, `JSONParseNode`, structured outputs
- `IMAGE` — lets the UI render a thumbnail for **any** node with an `IMAGE` output
  port, without checking `nodeType === 'ImageGenNode'` specifically
- `BYTES` — `FileReadNode` binary mode, audio/video pipelines

The `ValueType.validate()` method already exists and handles unknowns gracefully,
so adding entries is purely additive.

```python
# python/core/Types.py — ⚠️ CORE CHANGE: new value types
# Date: 2026-02-21
class ValueType(Enum):
    # existing
    ANY    = "any"
    INT    = "int"
    FLOAT  = "float"
    STRING = "string"
    BOOL   = "bool"
    DICT   = "dict"
    ARRAY  = "array"
    OBJECT = "object"
    VECTOR = "vector"
    MATRIX = "matrix"
    COLOR  = "color"
    BINARY = "binary"
    # NEW
    IMAGE  = "image"    # image URL or base64 blob — triggers thumbnail in UI
    BYTES  = "bytes"    # raw binary / audio / video data
```

**UI impact:** `FunctionNode.tsx` can switch from:

```typescript
// Before — fragile node-type check
const showThumbnail = data.nodeType === 'ImageGenNode';

// After — semantic port-type check
const showThumbnail = data.outputs.some(p => p.valueType === 'image');
```

---

## 4. Typed Port Defaults + Validation

**Files affected:**
- `python/core/NodePort.py`

**Why:** `NodePort.setValue()` currently logs a warning on type mismatch but
never raises. Silent type failures propagate deep into LLM calls before surfacing.

The existing `ValueType.validate()` is already correct. The change is to call it
in `__debug__` mode (stripped by `python -O`) so development catches mismatches
at the point of wiring, not at the point of failure.

```python
# python/core/NodePort.py — ⚠️ CORE CHANGE: raise on type mismatch in debug mode
# Date: 2026-02-21
def setValue(self, value: Any):
    if not ValueType.validate(value, self.data_type):
        if __debug__:
            raise TypeError(
                f"Port '{self.port_name}' on node '{self.node_id}' "
                f"expects {self.data_type.value}, got {type(value).__name__} = {value!r}"
            )
        else:
            logger.warning(
                f"Port '{self.port_name}' type mismatch: "
                f"expected {self.data_type.value}, got {type(value).__name__}"
            )
    self.value = value
    self._isDirty = False
```

Also add typed defaults to `InputDataPort.__init__` so ports never return `None`
when disconnected:

```python
# python/core/NodePort.py
class InputDataPort(DataPort):
    def __init__(self, node_id: str, port_name: str, data_type=DataType.ANY,
                 default=None):
        super().__init__(node_id, port_name, PORT_TYPE_INPUT, data_type=data_type)
        self.incoming_connections = []
        # Apply schema default or type default
        if default is not None:
            self.value = default
        # value is already set to _get_default_for_type(data_type) by NodePort.__init__
```

---

## 5. Observer Pattern on `Executor`

**Files affected:**
- `python/core/Executor.py`
- `python/server/langchain_nodes.py` (all nodes that currently call `sio.emit()`)

**Why:** Trace events (`NODE_START`, `NODE_COMPLETE`, `STREAM_CHUNK`) are
emitted from inside `langchain_nodes.py` via direct `socketio.emit()` calls.
This violates the project's separation-of-concerns principle:

> *Keep Node definitions separate from Executor logic.*

Nodes that call `socketio.emit()` directly:
- Cannot be unit tested without a live socket
- Cannot be compiled to standalone scripts cleanly
- Cannot be ported to TypeScript or Rust without re-importing a socket library

**What changes:**

```python
# python/core/Executor.py — ⚠️ CORE CHANGE: formal observer protocol
# Date: 2026-02-21
from typing import Protocol

class ExecutorObserver(Protocol):
    """Implement to receive execution lifecycle events from the Executor."""
    async def on_node_start(self,    node: 'Node') -> None: ...
    async def on_node_complete(self, node: 'Node',
                               result: 'ExecutionResult') -> None: ...
    async def on_node_error(self,    node: 'Node',
                               error: Exception) -> None: ...
    async def on_node_suspend(self,  node: 'Node') -> None: ...
    async def on_trace(self,         node: 'Node', trace: dict) -> None: ...

class Executor:
    def __init__(self, observer: 'ExecutorObserver | None' = None):
        self._observer = observer
        # ...existing init...
```

```python
# python/server/socket_observer.py — new file, bridges Executor to Socket.IO
class SocketIOObserver:
    def __init__(self, sio, net_id: str):
        self._sio    = sio
        self._net_id = net_id

    async def on_node_start(self, node):
        await self._sio.emit("trace", {"type": "NODE_START", "nodeId": node.id})

    async def on_node_complete(self, node, result):
        await self._sio.emit("trace", {"type": "NODE_COMPLETE", "nodeId": node.id})

    async def on_trace(self, node, trace):
        await self._sio.emit("trace", {**trace, "nodeId": node.id})

    async def on_node_error(self, node, error):
        await self._sio.emit("trace", {
            "type": "NODE_ERROR", "nodeId": node.id, "error": str(error)
        })

    async def on_node_suspend(self, node):
        await self._sio.emit("trace", {"type": "NODE_SUSPENDED", "nodeId": node.id})
```

**Note:** Implement improvement 6 (`ExecutionResult.trace`) before this one —
it provides the mechanism for nodes to return trace data without touching socketio.

---

## 6. `ExecutionResult.trace` Field

**Files affected:**
- `python/core/Executor.py` — `ExecutionResult`
- `python/server/langchain_nodes.py` — all streaming nodes

**Why:** Prerequisite for improvement 5. Nodes need a way to pass trace/event
data back to the executor without importing socketio. Adding a `trace` field to
`ExecutionResult` is the minimal change that enables this.

The executor reads `result.trace` after each `execute()` call and forwards it to
the observer. Nodes never touch socketio again.

```python
# python/core/Executor.py — ⚠️ CORE CHANGE: trace field on ExecutionResult
# Date: 2026-02-21
class ExecutionResult(IExecutionResult):
    def __init__(self,
                 command: ExecCommand,
                 control_outputs: Optional[Dict[str, Any]] = None,
                 trace: Optional[Dict[str, Any]] = None):    # NEW
        self.command         = command
        self.control_outputs = control_outputs or {}
        self.data_outputs    = {}
        self.trace           = trace or {}                   # NEW
        # ...existing fields...
```

**Before — node calls socketio directly:**

```python
await sio.emit("trace", {"type": "STREAM_CHUNK", "content": chunk})
return ExecutionResult(ExecCommand.LOOP_AGAIN, {"loop_body": True})
```

**After — node returns data, executor handles emission:**

```python
return ExecutionResult(
    ExecCommand.LOOP_AGAIN,
    control_outputs={"loop_body": True},
    trace={"type": "STREAM_CHUNK", "content": chunk}
)
```

---

## 7. Cycle Detection at Edge-Add Time

**Files affected:**
- `python/core/GraphPrimitives.py` — `Graph.add_edge()`

**Why:** Cycles are currently only detected when the executor runs (topological
sort fails). An edge that creates a cycle, added via the UI, gives no feedback
until execution starts — by which point the error is confusing and distant from
the action that caused it.

Eager detection at `add_edge()` means the server returns a `400` immediately,
and the UI can show a visual "cannot connect" flash on the attempted edge.

```python
# python/core/GraphPrimitives.py — ⚠️ CORE CHANGE: eager cycle detection
# Date: 2026-02-21

class GraphCycleError(Exception):
    pass

class Graph:
    def add_edge(self, from_node_id: str, from_port_name: str,
                 to_node_id: str, to_port_name: str) -> 'Edge':
        if self._would_create_cycle(from_node_id, to_node_id):
            raise GraphCycleError(
                f"Adding edge {from_node_id} → {to_node_id} would create a cycle. "
                f"Use a SubGraph or feedback variable for intentional cycles."
            )
        # ...existing add logic...

    def _would_create_cycle(self, from_id: str, to_id: str) -> bool:
        """DFS from to_id. If we can reach from_id, adding this edge creates a cycle."""
        visited: set = set()
        stack = [to_id]
        while stack:
            node_id = stack.pop()
            if node_id == from_id:
                return True
            if node_id not in visited:
                visited.add(node_id)
                # Walk all outgoing edges from this node
                for edge in self.edges:
                    if edge.from_node_id == node_id:
                        stack.append(edge.to_node_id)
        return False
```

---

## 8. Node `metadata` Block

**Files affected:**
- `python/core/GraphPrimitives.py` — `GraphNode.__init__`
- `python/core/Node.py` — `Node.__init__`
- `python/server/state.py` — seed network construction
- `python/compiler3/deserialiser.py` — graph JSON deserialisation

**Why:** Canvas position (`x`, `y`), collapsed state, and color overrides
currently live only in React state and are lost on server restart. Graph JSON
cannot roundtrip correctly without position data.

```python
# python/core/GraphPrimitives.py — ⚠️ CORE CHANGE: metadata block on GraphNode
# Date: 2026-02-21
class GraphNode(IGraphNode):
    def __init__(self, name: str, type: str, network_id: str = None,
                 metadata: dict = None):
        self.name      = name
        self.id        = uuid.uuid4().hex
        self.uuid      = uuid.uuid4().hex
        self.network_id = network_id
        self.metadata  = metadata or {}
        # metadata keys:
        # "x"         : float  — canvas x position
        # "y"         : float  — canvas y position
        # "collapsed" : bool   — collapsed in the UI
        # "color"     : str    — hex override, None = use schema default
        # "width"     : float  — width override, None = use schema min_width
```

**Graph JSON impact — serialised graphs include position:**

```json
{
  "id": "node_001",
  "type": "LLMNode",
  "name": "MyLLM",
  "metadata": { "x": 400, "y": 200, "collapsed": false, "color": null }
}
```

This makes the graph JSON file the single authoritative source of canvas layout —
no separate position store needed in React state.

---

## Implementation Order

### Batch 1 — Low-risk, single session (changes 2, 3, 4, 6, 7, 8)

All are purely additive. No existing behaviour changes.

```
3  ValueType additions (Types.py)        — 3 lines
8  metadata block (GraphPrimitives.py)   — 5 lines
7  cycle detection (GraphPrimitives.py)  — 15 lines
4  port validation (NodePort.py)         — 5 lines changed
6  ExecutionResult.trace (Executor.py)   — 3 lines
2  create_ports_from_schema (Node.py)    — 8 lines
```

### Batch 2 — Architectural (changes 1, 5)

Implement 6 before 5. Implement 5 before 1.

```
6  ExecutionResult.trace   — nodes can return trace data
5  Observer on Executor    — executor routes trace data via observer
1  SUSPEND command         — executor can park and resume execution
```

Each batch 2 change requires:
1. Core change with `# ⚠️ CORE CHANGE` header comment
2. Corresponding test in `python/test/test_<name>.py`
3. Entry in project `CHANGES.md`
