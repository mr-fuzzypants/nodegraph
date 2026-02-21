# Changes — 2026-02-21

## ForEachNode Implementation

---

### Core File Changes

#### `python/core/Node.py`
Added `ValueType.ANY` to the `ValueType` enum.

**Why:** `ForEachNode.item` output port must emit values of any type (the iterated list can contain strings, dicts, ints, etc.). Without `ANY` there was no way to express a type-agnostic port.

```python
# Added
ANY = "any"
```

#### `python/core/NodePort.py`
Added `ANY` handling in `InputDataPort.accepts()`.

**Why:** Required so `ForEachNode.item` can connect to downstream nodes regardless of what type the list contains.

```python
# Before
def accepts(self, value_type: ValueType) -> bool:
    return self.value_type == value_type

# After
def accepts(self, value_type: ValueType) -> bool:
    if self.value_type == ValueType.ANY:
        return True
    if value_type == ValueType.ANY:
        return True
    return self.value_type == value_type
```

---

### New Node — `ForEachNode`

**File:** `python/server/node_definitions.py`

Iterates a list, emitting one item per executor loop iteration via `LOOP_AGAIN`.

**Ports:**

| Port | Direction | Type | Notes |
|---|---|---|---|
| `exec` | control in | — | trigger |
| `items` | data in | `LIST` | list to iterate |
| `loop_body` | control out | — | fires once per item |
| `completed` | control out | — | fires when list exhausted |
| `item` | data out | `ANY` | current element |
| `index` | data out | `INT` | 0-based position |
| `total` | data out | `INT` | `len(items)` |

**Edge cases handled:**
- Empty list / `None` → `COMPLETED` immediately, `loop_body` never fires
- List snapshot on first entry — mid-loop mutations to `items` ignored
- Re-execution after `COMPLETED` — state resets cleanly

---

### Compiler Changes

#### `python/compiler3/templates.py`
- Added `_FOREACH_HELPER` preamble (async generator)
- Added `ForEachNodeTemplate` class
- Registered as `"ForEachNode"` in template registry

#### `python/compiler2/templates.py`
- Same as above (required for LangChain / L2 compilation target)

#### `python/compiler3/schema.py`
- Added `"ForEachNode"` to `KNOWN_NODE_TYPES` frozenset

#### `python/compiler3/deserialiser.py`
- Added `ForEachNode` to `PORT_SCHEMA` with full port spec

---

### UI Seed

#### `python/server/state.py`
Added `ForEachDemo` subnetwork seeded into `_seed_demo()`.

Layout:
```
ConstantNode(["apple", "banana", "cherry"])
     │ out → items
     ▼
ForEachNode ── loop_body ──► PrintNode  ← item
     └── completed ──────► PrintNode  ← total
```

All pre-existing LangChain demo x-positions shifted +300 to avoid overlap.

---

### New Files

| File | Purpose |
|---|---|
| `python/graphs/foreach_demo.json` | Serialised example graph |
| `python/compiled_json/foreach_demo.py` | Compiled output (generated, do not edit) |
| `changes_210226.md` | This file |

---

### Verification

```
51 passed in 0.32s    ← python/test/ full suite
ForEachDemo found: True
ForEachNode registered: True
[ItemPrinter] Process step 1
[ItemPrinter] Process step 2
[ItemPrinter] Process step 3
[Done] 3
```
