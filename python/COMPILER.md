# NodeGraph Compiler v2

> **Status**: Working — generates correct standalone Python from live graph objects.  
> **Core file changes**: None.  All compiler code is isolated in `python/compiler2/`.

---

## 1. Overview

The compiler transforms a live `nodegraph` `Graph` object into a self-contained Python file that has **no nodegraph imports**. The output requires only the domain dependencies for that graph (e.g. `langchain`, `openai`) and can be run on any machine with those packages installed.

### Motivation

| Problem | Compiler solution |
|---|---|
| Graphs embed the execution engine | Output calls Python directly — no `Executor`, no `PluginRegistry` |
| Node logic is spread across many files | Logic is inlined into a single script |
| Debugging requires tracing the executor | Output is plain Python — step through in any debugger |
| Deployment requires the full nodegraph runtime | Output is portable — one file, minimal deps |

### Usage

```python
from nodegraph.python.compiler2 import compile_graph

net, agent = build_streaming(task, tools)
source = compile_graph(net.graph, graph_name="my_pipeline")

with open("output.py", "w") as f:
    f.write(source)
```

```bash
python output.py   # runs without nodegraph installed
```

---

## 2. Architecture — Four-Phase Pipeline

```
  ┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌────────────┐
  │  Graph   │───▶│  Extractor   │───▶│  Scheduler  │───▶│  Emitter   │
  │ (live)   │    │  ir.IRGraph  │    │ IRSchedule  │    │ Python str │
  └──────────┘    └──────────────┘    └─────────────┘    └────────────┘
```

### Phase 1 — Extractor (`extractor.py`)

Converts the live `Graph` into a serialisable `IRGraph` snapshot.  No live node references survive this phase.

Key responsibilities:
- Skip the `NodeNetwork` container node (it is the graph host, not a computation unit)
- Classify each node into an `exec_class` via structural heuristics (port names, `is_flow_control_node`)
- Detect edge types (data / control) from port class names (`"Control" in type(port).__name__`)
- Capture static output-port values (e.g. `ConstantNode.outputs["out"].value`)

### Phase 2 — IR (`ir.py`)

Pure data classes — no execution logic, no live object references.

```
IRGraph
  ├── nodes: Dict[id, IRNode]
  │     ├── IRPort (input/output, data/control, static value)
  │     └── exec_class: constant | data | loop_again | branch | passthrough
  └── edges: List[IREdge]
        └── edge_class: data | control
```

### Phase 3 — Scheduler (`scheduler.py`)

Resolves **execution order** and **variable naming**:

1. **Driver detection** — finds the first flow-control node with no incoming control edges.  This is the entry point for the flow execution.
2. **Data preamble** — topological sort of all data/constant ancestors of the driver.
3. **Block construction** — follows control edges from the driver to classify the graph into `LoopBlock` (LOOP_AGAIN driver) or `SequenceBlock` (CONTINUE or passthrough driver).

Each `ScheduledNode` carries:
- `output_vars`      — `port → python_variable_name`
- `input_exprs`      — `port → python_expression` (either a variable reference or a `repr()` literal)
- `output_port_values` — raw values from static output ports (used by `ConstantNodeTemplate`)

**Variable naming convention**: `{safe_node_name}_{port_name}`

```
Node "Agent", port "step_type"  →  agent_step_type
Node "Task",  port "out"        →  task_out
```

### Phase 4 — Emitter (`emitter.py`) + Templates (`templates.py`)

The emitter walks the `IRSchedule` tree and delegates per-node code generation to `NodeTemplate` subclasses.  Templates are registered by `type_name` in `TEMPLATE_REGISTRY`.

---

## 3. Node Classification

| `exec_class` | Detection heuristic | Emission |
|---|---|---|
| `constant` | `is_flow_control=False`, no data input ports | `output_var = <literal>` |
| `data` | `is_flow_control=False`, has data inputs | `output_var = await <func>(inputs)` |
| `loop_again` | `is_flow_control=True`, has `loop_body` + `completed` outputs | `async for _step in <gen>:` |
| `branch` | `is_flow_control=True`, has `true_out` + `false_out` outputs | `if <cond>: ... else: ...` |
| `passthrough` | `is_flow_control=True`, none of the above | Inline function call |

---

## 4. The LOOP_AGAIN → Generator Pattern

This is the most important compilation pattern.  A `LOOP_AGAIN` node in the executor becomes an `async for` loop over an async generator in the compiled output.

**In the executor:**

```
Iteration 1: Agent.compute() → LOOP_AGAIN  → StepPrinter.compute() → CONTINUE
Iteration 2: Agent.compute() → LOOP_AGAIN  → StepPrinter.compute() → CONTINUE
...
Iteration N: Agent.compute() → COMPLETED   → Output.compute()      → CONTINUE
```

**In the compiled output:**

```python
# Preamble: the agent loop becomes an async generator function
async def _agent_event_stream(task, tool_names, model):
    ...
    async for event in agent.astream_events(...):
        if kind == "on_tool_start": yield { ... }
        elif kind == "on_tool_end": yield { ... }
        elif kind == "on_chain_end": yield { ... }

# Main function: the loop body is inlined
async for _step in _agent_event_stream(task=task_out, ...):
    agent_step_type = _step.get("step_type", "")
    ...
    if agent_step_type == "final":
        agent_result = agent_step_content
        break
    # ── loop_body branch ──
    if agent_step_type == "tool_call":
        print(f"  → {agent_tool_name}({agent_step_content})")
    ...
# ── completed branch ──
print(f"[Output] {agent_result}")
```

The mapping is:
- `NodeTemplate.preamble()` → the async generator function definition
- `NodeTemplate.emit_loop_expr()` → the `async for _step in <expr>:` expression
- `NodeTemplate.emit_loop_break()` → unpack `_step` fields + break-on-final
- loop body nodes → inlined via `emit_inline()` inside the `async for`
- completed branch nodes → inlined via `emit_inline()` after the loop

---

## 5. Adding a New Node Type

1. **Register the node type** in the execution system (existing requirement).
2. **Create a `NodeTemplate` subclass** in `python/compiler2/templates.py`:

```python
class MyNodeTemplate(NodeTemplate):
    def preamble(self, node: ScheduledNode) -> List[str]:
        # Return top-level function/import lines needed exactly once.
        return ["from mylib import myfunction", ""]

    def emit_inline(self, node: ScheduledNode, writer: CodeWriter) -> None:
        input_expr = node.input_exprs.get("my_input", '""')
        out_var    = node.output_vars.get("my_output", "_out")
        writer.writeln(f"{out_var} = myfunction({input_expr})")
```

3. **Register it**:

```python
TEMPLATE_REGISTRY["MyNodeType"] = MyNodeTemplate()
```

For `LOOP_AGAIN` nodes, also override `emit_loop_expr()` and `emit_loop_break()`.

---

## 6. Current Limitations

| Limitation | Detail |
|---|---|
| **NodeNetwork subgraphs** | Nested `NodeNetwork` nodes are not inlined.  The compiler currently skips network container nodes.  Subgraph inlining requires recursing into `net.graph` during extraction. |
| **BranchNode** | Structural scheduling is in place (`SequenceBlock` with body/chain), but the `BranchNodeTemplate` is not yet implemented.  The correct emission is `if/else` with two scoped blocks. |
| **Cyclic data flow** | The topological sort assumes a DAG.  Cycles (e.g. accumulator feeding back into a source) are not handled. |
| **Parallel fan-out** | Single control output with multiple downstream nodes is not yet tested.  The executor runs them concurrently (`asyncio.gather`); the compiler would need to emit them sequentially or as `asyncio.gather` calls. |
| **Dynamic tool lists** | Tools wired via a data edge (rather than a static port value) cannot be inlined by the compiler — the list isn't known at compile time. |
| **ForLoopNode** | Structurally identical to `ToolAgentStreamNode` (LOOP_AGAIN, `loop_body`/`completed`).  Template not yet registered — emits a TODO block. |

---

## 7. Suggested Core System Improvements

These are suggestions for improving the core `python/core/` files to make the compiler more robust.  **No core files were changed** by the compiler implementation — all suggestions are additive.

### 7.1 `compile_hint` on `Node`

The current `exec_class` detection uses a structural heuristic (port names).  A formal `compile_hint` property would be more reliable:

```python
# python/core/Node.py — SUGGESTED ADDITION
class CompileHint:
    CONSTANT    = "constant"    # Pure value source, no compute
    DATA        = "data"        # Standard data-push (CONTINUE)
    GENERATOR   = "generator"   # Emits as async for (LOOP_AGAIN)
    CONDITIONAL = "conditional" # Emits as if/else (BRANCH)
    PASSTHROUGH = "passthrough" # Inline CONTINUE call

class Node:
    # ... existing code ...
    compile_hint: str = CompileHint.DATA   # Override in subclasses
```

With this, `LLMStreamNode` and `ToolAgentStreamNode` would declare `compile_hint = CompileHint.GENERATOR`, and the extractor needs no heuristics.

### 7.2 `NodeCodeTemplate` protocol on `Node`

Allow node classes to self-describe their compilation:

```python
# python/core/Node.py — SUGGESTED ADDITION
class NodeCodeTemplate(Protocol):
    def preamble(self) -> List[str]: ...
    def emit_inline(self, vars: dict, writer: Any) -> None: ...
    def emit_loop_expr(self, vars: dict) -> str: ...

class Node:
    @classmethod
    def code_template(cls) -> Optional[NodeCodeTemplate]:
        """Override to provide compile-time code generation hints."""
        return None
```

This keeps compilation logic co-located with the node definition while remaining opt-in.

### 7.3 `serialize_ports()` on `Node`

A standardised serialisation method would make both the compiler and the REST API cleaner:

```python
# python/core/Node.py — SUGGESTED ADDITION
def serialize_ports(self) -> dict:
    return {
        "inputs":  {k: {"class": p.function.name, "value": p.value} for k, p in self.inputs.items()},
        "outputs": {k: {"class": p.function.name, "value": p.value} for k, p in self.outputs.items()},
    }
```

Currently the compiler reads port attributes directly from live objects; a stable `serialize_ports()` would make the extractor immune to internal refactoring.

### 7.4 `ExecCommand` annotations on `compute()`

Type the return command statically so tools can reason about it without running the node:

```python
# python/core/Node.py — SUGGESTED ADDITION
returns_commands: ClassVar[set[ExecCommand]] = {ExecCommand.CONTINUE}
```

Overridden in `ForLoopNode` to `{LOOP_AGAIN, COMPLETED}`, in `BranchNode` to `{CONTINUE}` etc.  This replaces the port-name heuristic entirely.

### 7.5 Graph validation before compilation

Before emitting code, the compiler should call a new `validate()` method on `Graph` that checks:
- No unreachable nodes
- No cyclic data dependencies
- All required input ports are connected or have defaults
- No mixed-type edge connections (control port → data port)

This would surface wiring errors at compile time rather than at runtime.

---

## 8. File Map

```
python/
├── compiler2/               ← NEW (no core changes)
│   ├── __init__.py          ← Public API: compile_graph(graph, graph_name) -> str
│   ├── ir.py                ← IRGraph, IRNode, IRPort, IREdge (data classes)
│   ├── extractor.py         ← live Graph → IRGraph
│   ├── scheduler.py         ← IRGraph → IRSchedule (ScheduledNode, LoopBlock, etc.)
│   ├── templates.py         ← NodeTemplate registry + templates per type_name
│   └── emitter.py           ← IRSchedule → Python source string
│
├── compile_demo.py          ← Demo: compiles streaming + blocking agent graphs
│
└── compiled/                ← Generated output (not committed to source control)
    ├── streaming_agent.py
    ├── blocking_agent.py
    └── streaming_agent_multistep.py
```

### Core files — unchanged

```
python/core/
├── Node.py           ← Node.compile() hook exists (pass) — no changes made
├── Executor.py       ← no changes
├── GraphPrimitives.py← no changes
├── NodePort.py       ← no changes
└── Types.py          ← no changes
```

---

## 9. Example Output

### Compiled streaming agent (`streaming_agent.py`)

Running `compile_graph(net.graph, "streaming-agent-simple")` on the streaming graph from `langchain_agent_stream_example.py` produces:

```python
#!/usr/bin/env python3
"""
Compiled from NodeGraph: streaming-agent-simple
Generated:  2026-02-21
...
"""
from __future__ import annotations
import asyncio, os

# ── LangChain tools ────────────────────────────────────────────
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str: ...

@tool
def word_count(text: str) -> str: ...

_TOOLS = {"calculator": calculator, "word_count": word_count}

async def _agent_event_stream(task, tool_names, model="gpt-4o-mini"):
    """Async generator over reasoning steps."""
    from langchain.agents import create_agent
    agent = create_agent(model=f"openai:{model}", ...)
    async for event in agent.astream_events(..., version="v2"):
        if kind == "on_tool_start": yield {"step_type": "tool_call", ...}
        elif kind == "on_tool_end": yield {"step_type": "tool_result", ...}
        elif kind == "on_chain_end" and name == "LangGraph": yield {"step_type": "final", ...}

async def run() -> None:
    task_out = 'What is 123 * 456? Then count the words in the answer.'

    agent_step_type = ""
    ...
    async for _step in _agent_event_stream(task=task_out, tool_names=['calculator', 'word_count'], model='gpt-4o-mini'):
        agent_step_type    = _step.get('step_type',  '')
        ...
        if agent_step_type == 'final':
            agent_result = agent_step_content
            break
        # Node: StepPrinter (StepPrinterNode)
        if agent_step_type == 'tool_call':
            print(f'  → {agent_tool_name}({agent_step_content})', flush=True)
        ...

    # Node: Output (PrintNode)
    print(f'[Output] ' + str(agent_result))

if __name__ == "__main__":
    asyncio.run(run())
```

**Verified output** (running the compiled file directly):

```
  → calculator({'expression': '123 * 456'})
  ← 56088
  → word_count({'text': '56088'})
  ← 1
[Output] The result of 123 × 456 is 56088, which consists of 1 word.
```
