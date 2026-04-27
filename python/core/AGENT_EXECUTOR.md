# AgentExecutor

LLM-driven graph traversal built on top of NodeGraph's `Executor`.

---

## What Was Changed and Why

### The One Change to `Executor.py`

The B+C block inside `cook_flow_control_nodes` — which decided what to execute next after a node fired its control outputs — was extracted verbatim into an `async def _process_control_outputs(...)` method:

```python
# Before (inlined in the result processing loop):
connected_ids = []
for control_name, control_value in result.control_outputs.items():
    edges = self.graph.get_outgoing_edges(cur_node.id, control_name)
    ...
    connected_ids.extend(next_ids)
for next_node_id in connected_ids:
    self.build_flow_node_execution_stack(...)

# After (extracted, called identically):
await self._process_control_outputs(cur_node, result, execution_stack, pending_stack)
```

This is a pure refactor. The base `Executor` behaviour is identical. All 51 existing tests pass unchanged.

The extraction was made `async` intentionally so subclasses can `await` LLM calls inside the override without requiring any changes to the main `cook_flow_control_nodes` loop, which is already `async`.

No other changes were made to `Executor.py`.

---

## Architecture

### Inheritance

```
Executor
└── AgentExecutor
```

`AgentExecutor` overrides exactly one method: `_process_control_outputs`. Everything else is inherited:

| Inherited from Executor | Role |
|-------------------------|------|
| `cook_flow_control_nodes` | Main scheduling loop, parallel batch execution, deferred stack |
| `_execute_single_node` | Node execution, timing, `on_before_node`/`on_after_node` hooks |
| `build_flow_node_execution_stack` | Dependency resolution before scheduling |
| `push_data_from_node` | Data port propagation along edges |
| `propogate_network_inputs_to_internal` | NodeNetwork boundary handling |
| `get_upstream_nodes` / `get_downstream_nodes` | Graph traversal helpers |

Nodes are completely unaware of the agent loop. They receive the same `ExecutionContext` dict and return the same `ExecutionResult` as in plain `Executor` execution. Separation of concerns is preserved.

### The Override: `_process_control_outputs`

Three phases run in sequence for every node that finishes:

```
Phase 1 — FORK CHECK (before super)
    Count how many distinct fired control ports have wired outgoing edges.
    If >1: LLM picks one port → result.control_outputs filtered to that port only.
    This is where branching decisions happen on fully-wired graphs.

Phase 2 — STATIC ROUTING (super call)
    Base Executor follows whichever edges remain after phase 1.
    For single-path and fan-out graphs: zero LLM calls, identical to plain Executor.

Phase 3 — DEAD-END FALLBACK (after super)
    If super() scheduled nothing (no wired successors existed),
    LLM calls another node that already exists in the graph, or terminates.
    Only activates when the graph has no wired successor.
```

### LLM Schemas

Two separate Pydantic models are used so the LLM's output type is precise at each call site:

**`ForkDecision`** — used at phase 1:
```python
class ForkDecision(BaseModel):
    chosen_port: str   # must match one port name from the candidates
    reasoning:   str
```

**`TraversalDecision`** — used at phase 3:
```python
class TraversalDecision(BaseModel):
    action:          Literal["call_node", "terminate"]
    node_id:         Optional[str]
    input_overrides: Optional[Dict[str, Any]]  # injected onto target node's input ports
    reasoning:       str
    is_complete:     bool
```

### Observability

| Attribute | Type | Contents |
|-----------|------|----------|
| `working_memory` | `Dict[str, Any]` | Latest output values from every node that has run, keyed by `name_nodeprefix` |
| `trace` | `List[Dict]` | Append-only record of every LLM decision taken, with step, type, node, action, reasoning |

`working_memory` is populated via the `on_after_node` hook — no new `Executor` API was needed.

### `AgentExecutor.plan()`

Class method that asks an LLM to design a graph from scratch and returns a ready-to-run pair:

```python
executor, start_node = await AgentExecutor.plan(
    "Add two numbers and log the result.",
    model="openai:gpt-4o-mini",
)
await executor.cook_flow_control_nodes(start_node)
```

Internally:
1. Calls `Node.list_node_types()` and creates dummy node instances to introspect port names
2. Presents the type catalogue to the LLM with its system prompt
3. LLM returns a `GraphPlan` (validated Pydantic model — `nodes: List[PlannedNode]`, `edges: List[PlannedEdge]`)
4. Materialised using `NodeNetwork.create_node()` and `graph.add_edge()` — identical to a human-built graph
5. The result is **saveable, loadable in the UI, and compilable by the existing compiler** without modification

---

## Practical Applications

### 1. Conditional Routing on Data Values

A `Classifier` node fires both `positive` and `negative` control ports (both are wired to downstream nodes). With `Executor` both paths run. With `AgentExecutor` the LLM reads the classifier's `confidence` output and chooses the more appropriate branch:

```
[Classifier] --positive--> [ApproveFlow]
           \--negative--> [RejectFlow]
```

The graph is fully wired. The LLM branches it at runtime based on content, not just structure.

### 2. Variable-Length Processing Chains

A pipeline that doesn't know how many transformation steps are needed at design time:

```
[Ingest] --> [Transform] --> (dead-end)
```

The LLM inspects the transform output and decides: loop Transform again with different parameters, call a downstream Validate node, or terminate. The graph topology stays fixed; the LLM provides the iteration count.

### 3. Tool Dispatch Without a Tool Registry

A graph contains specialised nodes (`SummariseNode`, `TranslateNode`, `ClassifyNode`). The start node fires a dead-end control output. The LLM reads the input data in `working_memory` and dispatches to the appropriate node directly — no routing logic in the graph, no tool registry, no LLM-specific scaffolding in any node.

### 4. LLM-Authored Graphs

`AgentExecutor.plan()` lets an LLM design the entire graph topology before execution begins:

```python
executor, start = await AgentExecutor.plan(
    "Fetch a URL, extract the main body text, classify its sentiment, and log the result.",
)
```

Because the result is a normal `NodeNetwork` + `Graph`, it is:
- Inspectable and editable in the TypeScript UI
- Serialisable to the same JSON format as hand-authored graphs
- Compilable by `python/compiler/` to Python, AssemblyScript, or Wasm
- Runnable by the plain `Executor` with no agent overhead

---

## Dangers

### LLM Calls Are on the Critical Execution Path

Every fork decision and every dead-end adds a synchronous (awaited) LLM round-trip to the execution hot path. On a graph with 10 branching nodes, a single slow model response (2–5s) becomes 10–50s of blocking latency. There is no timeout, no cancellation, no circuit breaker.

**Risk**: Long-running graphs silently stall waiting for LLM responses with no indication to callers.

### No Result Verification

After the LLM says "call node X with input Y", the executor sets `port.setValue(Y)` and runs the node. There is no type-checking against the port's declared `ValueType`, no range validation, and no way for the node to signal that the LLM-supplied input is malformed without raising an exception that propagates up through `asyncio.gather`.

**Risk**: An LLM hallucinating an integer when a string is expected corrupts port state silently for downstream nodes.

### `working_memory` Is Unbounded

Every node that executes appends to `working_memory`. On a long-running agentic loop (max_steps=20 nodes calling 3 sub-nodes each), this dict grows without bound and the last-5-entries truncation in the prompt builder hides the overflow rather than preventing it.

**Risk**: Memory growth proportional to total nodes executed across the session lifetime.

### `plan()` Trusts the LLM on Port Names

`_describe_node_types` creates dummy node instances via `Node.create_node()` and reads port names from the live objects. The LLM receives these names in its prompt. If the LLM misspells a port name in a `PlannedEdge`, `graph.add_edge()` is called with a non-existent port name. The Graph does not validate port existence — it stores the edge regardless — and the error only surfaces at execution time, potentially several nodes into the run.

**Risk**: Silent graph misconfiguration from LLM hallucination. The `# Skipping.` warning in `plan()` discards bad edges with a log line but no exception.

### Fork Fallback Is "Follow All Paths"

If the LLM call fails or returns an invalid port name during fork resolution, the fallback is to leave `result.control_outputs` unmodified and call `super()`, which follows all wired paths. On a graph with expensive downstream nodes (network calls, model inference), this silently doubles the work.

**Risk**: Silent cost amplification on LLM failure, opposite of the intended behaviour.

### `max_steps` Counts Nodes Executed, Not LLM Calls

`self._step` is incremented by `_capture_node_outputs` (the `on_after_node` hook), which fires on every node execution — including nodes scheduled by static routing with no LLM involvement. A graph with 15 statically-wired nodes exhausts a `max_steps=20` budget before the LLM is ever consulted at a genuine dead-end.

**Risk**: The budget is consumed by execution progress, not by LLM decisions, making it an unreliable safety valve.

### No State Persistence Across Sessions

`working_memory` and `trace` are instance attributes that are lost when the `AgentExecutor` object is garbage-collected. There is no checkpoint mechanism connected to the existing `on_checkpoint` hook stub in `Executor`. Resuming a partially-executed agentic workflow after a crash is not possible.

**Risk**: Any long-running workflow is unrecoverable if the process dies mid-execution.

---

## Comparison with GripTape

This section is an honest evaluation. GripTape is a mature, production-oriented agent framework. The comparison is relevant because both systems execute LLM-driven task graphs, but they make opposite architectural bets.

### What GripTape Does

GripTape represents an LLM workflow as a `Pipeline` or `Workflow` containing `Task` objects. Tasks communicate by passing `Artifact` values. An `Agent` wraps a pipeline and manages the agent loop, memory drivers, and tool declarations. The LLM is called by the agent; the task graph determines flow.

Tasks expose a tool interface (`@tool`) that the LLM calls by name. GripTape manages prompt construction, tool invocation, result parsing, retry logic, and structured logging.

### Where AgentExecutor Is Technically Stronger

**Graph compilation.** An `AgentExecutor`-generated graph can be compiled to WebAssembly by the existing `python/compiler/` pipeline. GripTape workflows are Python objects with no equivalent lower-level target. A NodeGraph graph that routes via LLM decisions can be progressively migrated toward fully-static execution by wiring the edges the LLM repeatedly chooses — an optimisation path that does not exist in GripTape.

**Graph topology as first-class data.** NodeGraph's `Graph` is a data structure (nodes + edges in an Arena) that the UI can render, edit, save, and reload. GripTape pipelines are code. The LLM's routing decisions (`trace`) and the graph structure it operated on can both be inspected, diffed, and stored as JSON. GripTape has no equivalent inspectable graph object.

**Node execution isolation.** NodeGraph nodes are completely unaware of the agent loop. The same `AddNode` or `LogNode` runs identically under `Executor` and `AgentExecutor`. GripTape tasks must be authored with the agent context in mind (prompt templates, `context` dict, `Artifact` types). There is no clean separation between "what the task does" and "how it participates in the agent loop".

**Subgraph composition.** `NodeNetwork` allows hierarchical composition — an agent can operate on a graph that contains other graphs as nodes. GripTape has no equivalent hierarchical nesting.

### Where AgentExecutor Is Technically Weaker

**Tool registry.** GripTape has a mature, typed, versioned tool system. Tools declare their schema, handle parameter validation, raise typed exceptions, and support retries. `AgentExecutor`'s equivalent is `input_overrides` — a raw `Dict[str, Any]` that bypasses port type declarations entirely. GripTape tools are production-ready. `input_overrides` is a proof-of-concept.

**Memory architecture.** GripTape provides `ConversationMemory`, `SummaryConversationMemory`, `TaskMemory`, and `MetaMemory` with pluggable storage backends (SQL, vector DBs, etc.). `AgentExecutor.working_memory` is a plain dict in process memory. There is no persistence, no retrieval, no summarisation for long contexts, and no cross-session continuity.

**Prompt management.** GripTape manages the conversation history, system prompts, tool descriptions, and output parsing in a single coherent structure. `AgentExecutor` constructs prompts by string concatenation in `_build_fork_prompt` and `_build_decision_prompt`. There is no conversation history — the LLM receives no memory of its prior decisions beyond what fits in `working_memory[-5:]`. Across a 20-step execution the LLM is effectively stateless.

**Retry and error handling.** GripTape has configurable retry policies, exception handlers per-task, and structured error escalation paths. `AgentExecutor` catches all LLM exceptions with a bare `except Exception` and either falls back silently (fork: follow all paths) or logs and returns (dead-end: terminate). Neither fallback is safe in production — one doubles cost, the other silently abandons the workflow.

**Observability integration.** GripTape produces structured event streams compatible with OpenTelemetry. `AgentExecutor.trace` is a list of dicts written to nowhere. There is no logging framework integration, no span tracking, no token usage accounting.

**Streaming.** GripTape supports streaming LLM responses with a callback interface. `AgentExecutor` uses `await agent.run(prompt)` — a blocking call that waits for the full structured response before proceeding. For large responses or slow models this blocks the entire execution loop.

**Testing.** GripTape provides `MockStructure`, `MockTask`, and prompt injection utilities for deterministic testing. `AgentExecutor` has no mock LLM injection point and no deterministic test mode. Every test that exercises the agent path requires a real LLM API key or a complete `pydantic-ai` mock at the `Agent` class level.

### The Fundamental Difference

GripTape treats the LLM as the primary computation unit. Tasks exist to provide structured inputs and outputs. The agent loop is the main execution model.

`AgentExecutor` treats the graph as the primary computation unit. The LLM is consulted only when the graph constrains the choices (at a fork or dead-end). On a well-designed graph the LLM is never called. On a poorly-designed graph the LLM papers over missing edges.

This is both the system's strength and its honest limitation: `AgentExecutor` is a tool for making incomplete or ambiguous graphs executable. GripTape is a tool for building agent workflows from scratch. They are not competing at the same problem.

**Appropriate use**: `AgentExecutor` on a graph where the routing is mostly static and the LLM resolves 1–3 genuine decision points per execution run. GripTape for a workflow that is primarily LLM-driven with structured tool calls at the leaves.

**Inappropriate use**: `AgentExecutor` as a replacement for proper graph design — using dead-ends intentionally as a substitute for wiring edges. This trades graph clarity for LLM opacity, increases per-run cost, and removes the ability to compile, reproduce, or audit execution.
