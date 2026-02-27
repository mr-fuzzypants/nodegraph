# Human-in-the-Loop: Analysis, Remediation & Running the Demo

## How it works today

### The node: `HumanInputNode`

`HumanInputNode.compute()` does the following when the executor calls it:

1. Creates a fresh `asyncio.Event` and stores it on `self._event`.
2. Registers itself in the class-level dict `HumanInputNode._pending[self.id] = self`.
3. Fires a `HUMAN_INPUT_REQUIRED` trace event so clients can react (e.g. show a modal).
4. Calls `await asyncio.wait_for(self._event.wait(), timeout=timeout)`.  
   This suspends **only this coroutine** — it does not block the event loop.
5. When `POST /api/nodes/{node_id}/human-input` arrives, the route calls `node.provide_response(text)`, which sets `self._response = text`, fires a `NODE_WAITING` trace event (phase=resuming), and calls `self._event.set()`.
6. `compute()` unblocks, removes the node from `_pending`, and returns `ExecutionResult(ExecCommand.WAIT)` with `control_outputs["responded"] = True` (or `"timed_out" = True` on timeout).
7. The scheduler detects `WAIT`, records it in `executor.waiting_nodes`, fires the `on_node_waiting` hook (-> `NODE_RESUMED` trace event), then routes control outputs normally via `_process_control_outputs`.

### Execution sequence

```
execute_node() called -> run_id generated -> executor stored in graph_state.active_executors
cook_flow_control_nodes enters -> batch = [Question, HumanIn] in execution_stack
  asyncio.gather launches both coroutines
    Question.compute() -> returns immediately, ExecCommand.CONTINUE
    HumanIn.compute()  -> fires HUMAN_INPUT_REQUIRED -> suspends at asyncio.wait_for(...)
  gather() waits for all coroutines to complete
    ...server is still alive and accepting requests...
  POST /api/nodes/{id}/human-input {"response":"Alice"} arrives
    provide_response("Alice") -> fires NODE_WAITING(phase=resuming) -> event.set()
    HumanIn.compute() unblocks -> returns ExecCommand.WAIT
  gather() collects both results
  result processing loop (scheduler):
    Question: command != LOOP_AGAIN, != WAIT -> _process_control_outputs (no edges, no-op)
    HumanIn:  command == "WAIT"
      -> executor.waiting_nodes[node_id] = result
      -> on_node_waiting hook fires -> NODE_RESUMED trace event emitted
      -> _process_control_outputs -> control_outputs["responded"]=True -> Output node pushed
      -> waiting_nodes[node_id] cleaned up
next batch = [Output]
  Output.compute() -> prints "Alice" -> execution ends
graph_state.active_executors.pop(run_id)  <- cleaned up in finally block
execute_node returns {"status": "ok", "runId": "..."}
```

---

## Gaps: Status

### Gap 1 - Scheduler blind to WAIT state - FIXED

**Was:** `ExecCommand.WAIT` fell through identically to `CONTINUE` with no branch check.

**Fix applied (`python/core/Executor.py`):**
Added `waiting_nodes: Dict[str, ExecutionResult]` and `on_node_waiting = None` to `Executor.__init__`.
Added WAIT branch in `cook_flow_control_nodes` after the LOOP_AGAIN check:

```python
elif result.command.name == "WAIT":
    self.waiting_nodes[cur_node.id] = result
    if self.on_node_waiting is not None:
        ret = self.on_node_waiting(cur_node.id, cur_node.name)
        if ret is not None and hasattr(ret, "__await__"):
            await ret
# _process_control_outputs follows (routing is correct -- compute already unblocked)
self.waiting_nodes.pop(cur_node.id, None)   # cleanup after routing
```

---

### Gap 2 - No execution identity (run_id) - FIXED

**Was:** No `run_id`, all concurrent executions shared `HumanInputNode._pending` keyed only by `node_id` — simultaneous executions would collide.

**Fix applied (`python/server/routes/graph_routes.py`, `python/server/state.py`):**
- `run_id = uuid.uuid4().hex` generated per execution.
- `graph_state.active_executors[run_id] = executor` stored before execution, removed in `finally`.
- `run_id` included in `EXEC_START`, `EXEC_DONE`, `EXEC_ERROR` trace events and in the HTTP response body.
- New `GET /api/executions/{run_id}/waiting` endpoint to introspect paused nodes.
- `active_executors: Dict[str, Any] = {}` added to `GraphState.__init__`.

---

### Gap 3 - No NODE_WAITING / NODE_RESUMED trace events - FIXED

**Was:** The trace stream had no events distinguishing a waiting node from a running one.

**Fix applied:**

| Event | Source | When |
|---|---|---|
| `HUMAN_INPUT_REQUIRED` | `HumanInputNode.compute()` | Before blocking — includes `nodeId` and `prompt` |
| `NODE_WAITING` (phase=resuming) | `HumanInputNode.provide_response()` | When human's response is received, before `compute()` returns |
| `NODE_RESUMED` | `_on_node_waiting` hook in `graph_routes.py` | After `compute()` returns WAIT, before routing outputs |

---

### Gap 4 - WAIT not durable across process restarts - NOT FIXED (out of scope)

The suspension is still held in an in-memory `asyncio.Event`. If the server process dies while `HumanInputNode` is waiting, the execution cannot be resumed. Addressing this requires:

1. A two-phase WAIT protocol where the node declares intent *before* `compute()` is called so the scheduler can snapshot state first.
2. Serialisation of the execution stack and port values to a durable store.
3. A `POST /executions/{run_id}/resume` endpoint that rehydrates a snapshot.

This is a separate workstream. The current in-process approach is the right starting point for experimenting with the semantics.

---

### Gap 5 - asyncio.Event | None syntax (Python 3.10+) - FIXED

**Was:** `self._event: asyncio.Event | None = None` — union syntax requires Python 3.10.

**Fix applied (`python/server/node_definitions.py`):**

```python
from typing import Dict as _Dict, Optional as _Optional
# ...
self._event: _Optional[asyncio.Event] = None
```

---

## Summary table

| # | Gap | Status | Notes |
|---|-----|--------|-------|
| 1 | Scheduler blind to WAIT | FIXED | WAIT branch + waiting_nodes + on_node_waiting hook |
| 2 | No execution identity (run_id) | FIXED | uuid4 per execution, active_executors dict, new waiting endpoint |
| 3 | No NODE_WAITING/NODE_RESUMED events | FIXED | Three distinct trace events at correct lifecycle points |
| 4 | WAIT not durable across restarts | DEFERRED | Requires two-phase protocol + durable store |
| 5 | asyncio.Event pipe None syntax | FIXED | Optional[asyncio.Event] from typing |

---

## Running the demo

### Prerequisites

Server running on port 3001:
```bash
cd /Users/robertpringle/development
/usr/local/bin/python3 -m uvicorn nodegraph.python.server.main:socket_app \
  --port 3001 --log-level warning
```

### Step 1 - Find the demo network and its root node

```bash
ROOT_ID=$(curl -s http://localhost:3001/api/networks/root | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -s "http://localhost:3001/api/networks/$ROOT_ID" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for n in d['nodes']:
    if 'Human' in n['name']:
        print('net id :', n['subnetworkId'])
        print('node   :', n['name'], '-', n['id'])
"
```

### Step 2 - Open the demo subnetwork, find node ids

```bash
HITL_NET_ID=<subnetworkId from above>
curl -s "http://localhost:3001/api/networks/$HITL_NET_ID" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for n in d['nodes']:
    print(n['name'], '|', n['type'], '|', n['id'])
"
```

Note the id of the **Question** node (ConstantNode) and the **HumanIn** node (HumanInputNode).

### Step 3 - Start execution (returns immediately with runId)

```bash
QUESTION_NODE_ID=<id of Question node>
curl -s -X POST \
  "http://localhost:3001/api/networks/$HITL_NET_ID/execute/$QUESTION_NODE_ID" | python3 -m json.tool
# -> {"status": "ok", "runId": "abc123..."}
```

The server prints:
```
[HumanInputNode 'HumanIn'] WAITING -- prompt: 'What is your name?'
```
Trace stream fires: `EXEC_START` -> `NODE_RUNNING` -> `HUMAN_INPUT_REQUIRED`

### Step 4 - (Optional) Inspect waiting nodes

```bash
RUN_ID=<runId from Step 3>
curl -s "http://localhost:3001/api/executions/$RUN_ID/waiting" | python3 -m json.tool
# -> {"runId": "abc123...", "waitingNodes": [{"nodeId": "...", "prompt": "What is your name?"}]}
# -> 404 if execution has completed or run_id is unknown
```

### Step 5 - Deliver the human response

```bash
HITL_NODE_ID=<id of HumanIn node from Step 2>
curl -s -X POST \
  "http://localhost:3001/api/nodes/$HITL_NODE_ID/human-input" \
  -H 'Content-Type: application/json' \
  -d '{"response": "Alice"}' | python3 -m json.tool
```

Full trace sequence:
1. `EXEC_START` (with runId)
2. `NODE_RUNNING` (Question)
3. `NODE_DONE` (Question)
4. `NODE_RUNNING` (HumanIn)
5. `HUMAN_INPUT_REQUIRED`
6. `NODE_WAITING` phase=resuming  <- fires when provide_response() called
7. `NODE_RESUMED`                 <- fires from scheduler on_node_waiting hook
8. `NODE_DONE` (HumanIn)
9. `NODE_RUNNING` (Output)
10. `NODE_DONE` (Output)
11. `EXEC_DONE` (with runId)

### Timeout path

If 60 s elapse with no response, `timed_out` fires instead of `responded` and the Timeout PrintNode executes.

---

## What remains to be done

| Item | Priority | Notes |
|---|---|---|
| **Dedicated tests** - `python/test/test_human_in_the_loop.py` | High | Cover: WAIT branch populates waiting_nodes; provide_response() unblocks routing; timeout fires timed_out; run_id cleanup in finally |
| **UI modal** - React component listening for HUMAN_INPUT_REQUIRED SSE event | Medium | Show input box when event fires; POST to /api/nodes/{id}/human-input; dismiss on NODE_RESUMED |
| **Concurrent-execution collision** | Medium | _pending keyed by node_id only -- if two executions run the same physical node simultaneously, provide_response() unblocks both. Fix: key by (node_id, run_id) tuple |
| **Durable WAIT** (Gap 4) | Low | Snapshot execution state to disk/DB so server can resume after restart |

---

## Test coverage

51 existing Python tests pass after all changes (`pytest python/test/` — 0.24 s). No dedicated human-in-the-loop test suite has been written yet (see "What remains" above).
