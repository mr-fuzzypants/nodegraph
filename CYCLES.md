# CYCLES.md — Cycle Safety in the NodeGraph Execution Engine

Graphs in this engine are conceptually directed acyclic graphs (DAGs), but the
execution model deliberately supports one class of cycle: **loop-mediated
back-edges**.  Understanding when a cycle is safe vs. unsafe is essential for
graph authors and node implementors.

---

## Table of Contents

1. [Core Rule](#1-core-rule)
2. [How the Executor Processes Nodes](#2-how-the-executor-processes-nodes)
3. [Safe Cycles — Mediated by a Loop Node](#3-safe-cycles--mediated-by-a-loop-node)
   - 3.1 WhileLoopNode — minimal single back-edge
   - 3.2 WhileLoopNode — inter-node data back-edge
   - 3.3 Nested loops
4. [Unsafe Cycles — Unmediated Data Dependencies](#4-unsafe-cycles--unmediated-data-dependencies)
   - 4.1 Self-loop
   - 4.2 Two-node mutual dependency
   - 4.3 Three-node dependency cycle
5. [Guards Implemented](#5-guards-implemented)
6. [Demo Networks](#6-demo-networks)
7. [Rule Summary Table](#7-rule-summary-table)

---

## 1. Core Rule

> **A cycle is safe if and only if every back-edge in the cycle passes through
> a flow-control loop node (WhileLoopNode, ForLoopNode, ForEachNode) that
> converts it into a deferred `LOOP_AGAIN` command.**

A back-edge that connects pure data nodes directly — without passing through a
loop node — creates a circular data dependency that the executor cannot resolve.
This is detected as a deadlock and raises a `RuntimeError`.

---

## 2. How the Executor Processes Nodes

The executor (`cook_flow_control_nodes` in `python/core/Executor.py`) uses three
stacks to manage execution:

| Stack | Purpose |
|---|---|
| `execution_stack` | Flow-control nodes ready to run now |
| `pending_stack` | Data nodes waiting for their upstream dependencies to be satisfied |
| `deferred_stack` | Loop nodes deferred via `LOOP_AGAIN` (LIFO — innermost first) |

**Execution life-cycle for a single flow step:**

```
1. Pop top entry from deferred_stack (LIFO)  → reload that loop's nodes
2. While execution_stack is non-empty:
   a. pop a flow-control node
   b. satisfy its data dependencies (cook pending_stack in topological order)
   c. run the node
   d. if result == LOOP_AGAIN → push to deferred_stack; remove this loop's
      nodes from execution_stack
   e. else push successor control nodes onto execution_stack
3. If pending_stack is still non-empty → deadlock → RuntimeError
```

The `LOOP_AGAIN` return value is what makes cycles safe: the loop node defers
itself and its body back onto the stack rather than completing, so the
dependency graph always remains acyclic at any single moment.

---

## 3. Safe Cycles — Mediated by a Loop Node

### 3.1 WhileLoopNode — minimal single back-edge

```
┌──────────────────────────────────────────────────────────┐
│                         SAFE                             │
│                                                          │
│   ┌────────────┐  loop_body   ┌────────────┐            │
│   │WhileLoop   │─────────────▶│  BodyNode  │            │
│   │            │              │            │            │
│   │ stop_signal│◀─────────────│stop_signal │            │
│   └────────────┘  ← back-edge └────────────┘            │
│          │                                              │
│       completed                                         │
│          ▼                                              │
│   ┌────────────┐                                        │
│   │   Done     │                                        │
│   └────────────┘                                        │
└──────────────────────────────────────────────────────────┘
```

**Why it is safe:**  
`WhileLoop` emits `LOOP_AGAIN` each time it fires `loop_body`.  The executor
pushes the loop node onto the `deferred_stack`.  After the body finishes, the
deferred entry re-expands the loop so `WhileLoop` runs again, reading the new
`stop_signal`.  The back-edge carries data *between* deferred iterations — it
never creates a simultaneous circular dependency.

**Key guarantee:** `WhileLoop` always fires `loop_body` on its very first
invocation (the stop condition check happens *after* the first iteration), so
even a loop wired to terminate immediately will execute the body once.

---

### 3.2 WhileLoopNode — inter-node data back-edge

The most powerful safe-cycle pattern: `NodeA` produces data that `NodeB`
consumes, and `NodeB`'s output is wired *back* as a new input to `NodeA` for
the next iteration.

```
┌──────────────────────────────────────────────────────────────┐
│                          SAFE                                │
│                                                              │
│  ┌──────────┐ loop_body  ┌──────────┐                       │
│  │WhileLoop │──────────▶ │ Counter  │                       │
│  │          │            │          │──next──┐              │
│  │stop_sig  │◀─stop_sig──│          │        ▼              │
│  └──────────┘            └──────────┘  ┌──────────┐        │
│       │                                │ Producer │        │
│    completed                           │          │──next──┐ │
│       ▼                                │ base_val │◀────── │ │
│  ┌──────────┐                          └──────────┘  ┌──────┐│
│  │  Done    │                                         │Consmr││
│  └──────────┘                          ▲             │      ││
│                                        └─── processed┤      ││
│                                              back-edge└──────┘│
└──────────────────────────────────────────────────────────────┘
```

`Consumer.processed → Producer.base_value` is the back-edge.  The data
propagation pipeline (`push_data_from_node`) runs *inside* a single loop
iteration after the loop node fires.  By the time that data tries to update
`Producer.base_value`, the current iteration's Producer has already run.  The
value takes effect in the *next* deferred iteration.

---

### 3.3 Nested loops

Loops may be freely nested.  The deferred stack is LIFO, so the **innermost**
loop is always popped and re-expanded first.  An outer loop does not resume
until the inner loop emits `COMPLETED` and drains from the deferred stack.

```
┌──────────────────────────────────────────────────────┐
│                       SAFE                           │
│                                                      │
│  ┌──────────┐ loop_body  ┌──────────┐               │
│  │  Outer   │──────────▶ │  Inner   │               │
│  │ (For/   │  (each iter)│ (For/   │               │
│  │  While)  │            │  While)  │               │
│  │          │◀──completed│          │               │
│  └──────────┘            └────┬─────┘               │
│                          loop_body                  │
│                               ▼                     │
│                         ┌──────────┐                │
│                         │   Body   │                │
│                         └──────────┘                │
└──────────────────────────────────────────────────────┘
```

**Rule:** Inner loop's `completed` edge must connect to the outer loop body's
*next* node (or be unconnected).  The outer loop must not have its own
`LOOP_AGAIN` check prematurely triggered by the inner loop.

---

## 4. Unsafe Cycles — Unmediated Data Dependencies

### 4.1 Self-loop

```
┌─────────────────────────────────┐
│            UNSAFE               │
│                                 │
│   ┌────────┐                    │
│   │ NodeA  │──out──┐            │
│   │        │       │            │
│   └────────┘◀──in──┘            │
│       self-loop                 │
└─────────────────────────────────┘

Raises: ValueError("Self-loop detected")
When: Graph.add_edge (build time, before execution)
```

Any edge where `from_node_id == to_node_id` is an immediate build-time error.
This check is in GraphPrimitives.add_edge.

---

### 4.2 Two-node mutual dependency

```
┌─────────────────────────────────────────┐
│                 UNSAFE                  │
│                                         │
│  ┌──────┐  sum ──▶  b  ┌──────┐        │
│  │ AddA │             │ AddB │        │
│  │      │  b  ◀── sum  │      │        │
│  └──────┘              └──────┘        │
│                                         │
│  Neither node can run first.            │
│  Raises: RuntimeError("deadlock ...")   │
│  When: executor, after constants are    │
│         consumed from pending_stack     │
└─────────────────────────────────────────┘
```

Even if constants feed the non-cyclic inputs (`AddA.a` and `AddB.a`), once
those constants are executed the remaining dependency `AddA←→AddB` has no
satisfiable ordering.

---

### 4.3 Three-node dependency cycle

```
┌───────────────────────────────────────────────────┐
│                     UNSAFE                        │
│                                                   │
│   ┌──────┐ sum ▶ a ┌──────┐ sum ▶ a ┌──────┐    │
│   │ AddA │         │ AddB │         │ AddC │    │
│   └──────┘         └──────┘         └──────┘    │
│      ▲                                   │       │
│      └──────────────── sum ◀─────────────┘       │
│                cycle closes here                 │
│                                                   │
│  If no constants feed any node in the cycle,      │
│  the executor's initial sweep produces an empty  │
│  execution_stack → deadlock guard fires at once. │
│  Raises: RuntimeError("deadlock ...")             │
└───────────────────────────────────────────────────┘
```

---

## 5. Guards Implemented

Three layers of protection are in place:

### Guard 1 — Self-loop check (build time)

Location: `python/core/GraphPrimitives.py`, `Graph.add_edge`

```python
if from_node_id == to_node_id:
    raise ValueError(f"Self-loop detected: node '{from_node_id}' cannot connect to itself.")
```

Fires immediately when the graph is built.  No execution is ever attempted.

---

### Guard 2 — DFS cycle detection in data dependency traversal

Location: `python/core/Executor.py`, `build_data_node_execution_stack`

```python
def build_data_node_execution_stack(self, node, execution_stack, pending_stack,
                                    _building: Optional[Set[str]] = None):
    if _building is None:
        _building = set()
    if node.id in _building:
        return          # cycle detected — stop recursion here
    _building.add(node.id)
    ...
    _building.discard(node.id)
```

When traversing upstream data dependencies, this prevents infinite recursion on
cyclic data graphs.  The node that would cause the cycle is still recorded in
`pending_stack` as a dependency — it just isn't traversed again.  This means
the deadlock detector (Guard 3) will see the unresolvable cycle and raise the
appropriate error.

---

### Guard 3 — Deadlock detector (runtime)

Location: `python/core/Executor.py`, `cook_flow_control_nodes`

```python
# After each execution batch (step 5):
if not execution_stack and not deferred_stack and pending_stack:
    waiting = {nid: list(deps) for nid, deps in pending_stack.items()}
    raise RuntimeError(
        f"Deadlock or circular dependency detected. "
        f"Nodes still waiting: {waiting}"
    )

# Final assertion at end of function:
if pending_stack:
    raise RuntimeError(
        f"Execution completed with unresolved node dependencies: "
        f"{list(pending_stack.keys())}"
    )
```

Two check points:
1. **Mid-loop**: catches deadlock as soon as the execution and deferred stacks
   are exhausted but pending work remains (covers the mutual-dependency case
   after constants are consumed).
2. **End of function**: catches any residual unresolved nodes as a final safety
   net.

---

## 6. Demo Networks

### ImageRefinementDemo — safe inter-node cycle

Registered in `python/server/state.py`.

```
┌─────────────────────────────────────────────────────────────────┐
│                    ImageRefinementDemo                          │
│                         SAFE                                    │
│                                                                 │
│  ┌──────────┐ loop_body   ┌────────────┐                       │
│  │WhileLoop │────────────▶│ HumanInput │                       │
│  │          │◀─stop_signal│  (WAIT)    │──────────────────┐    │
│  └──────────┘             └────────────┘   feedback        │    │
│       │                         │ response                  │    │
│    completed                    ▼                           │    │
│       ▼                  ┌────────────┐                     │    │
│   ┌──────────┐ next ──▶  │  Prompt    │                     │    │
│   │  Print   │           │  Refine   │◀────────────────────┘    │
│   │  URL     │           └────────────┘                          │
│   └──────────┘                 │ refined_prompt                  │
│                                ▼                                 │
│                         ┌────────────┐                          │
│                         │  ImageGen  │                          │
│                         └────────────┘                          │
│                                │ revised_prompt                  │
│                                └──────────────▶ PromptRefine     │
│                                    back-edge ← original_prompt   │
└─────────────────────────────────────────────────────────────────┘
```

**Back-edges:**
- `HumanInput.response → WhileLoop.stop_signal` (loop termination)
- `HumanInput.response → PromptRefine.feedback` (data for next refinement)
- `ImageGen.revised_prompt → PromptRefine.original_prompt` ← inter-node back-edge

**Safety:** Both back-edges flow *through* `WhileLoop`.  The `LOOP_AGAIN` defer
mechanism ensures `PromptRefine.original_prompt` is only read at the START of
the next iteration, by which point both upstream nodes have already finished
their current iteration.

---

### DeadlockCycleDemo — intentional deadlock for testing

Registered in `python/server/state.py`.

```
┌────────────────────────────────────────────────────────┐
│                   DeadlockCycleDemo                    │
│                       UNSAFE                           │
│                                                        │
│  ┌───────┐           ┌───────┐                        │
│  │Const5 │──▶ a ─▶   │ AddA  │──sum──▶ b ──▶ AddB ─┐  │
│  └───────┘           │       │                      │  │
│                      └───────┘◀─── sum ◀── AddB ◀──┘  │
│                                          │             │
│  ┌───────┐                              │             │
│  │Const3 │──────────────────▶ a ────▶── ┘             │
│  └───────┘                                             │
│                                                        │
│  Executing this network raises RuntimeError.           │
└────────────────────────────────────────────────────────┘
```

This network is intentionally broken to demonstrate the deadlock guard.
Load it from the UI and click "Run" to see the error surfaced in the trace.

---

## 7. Rule Summary Table

| Topology | Mediated by loop node? | Detected at | Error |
|---|---|---|---|
| Self-loop (A → A) | — | Build time | `ValueError("Self-loop")` |
| Two-node mutual dep (A ↔ B) | No | Runtime | `RuntimeError("deadlock…")` |
| Three-node cycle (A→B→C→A) | No | Runtime | `RuntimeError("deadlock…")` |
| WhileLoop body back-edge | **Yes** | — | ✅ Safe |
| ForLoop body back-edge | **Yes** | — | ✅ Safe |
| Nested loops | **Yes** | — | ✅ Safe |
| Inter-node back-edge inside loop | **Yes** | — | ✅ Safe |

**One sentence to remember:**

> Cycles are safe **only** when every back-edge is mediated by a loop node
> that converts it into a deferred `LOOP_AGAIN` command — never when raw data
> nodes depend on each other in a ring.
