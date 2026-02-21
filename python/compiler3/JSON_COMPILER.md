# JSON Compilation — Developer Guide

## Overview

The JSON compiler pipeline allows you to compile a NodeGraph directly from a
`.json` file — no live Python node objects required.  This is the foundation
for a hosted API service where clients submit graph descriptions and receive
standalone Python files in return.

The JSON pathway slots into the existing compiler pipeline by replacing
`compiler2/extractor.py` (which requires a live `Graph` instance) with
`compiler3/deserialiser.py` (which reads a structured JSON dict).

```
Live code path:
    Graph  →  [compiler2.extractor]  →  IRGraph

JSON code path:
    graph.json  →  [compiler3.deserialiser]  →  IRGraph

Shared from here on:
    IRGraph  →  [compiler2.scheduler]  →  IRSchedule
    IRSchedule  →  [compiler3.emitter]  →  standalone Python source
```

---

## File Map

| File | Purpose |
|------|---------|
| `python/compiler3/deserialiser.py` | `json_to_ir(source) → IRGraph` — core JSON → IR conversion |
| `python/compiler3/schema.py` | Graph JSON schema definition + lightweight validator |
| `python/compile_from_json.py` | CLI entry point |
| `python/graphs/*.json` | Example serialised graphs |

---

## JSON Format

### Top-level structure

```json
{
  "graph_name": "my-pipeline",
  "id":         "optional-stable-uuid",
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `graph_name` | string | ✅ | Human label; used as the compiled file header and Python function name |
| `id` | string | ❌ | Stable ID (useful for versioning / caching) |
| `nodes` | array | ✅ | List of node objects |
| `edges` | array | ✅ | List of edge objects |

### Node object

```json
{
  "id":      "node_001",
  "type":    "ConstantNode",
  "name":    "Task",
  "inputs":  { "value": "Hello, world!" },
  "outputs": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique within the graph; used in edge references |
| `type` | string | ✅ | Registered node type name (see Known Node Types) |
| `name` | string | ❌ | Display name (defaults to `id` if omitted) |
| `inputs` | object | ❌ | Static input-port values; wired ports are satisfied by edges |
| `outputs` | object | ❌ | Static output-port overrides (rarely needed) |

**ConstantNode special case:** its constant value goes in `inputs.value` in JSON,
even though the live `ConstantNode` stores it on `outputs["out"].value`.
The deserialiser handles the translation automatically.

### Edge object

```json
{
  "from_node": "node_001",
  "from_port": "out",
  "to_node":   "node_002",
  "to_port":   "task"
}
```

All four fields are required strings.  Edge class (data / control) is inferred
from the source port's class in the PORT_SCHEMA registry.

---

## Known Node Types

| Type | Classification | Notable ports |
|------|---------------|---------------|
| `ConstantNode` | constant | out (data out) |
| `AddNode` | data | a, b → sum |
| `MultiplyNode` | data | a, b → product |
| `PrintNode` | passthrough | exec (ctrl in), value (data in), next (ctrl out) |
| `BranchNode` | branch | exec, condition → true_out, false_out |
| `ForLoopNode` | loop_again | exec, start, end → loop_body, completed, index |
| `AccumulatorNode` | passthrough | exec, val → next |
| `StepPrinterNode` | passthrough | exec, step_type, step_content, tool_name → next |
| `ToolAgentNode` | data | task, tools, model → result, tool_calls, steps |
| `ToolAgentStreamNode` | loop_again | exec, task, tools, model → loop_body, completed, step_type, step_content, tool_name, step_count, result |
| `LLMNode` | data | prompt, system_prompt, model, temperature → response, model_used, tokens_used |
| `PromptTemplateNode` | data | template, variables → prompt |
| `VectorNode` | data | x, y, z → vec |
| `DotProductNode` | data | vec_a, vec_b → result |

---

## CLI Usage

```bash
# Basic — compile to L3 (zero-framework, raw openai) in python/compiled_json/
python python/compile_from_json.py python/graphs/streaming_agent.json

# Custom output directory
python python/compile_from_json.py python/graphs/blocking_agent.json --out python/compiled_l3/

# L2 target (LangChain output)
python python/compile_from_json.py python/graphs/streaming_agent.json --target l2 --out python/compiled/

# Print to stdout instead of writing a file
python python/compile_from_json.py python/graphs/blocking_agent.json --print

# Treat unknown node types as errors (for CI)
python python/compile_from_json.py python/graphs/streaming_agent.json --strict
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | File not found, schema validation error, or unhandled exception |

---

## Port Schema Registry (`PORT_SCHEMA`)

`compiler3/deserialiser.py` contains `PORT_SCHEMA` — a dict mapping every
known node type to its full port specification.  This is how the deserialiser
resolves port class (`"data"` or `"control"`) without instantiating live nodes.

```python
PORT_SCHEMA: Dict[str, Dict[str, Dict[str, Any]]] = {
    "PrintNode": {
        "exec":  {"direction": "in",  "port_class": "control"},
        "value": {"direction": "in",  "port_class": "data"},
        "next":  {"direction": "out", "port_class": "control"},
    },
    ...
}
```

### Fallback heuristic

For ports not found in `PORT_SCHEMA` (unknown type, or extra ports beyond the
schema), the deserialiser falls back to a name-pattern heuristic:

```python
_CONTROL_PORT_NAMES = frozenset({
    "exec", "next", "loop_body", "completed",
    "true_out", "false_out", "trigger", "done",
})
```

Any port name in this set → `"control"`. Everything else → `"data"`.

---

## Adding a New Compilable Node Type

### 1. Register the port schema

Add an entry to `PORT_SCHEMA` in `compiler3/deserialiser.py`:

```python
"MyCustomNode": {
    "exec":      {"direction": "in",  "port_class": "control"},
    "text":      {"direction": "in",  "port_class": "data", "default": ""},
    "next":      {"direction": "out", "port_class": "control"},
    "result":    {"direction": "out", "port_class": "data"},
},
```

### 2. Register the type name in schema.py

Add the type name to `KNOWN_NODE_TYPES` in `compiler3/schema.py`:

```python
KNOWN_NODE_TYPES: frozenset[str] = frozenset({
    ...
    "MyCustomNode",
})
```

### 3. Add a code template

Add a `NodeTemplate` subclass to `compiler3/templates.py`:

```python
class MyCustomNodeTemplate(NodeTemplate):
    def preamble(self, node: ScheduledNode) -> List[str]:
        return []  # top-level helpers, if any

    def emit_inline(self, node: ScheduledNode, writer: CodeWriter) -> None:
        text_expr = node.input_exprs.get("text", '""')
        result_var = node.output_vars.get("result", "_result")
        writer.writeln(f"{result_var} = my_custom_transform({text_expr})")

TEMPLATE_REGISTRY["MyCustomNode"] = MyCustomNodeTemplate()
```

### 4. Write a JSON example

```json
{
  "graph_name": "my-custom-pipeline",
  "nodes": [
    { "id": "n1", "type": "ConstantNode", "name": "Input",
      "inputs": { "value": "hello" }, "outputs": {} },
    { "id": "n2", "type": "MyCustomNode", "name": "Transform",
      "inputs": {}, "outputs": {} }
  ],
  "edges": [
    { "from_node": "n1", "from_port": "out", "to_node": "n2", "to_port": "text" }
  ]
}
```

---

## Validator

`compiler3/schema.py` provides a lightweight structural validator (no
third-party dependencies):

```python
from nodegraph.python.compiler3.schema import validate, validate_file, SchemaError

# Validate a pre-parsed dict
try:
    validate(my_dict)
except SchemaError as e:
    print(f"Invalid graph: {e}")

# Validate + load a file
data = validate_file("python/graphs/streaming_agent.json")
```

**Checks performed:**
- `graph_name`, `nodes`, `edges` fields present and correctly typed
- Each node has `id` (string, unique) and `type` (string)
- Each edge has `from_node`, `from_port`, `to_node`, `to_port` (all strings)
- Edge endpoints reference valid node IDs
- Node types are in `KNOWN_NODE_TYPES` (warning by default; error with `--strict`)

---

## Programmatic API

You can drive the pipeline from Python without using the CLI:

```python
from nodegraph.python.compiler3.deserialiser import json_to_ir
from nodegraph.python.compiler2.scheduler    import Scheduler
from nodegraph.python.compiler3.emitter      import emit

# Load and compile
ir       = json_to_ir("python/graphs/streaming_agent.json")
schedule = Scheduler(ir).build(graph_name=ir.name)
source   = emit(schedule)

# Write to disk
with open("my_pipeline.py", "w") as f:
    f.write(source)

# Or pass source through the network — the output is just a string
```

---

## Architecture Notes

### Why a separate deserialiser instead of extending extractor.py?

`extractor.py` is coupled to live `Graph`/`Node` objects from the execution
engine.  The deserialiser is purely data-in, data-out — it only imports from
`compiler2.ir` (dataclasses).  This separation keeps the two ingest paths
independently testable and decoupled.

### Exec-class inference without live nodes

The live extractor infers exec_class by inspecting actual port objects
(`_is_control_port(port)` checks the class name for "Control").  The
deserialiser replicates this by:

1. Looking up the port's class in `PORT_SCHEMA` (primary path).
2. Falling back to `_CONTROL_PORT_NAMES` pattern matching (secondary path).
3. Applying the same structural rules as `extractor._infer_exec_class`:
   - Has `loop_body` + `completed` outputs → `"loop_again"`
   - Has `true_out` + `false_out` outputs → `"branch"`
   - Has any control outputs → `"passthrough"`
   - Has no data inputs and is not flow-control → `"constant"`
   - Otherwise → `"data"`

### Shared IR

Both pathways produce the same `IRGraph` dataclass.  All downstream phases
(scheduler, emitter) are unmodified — they operate on `IRGraph` regardless
of how it was constructed.

---

## Limitations

| Limitation | Notes |
|-----------|-------|
| No sub-graphs (NodeNetworks) | JSON format is flat; nested networks not yet supported |
| Static tool list | `tools` input must list tool names explicitly in JSON; dynamic tool loading not supported |
| No runtime type checking | Port value types are not validated beyond structural shape |
| PORT_SCHEMA is hardcoded | Must be manually updated when adding new node types |

---

## Suggested Improvements

1. **Auto-generate PORT_SCHEMA** — introspect live node classes at import time
   to build PORT_SCHEMA dynamically, eliminating manual maintenance.

2. **JSON Schema file** — export a `graph.schema.json` (JSON Schema draft-07)
   alongside `schema.py` so editors can provide autocomplete for `.json` files.

3. **Sub-graph support** — add a `"nodes"` → `"type": "NodeNetworkNode"` with
   a nested `"subgraph"` field to support composable pipelines.

4. **Hosted API** — wrap `compile_from_json.py` behind a FastAPI endpoint:
   `POST /compile` → `{ source: str }`.  The deserialiser + scheduler + emitter
   are stateless so this is trivially parallelisable.

5. **Round-trip serialiser** — complement the deserialiser with a `graph_to_json()`
   function that serialises a live `Graph` to the canonical JSON format, enabling
   export from the canvas UI.
