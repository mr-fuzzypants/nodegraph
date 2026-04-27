# NodeGraph TypeScript Port — Notes

## What Was Accomplished

### 1. Full TypeScript port of the Python core

All seven files in `python/core/` were ported to `typescript/src/core/` with function and method names preserved exactly:

| Python | TypeScript |
|--------|-----------|
| `Types.py` | `Types.ts` |
| `Interface.py` | `Interface.ts` |
| `NodePort.py` | `NodePort.ts` |
| `GraphPrimitives.py` | `GraphPrimitives.ts` |
| `Node.py` | `Node.ts` |
| `Executor.py` | `Executor.ts` |
| `NodeNetwork.py` | `NodeNetwork.ts` |

Notable translation decisions:
- Python `@PluginRegistry.register` → TypeScript `@Node.register('TypeName')` (decorator factory using a static `Map` on the `Node` class)
- Python `defaultdict(list)` for edge maps → `Map<string, Edge[]>` with explicit initialisation
- Python `asyncio.gather()` → `Promise.all()`
- Python `uuid.uuid4().hex` → `uuidv4().replace(/-/g, '')`
- Python `@staticmethod` → TypeScript `namespace` block on the same enum (e.g. `ValueType.validate(...)`)

### 2. All pytest tests ported to Jest

Six pytest files were ported to Jest + ts-jest. All 47 tests pass:

| Pytest file | Jest file |
|-------------|-----------|
| `test_nodes.py` | `test/test_nodes.test.ts` |
| `test_node_ports.py` | `test/test_node_ports.test.ts` |
| `test_node_cooking.py` | `test/test_node_cooking.test.ts` |
| `test_node_network.py` | `test/test_node_network.test.ts` |
| `test_node_cooking_flow.py` | `test/test_node_cooking_flow.test.ts` |
| `test_loop_node.py` | `test/test_loop_node.test.ts` |

### 3. HTTP server exposing the graph engine

An Express server (`server/`) wraps the TypeScript core and exposes a REST API. It holds all graph state in memory as live `NodeNetwork` instances, serialising them to JSON on demand.

### 4. ReactFlow UI

A Vite + React 18 + `@xyflow/react` UI (`typescript/ui/`) visualises graphs returned by the server. It supports:
- Browsing and editing the root network
- Navigating into subnetworks and back via a breadcrumb
- Split-pane layout (`SplitManager`) — multiple graph views side-by-side
- Creating nodes from a palette and wiring them together
- Triggering execution on individual nodes
- Editing port values in a dedicated `ParameterPane`

### 5. Real-time execution tracing

A WebSocket channel (`ws://localhost:3001/ws/trace`) streams fine-grained execution events from the server to the UI in real time:

- **`TraceEmitter`** (`server/src/trace/TraceEmitter.ts`) — singleton event bus. Fires typed `TraceEvent` objects; also manages the step-mode pause queue.
- **`wsServer.ts`** — attaches a `WebSocketServer` to the HTTP server and fans every `TraceEvent` out to all connected clients.
- **`traceTypes.ts`** — shared event union: `EXEC_START`, `NODE_PENDING`, `NODE_RUNNING`, `NODE_DONE`, `NODE_ERROR`, `EDGE_ACTIVE`, `EXEC_DONE`, `EXEC_ERROR`, `STEP_PAUSE`.
- **`useTraceSocket`** (`typescript/ui/src/hooks/useTraceSocket.ts`) — React hook that opens the WebSocket, reconnects on disconnect, and forwards events to a callback.
- **`traceStore`** (`typescript/ui/src/store/traceStore.ts`) — Zustand store holding per-node `NodeTraceState` (`pending` / `running` / `paused` / `done` / `error`) and active edge highlights.
- **Node glow** — `FunctionNode` and `NetworkNode` apply a colour-coded box-shadow and a status badge based on trace state:
  - `pending` → indigo `#818cf8`
  - `running` → yellow `#facc15` + ⏳ badge
  - `paused` → orange `#f97316` + ⏸ wait badge
  - `done` → green `#4ade80` + ✓ Xms badge
  - `error` → red `#f87171` + ✕ err badge
- **Edge flash** — `EDGE_ACTIVE` events highlight the corresponding ReactFlow edge for 1.2 s.

### 6. Step-by-step execution mode

When step mode is active, execution pauses before each node so the user can inspect state and advance one node at a time.

**Server side:**
- `TraceEmitter.enableStep()` / `disableStep()` toggle step mode around a single execution run.
- `TraceEmitter.waitForStep()` appends a resolver to a queue (`_resumeQueue`); `resume()` drains the entire queue at once (handles concurrent upstream data dependencies correctly).
- `Executor.onBeforeNode` is an `async` hook called before every node in both `cook_flow_control_nodes` and `cook_data_nodes`. In step mode it fires `STEP_PAUSE` then `await globalTracer.waitForStep()`.
- `POST /api/step/resume` unblocks the executor. Using REST (not a WS message back to the server) ensures reliable delivery through the Vite proxy.
- `?step=true` query parameter on the execute route opts into step mode for that run.

**Client side:**
- **Step Mode toggle** in the `App.tsx` header enables/disables the flag stored in `traceStore`.
- When `isPaused === true` a pulsing **▶ Step** button appears in the header. Clicking it calls `graphClient.stepResume()` (`POST /api/step/resume`). The button hides when the server's `NODE_RUNNING` event arrives (not optimistically), so a failed request is immediately retryable.
- `stepModeEnabled` is read from `traceStore` by `paneStore.executeNode` and passed as the `step` flag to `graphClient.execute()`.

### 7. Loop example graphs

**`LoopDemo`** subnetwork in `state.ts` demonstrates the basic flow-control execution path:
- **`ForLoopNode`** — iterates `start`..`end` (exclusive), emitting `loop_body` control + current `index` data on each iteration, then `completed`.
- **`AccumulatorNode`** — flow-control node that records every `val` it receives, tracking `callCount` and `values[]`.
- Wired as: `ForLoopNode.loop_body → AccumulatorNode.exec`, `ForLoopNode.index → AccumulatorNode.val`.

**`ParallelNestedLoopDemo`** in `state.ts` demonstrates two parallel nested-loop branches fired from a single `PrintNode`:
- Branch A: `OuterA (0→2) → InnerA (0→3) → AccumulatorA` — expected `AccumulatorA.callCount = 6`.
- Branch B: `OuterB (0→3) → InnerB (0→2) → AccumulatorB` — expected `AccumulatorB.callCount = 6`.
- Both branches run in parallel (same `executionStack` batch, `Promise.all`); loop iterations within each branch are serialised by the LIFO deferred stack.

### 8. LIFO deferred stack for nested loops

`cook_flow_control_nodes` uses a LIFO `deferredStack` (pop from the end) for loop re-entries.

**Why LIFO?** Loop re-entry entries are pushed in temporal order — the outer loop fires first and pushes itself (tick 1), then the inner loop fires and pushes itself (tick 2). `pop()` always yields the most-recently-pushed entry, which is the innermost loop. This guarantees inner loops complete all their iterations before the outer loop advances to its next iteration:

```
OuterLoop iter 0 → deferredStack=[Outer], exec=[Inner]
InnerLoop iter 0 → deferredStack=[Outer,Inner], exec=[Counter]
Counter done → pop() gives Inner  ← correct
InnerLoop iter 1 → deferredStack=[Outer,Inner], exec=[Counter]
Counter done  → pop() gives Inner again
InnerLoop COMPLETED → deferredStack=[Outer]
pop() gives Outer  → outer iter 1 starts fresh
```

FIFO (`shift`) instead gives `Outer` from the front when `Counter` drains, firing the second outer iteration before the inner loop finishes.

### 9. Step into / out of subnetworks while debugging

`GraphPane.tsx` shows navigation buttons in the pane header when execution is paused:

- **`⤴ Out`** — visible when the breadcrumb depth is > 1. Calls `exitTo(breadcrumb.length - 2)` to step back up one level.
- **`⤵ Into [Name]`** — visible when a `NetworkNode` is selected or is the `pausedAtNodeId`. Glows orange while paused to indicate it is the active pause site.

Both buttons read from `useTraceStore` (`isPaused`, `pausedAtNodeId`) so they only appear when relevant.

### 10. Node state serialisation (`serializeState` / `deserializeState`)

The `Node` base class (`typescript/src/core/Node.ts`) gained two overridable methods:

```typescript
serializeState(): Record<string, unknown>
deserializeState(state: Record<string, unknown>): void
```

The base implementation captures all port values, keyed as `out:<portName>` for outputs and `in:<portName>` for inputs. Subclasses extend it by spreading `super.serializeState()` and appending any private fields:

```typescript
// ForLoopNode example
serializeState() {
  return { ...super.serializeState(), _loopIndex: this._loopIndex, _loopActive: this._loopActive };
}
```

`ForLoopNode` was also refactored from `_currentIndex: number | null` (null-as-sentinel) to explicit `_loopIndex = 0` + `_loopActive = false` fields, which are unambiguous during serialisation/deserialisation and easier to reason about when resuming a checkpoint. A typo `looop_body` in the `COMPLETED` branch was fixed to `loop_body` at the same time.

### 11. Resumable execution via `ExecutionCheckpoint`

`Executor.ts` now exports an `ExecutionCheckpoint` interface and the `Executor` class has an `onCheckpoint?` hook:

```typescript
export interface ExecutionCheckpoint {
  rootNodeId:     string;
  networkId:      string;
  executionStack: string[];
  deferredStack:  string[];   // LIFO order preserved
  pendingStack:   Record<string, string[]>;
  completedNodes: string[];
  nodeStates:     Record<string, Record<string, unknown>>;  // via serializeState()
  failedNodeId:   string | null;
  failedError:    string | null;
  timestamp:      number;
}
```

**Checkpoint emission:**
- After every successfully completed batch `completedNodes` is extended and `onCheckpoint` is called with a full snapshot.
- If `Promise.all(tasks)` throws, an error checkpoint is emitted first (with `failedNodeId` set when the failing batch contained exactly one node) and then the error is re-thrown.

**Checkpoint restore:**
- Pass an `ExecutionCheckpoint` as the optional fourth argument to `cook_flow_control_nodes`. All stacks are re-seeded from the snapshot, `deserializeState` is called for every previously-completed node, and the same `while` loop continues from where execution diverged — no work is repeated.

---

## Architectural Overview

```
nodegraph/
├── python/core/          ← Reference implementation (unchanged)
├── typescript/
│   ├── src/core/         ← TypeScript port of the core engine
│   │   ├── Types.ts          Enums: PortDirection, PortFunction, ValueType, NodeKind
│   │   ├── Interface.ts      Abstract base classes (INode, INodePort, IExecutionContext…)
│   │   ├── NodePort.ts       Concrete port types (InputDataPort, OutputControlPort…)
│   │   ├── GraphPrimitives.ts  Edge, GraphNode, Graph (Arena pattern)
│   │   ├── Node.ts           Abstract Node base with static registry + factory
│   │   │                     serializeState() / deserializeState() for checkpoint support
│   │   ├── Executor.ts       Async graph traversal: cook_data_nodes / cook_flow_control_nodes
│   │   │                     onBeforeNode / onAfterNode / onCheckpoint / onEdgeData async hooks
│   │   │                     ExecutionCheckpoint interface — LIFO deferred stack, per-batch snapshots
│   │   ├── NodeNetwork.ts    Composite node that owns a Graph and acts as a node factory
│   │   └── index.ts          Barrel export
│   ├── test/             ← Jest test suite (47 tests, all passing)
│   └── ui/               ← React + ReactFlow frontend
│       └── src/
│           ├── api/graphClient.ts      Typed axios wrapper for all server endpoints
│           ├── store/
│           │   ├── graphStore.ts       Zustand — graph state, navigation, CRUD
│           │   ├── paneStore.ts        Zustand — per-pane state (active network, execute)
│           │   └── traceStore.ts       Zustand — live trace state (node glows, edge flashes)
│           ├── hooks/
│           │   └── useTraceSocket.ts   WebSocket hook → traceStore
│           ├── types/
│           │   ├── uiTypes.ts          Shared UI-only types
│           │   └── traceTypes.ts       TraceEvent union (mirrors server)
│           ├── components/
│           │   ├── nodes/
│           │   │   ├── FunctionNode.tsx    Leaf node (data + flow-control) with trace glow
│           │   │   └── NetworkNode.tsx     Subgraph node with trace glow + "⤵ Enter"
│           │   └── canvas/
│           │       ├── GraphCanvas.tsx     ReactFlow canvas + node palette
│           │       ├── GraphPane.tsx       Pane header with ⤴ Out / ⤵ Into step-debug nav
│           │       ├── BreadcrumbNav.tsx   Hierarchical navigation bar
│           │       ├── SplitManager.tsx    Split-pane layout manager
│           │       └── ParameterPane.tsx   Port value editor panel
│           └── App.tsx                 Header (step mode controls) + SplitManager
└── server/               ← Express HTTP server
    └── src/
        ├── main.ts               App entry point (port 3001)
        ├── state.ts              Singleton GraphState — live NodeNetwork instances + positions
        ├── nodeDefinitions.ts    Registered demo nodes (ConstantNode, AddNode, MultiplyNode,
        │                         ForLoopNode, AccumulatorNode, BranchNode, PrintNode…)
        ├── serializers/
        │   └── graphSerializer.ts  Converts NodeNetwork → JSON wire format
        ├── trace/
        │   ├── TraceEmitter.ts   Singleton event bus + step-mode pause queue
        │   ├── wsServer.ts       WebSocket fan-out of TraceEvents to all clients
        │   └── traceTypes.ts     Authoritative TraceEvent union type
        └── routes/
            └── graphRoutes.ts    All REST endpoints
```

### Data flow

```
┌─────────────────────┐    REST / JSON (axios)    ┌──────────────────────┐
│   React UI          │ ◄──────────────────────► │   Express Server     │
│   (port 5173)       │                           │   (port 3001)        │
│                     │  WS (trace events only)   │                      │
│  traceStore         │ ◄──────────────────────   │  TraceEmitter        │
│  graphStore         │                           │  wsServer            │
│  paneStore          │                           │                      │
│  ReactFlow canvas   │  POST /api/step/resume    │  GraphState          │
│  ParameterPane      │ ──────────────────────►   │  ├─ NodeNetwork tree │
│  SplitManager       │                           │  └─ position map     │
└─────────────────────┘                           │                      │
                                                  │  TypeScript core     │
                                                  │  ├─ Node             │
                                                  │  ├─ NodeNetwork      │
                                                  │  ├─ Graph            │
                                                  │  └─ Executor         │
                                                  └──────────────────────┘
```

### REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/api/networks/root` | Root network id + name |
| `GET` | `/api/networks` | List all networks (id, name, path, parentId) |
| `GET` | `/api/networks/:id` | Full serialised graph |
| `POST` | `/api/networks/:id/networks` | Create subnetwork |
| `POST` | `/api/networks/:id/nodes` | Create node |
| `DELETE` | `/api/networks/:id/nodes/:nodeId` | Delete node |
| `POST` | `/api/networks/:id/edges` | Add edge |
| `DELETE` | `/api/networks/:id/edges` | Remove edge |
| `PUT` | `/api/networks/:id/nodes/:nodeId/position` | Persist layout position |
| `PUT` | `/api/networks/:id/nodes/:nodeId/ports/:portName` | Set port value |
| `GET` | `/api/node-types` | List registered node type names |
| `POST` | `/api/networks/:id/execute/:nodeId` | Execute from a node (`?step=true` for step mode) |
| `POST` | `/api/step/resume` | Unblock executor in step mode |

### WebSocket

| URL | Direction | Description |
|-----|-----------|-------------|
| `ws://localhost:3001/ws/trace` | Server → Client | Stream of `TraceEvent` objects during execution |

---

## How to Run

### Prerequisites
- Node.js ≥ 18
- All dependencies installed (see steps below)

### 1. Install dependencies

```bash
# Core TypeScript library + tests
cd typescript && npm install

# Server
cd ../server && npm install

# UI
cd ../typescript/ui && npm install
```

### 2. Run the tests

```bash
cd typescript
npm test
# Expected: 47 tests, 6 suites, all passing
```

### 3. Start the server

```bash
cd server
node_modules/.bin/ts-node-transpile-only src/main.ts
# Listening on http://localhost:3001
```

### 4. Start the UI

In a separate terminal:

```bash
cd typescript/ui
npm run dev
# Open http://localhost:5173
```

The UI proxies `/api` requests to the server via Vite's dev proxy (configured in `vite.config.ts`).

### 5. Build for production

```bash
# Build the UI
cd typescript/ui && npm run build

# Build the server
cd server && node_modules/.bin/tsc
node dist/main.js
```

### Adding new node types

1. Create a class in `server/src/nodeDefinitions.ts` (or a new file imported from there):

```typescript
@Node.register('MyNode')
class MyNode extends Node {
  constructor(id: string, type = 'MyNode', networkId: string | null = null) {
    super(id, type, networkId);
    this.inputs['in'] = new InputDataPort(this.id, 'in', ValueType.INT);
    this.outputs['out'] = new OutputDataPort(this.id, 'out', ValueType.INT);
  }

  async compute(ctx?: any): Promise<ExecutionResult> {
    const val = (this.inputs['in'] as any).value ?? 0;
    const result = new ExecutionResult(ExecCommand.CONTINUE);
    result.data_outputs['out'] = val * 2;
    return result;
  }
}
```

2. Restart the server — `GET /api/node-types` will include `"MyNode"` and the palette will show it automatically.

---

## Suggestions for Further Improvement

### Code quality

1. **Enable `strict: true`** in both `typescript/tsconfig.json` and `server/tsconfig.json`. This surfaces latent `null` / `undefined` bugs and makes the codebase self-documenting. The main changes required are adding explicit null guards and tightening `any` types.

2. **Replace `any` with proper types in `Executor.ts`**. The `executionContext` dictionary and `pendingStack` map are typed as `any` throughout. Introducing `ExecutionContextDict` and `PendingStack` interfaces would make the execution pipeline easier to reason about and extend.

3. **Remove debug `console.log` calls from production code**. The core and server files contain dozens of verbose log lines ported from Python development. Replace with a lightweight logger (e.g. the `debug` package) gated on a `DEBUG` environment variable so tests run silently and production is quiet.

### Testing

4. **Isolate the Node registry between tests**. Node types are registered into a global static `Map` on the `Node` class. If two test files register the same type name, they silently overwrite each other. Snapshot and restore the registry in `beforeAll`/`afterAll`, or make the registry injectable so it can be mocked per-test.

5. **Add server integration tests**. The server has no test suite. Use `supertest` against the Express app to cover the REST routes without needing a live network.

### Architecture

6. **Persist state to disk**. Graph state is held in memory and lost on server restart. Serialise the `GraphState` to a JSON file (or SQLite via `better-sqlite3`) on every mutation and reload it on startup.

7. ~~**WebSocket push for live execution**~~ — **Done.** A `ws` WebSocket server fans `TraceEvent` objects to the UI in real time. Node glow, edge flash, and step mode are all driven by this channel.

7b. ~~**Nested loop correctness (LIFO deferred stack)**~~ — **Done.** See §8 above.

7c. ~~**Step into / out of subnetworks while debugging**~~ — **Done.** See §9 above.

7d. ~~**Resumable execution via `ExecutionCheckpoint`**~~ — **Done.** See §§10–11 above.

8. **Extract node type definitions to a shared package**. Node type names and port schemas are currently defined only in `server/src/nodeDefinitions.ts`. Moving them to a shared `packages/node-types` workspace package would allow the UI to render accurate port metadata without an extra API round-trip.

9. **Fix the global `Graph` node registry**. The `Graph` class stores every node ever created in a static `Map`, which grows unboundedly in long-running processes. Replace it with per-instance scope and explicitly remove entries in `deleteNode`.

### UI

10. ~~**Editable port values in the canvas**~~ — **Done.** `ParameterPane.tsx` renders an editor panel for the selected node's input port values.

10b. ~~**Step into/out of subnetwork nodes while paused**~~ — **Done.** `GraphPane.tsx` shows `⤴ Out` / `⤵ Into` buttons when `isPaused`, driven by `useTraceStore`.

11. **Context menu for nodes**. Right-click on a node should offer: Delete, Edit name, Enter (for network nodes), Execute, and Inspect current output values.

12. **Undo / redo**. The Zustand store mutates state directly. Wrapping mutations with `zundo` (a Zustand undo middleware) would add undo/redo with minimal changes.

13. **Auto-layout**. When a new graph is loaded the nodes can overlap. Applying a simple Dagre or ELK layout pass as a post-fetch step would make large graphs readable immediately.

14. **Step mode — multi-execution concurrency guard**. Currently a second `POST .../execute` call while one is already paused in step mode would share the same `TraceEmitter` queue, causing undefined interleaving. Add an `isRunning` guard on the server route (return 409) to prevent concurrent runs.
