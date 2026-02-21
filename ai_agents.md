# AI Agents Integration

## Overview

This document covers the LangChain node integration added to the Python server. LangChain node types are first-class nodes in the graph — the executor treats them identically to `AddNode` or `ForLoopNode`. Internally they drive OpenAI APIs and bridge per-step events (token chunks, tool calls, timing) into the trace system so the UI shows live activity.

---

## Architecture

```
Your NodeNetwork (Executor.py)
    │
    ├── ConstantNode, AddNode, ForLoopNode …  ← Your Executor handles these
    │
    ├── PromptTemplateNode   ← LangChain, no API call (pure string rendering)
    ├── TextSplitterNode     ← LangChain, no API call (pure text processing)
    │
    ├── LLMNode              ─┐
    ├── LLMStreamNode         ├─ OpenAI chat completion API
    ├── ToolAgentNode        ─┘
    │
    ├── EmbeddingNode        ← OpenAI embeddings API
    │
    └── [future] more node types...
```

The executor never calls LangChain directly — it simply calls `node.compute()` on each node, the same as any other node type. LangChain nodes:

1. Read values from their input ports
2. Call the relevant LangChain / OpenAI API
3. Write results to their output ports
4. Fire trace events (`STREAM_CHUNK`, `AGENT_STEP`, `NODE_DETAIL`) into `global_tracer` so the UI can display live activity in the Parameter Pane

---

## File Locations

| File | Purpose |
|---|---|
| `python/server/langchain_nodes.py` | All 6 LangChain node type definitions |
| `python/server/node_definitions.py` | Registers all nodes; imports `langchain_nodes` as side-effect |
| `python/server/state.py` | Seeds 3 demo subnetworks (`LLMPipeline`, `AgentDemo`, `EmbedSimilarity`) |
| `typescript/ui/src/types/traceTypes.ts` | `STREAM_CHUNK`, `AGENT_STEP`, `NODE_DETAIL` event types added |
| `typescript/ui/src/store/traceStore.ts` | Handles new events; `streamBuffer`, `agentSteps`, `detail` per node |
| `typescript/ui/src/components/canvas/ParameterPane.tsx` | Live streaming panel, agent step log, detail badges |

---

## Node Reference

### PromptTemplateNode
Renders a LangChain `PromptTemplate` string with a dict of variables. No API call.

| Port | Direction | Type | Default |
|---|---|---|---|
| `template` | input | string | `"Answer the following question: {question}"` |
| `variables` | input | any (dict or JSON string) | `{"question": "What is a node graph?"}` |
| `prompt` | output | string | rendered prompt |

**Example template:** `"You are a {role}. Answer in one sentence: {question}"`  
**Example variables:** `{"role": "physicist", "question": "What is entropy?"}`

---

### LLMNode
Single-shot blocking chat completion.

| Port | Direction | Type | Default |
|---|---|---|---|
| `prompt` | input | string | — |
| `system_prompt` | input | string | `"You are a helpful assistant."` |
| `model` | input | string | `"gpt-4o-mini"` |
| `temperature` | input | float | `0.7` |
| `response` | output | string | — |
| `model_used` | output | string | — |
| `tokens_used` | output | int | — |

**Trace events:** `EDGE_ACTIVE` (prompt → llm, llm → response), `NODE_DETAIL` (model, tokens, durationMs)

---

### LLMStreamNode
Streaming chat completion. Each token chunk fires a `STREAM_CHUNK` event — the UI Parameter Pane shows a live-updating response as tokens arrive.

| Port | Direction | Type | Default |
|---|---|---|---|
| `prompt` | input | string | — |
| `system_prompt` | input | string | `"You are a helpful assistant."` |
| `model` | input | string | `"gpt-4o-mini"` |
| `response` | output | string | full assembled response |
| `chunk_count` | output | int | number of token chunks received |

**Trace events:** `STREAM_CHUNK` (per token), `NODE_DETAIL` (model, chunks, durationMs)

---

### ToolAgentNode
ReAct-style agent with access to built-in tools. Each tool call fires an `AGENT_STEP` event visible as a collapsible log in the Parameter Pane.

| Port | Direction | Type | Default |
|---|---|---|---|
| `task` | input | string | — |
| `tools` | input | any (list of tool names) | `["calculator", "word_count"]` |
| `model` | input | string | `"gpt-4o-mini"` |
| `result` | output | string | agent's final answer |
| `tool_calls` | output | any (list of dicts) | per-step tool call log |
| `steps` | output | int | number of tool calls made |

**Built-in tools:**

| Tool name | Description |
|---|---|
| `calculator` | Evaluates a Python math expression string |
| `word_count` | Counts words in a text string |
| `web_search` | DuckDuckGo search (requires `langchain-community`) |

**Trace events:** `EDGE_ACTIVE` (task → agent, agent → result), `AGENT_STEP` (per tool call with input/output), `NODE_DETAIL` (steps, durationMs)

---

### EmbeddingNode
Converts text to a float vector embedding. Connects directly to `DotProductNode` for similarity comparisons.

| Port | Direction | Type | Default |
|---|---|---|---|
| `text` | input | string | — |
| `model` | input | string | `"text-embedding-3-small"` |
| `embedding` | output | vector (list[float]) | — |
| `dimensions` | output | int | 1536 or 3072 depending on model |

**Example pipeline:**
```
TextA → EmbeddingNode → (vec_a) ─┐
                                   ├─ DotProductNode → similarity score
TextB → EmbeddingNode → (vec_b) ─┘
```

**Trace events:** `EDGE_ACTIVE` (text → embedder, embedder → embedding), `NODE_DETAIL` (model, dimensions, durationMs)

---

### TextSplitterNode
Splits a long document into overlapping chunks using LangChain's `RecursiveCharacterTextSplitter`. No API call needed. First stage of a RAG pipeline.

| Port | Direction | Type | Default |
|---|---|---|---|
| `text` | input | string | — |
| `chunk_size` | input | int | `512` |
| `chunk_overlap` | input | int | `64` |
| `chunks` | output | any (list[str]) | — |
| `chunk_count` | output | int | — |

**Trace events:** `NODE_DETAIL` (chunkCount, chunkSize, overlap, totalChars)

---

## Demo Subnetworks

Three subnetworks are seeded automatically on server startup and visible in the root graph:

### LLMPipeline
```
PromptTemplateNode → LLMNode → PrintNode
```
Default question: `"What is a node graph?"`  
Default model: `gpt-4o-mini`, temperature 0.3

### AgentDemo
```
ConstantNode (task) → ToolAgentNode → PrintNode
```
Default task: `"What is 123 * 456? Then count the words in the answer."`  
Tools: `calculator`, `word_count`

### EmbedSimilarity
```
ConstantNode (TextA) → EmbeddingNode ─┐
                                        ├─ DotProductNode → PrintNode
ConstantNode (TextB) → EmbeddingNode ─┘
```
Default texts: `"The cat sat on the mat."` and `"A feline rested on a rug."`
(Semantically similar sentences — dot product will be high)

---

## Environment Variables

### Required

```bash
export OPENAI_API_KEY="sk-..."
```

Set before starting the Python server. LangChain-openai reads this automatically — no code changes needed.

### Optional

```bash
# Enable LangSmith tracing (LangChain's own observability dashboard)
export LANGCHAIN_TRACING_V2="true"
export LANGCHAIN_API_KEY="ls__..."
export LANGCHAIN_PROJECT="nodegraph"   # optional, defaults to "default"

# Point LangChain at a different OpenAI-compatible endpoint (e.g. Azure OpenAI)
export OPENAI_API_BASE="https://your-resource.openai.azure.com/"
export OPENAI_API_VERSION="2024-02-01"

# Increase timeout for slow models
export OPENAI_TIMEOUT="120"
```

LangSmith is completely optional. When enabled, every LLM call and tool invocation is automatically traced in LangSmith's dashboard at https://smith.langchain.com — separate from (and complementary to) the in-UI trace overlay.

---

## Dependencies

### Python (install once)

```bash
pip install langchain langchain-openai langchain-community langchain-text-splitters
```

The server starts cleanly without these — LangChain nodes are skipped at registration time with a printed warning. All non-LangChain nodes (`AddNode`, `ForLoopNode`, etc.) continue to work.

Full Python server requirements:
```bash
pip install fastapi "uvicorn[standard]" python-socketio python-multipart \
            langchain langchain-openai langchain-community langchain-text-splitters
```

### Node.js (already installed)
`socket.io-client` is already installed in `typescript/ui/`.

---

## Running

### 1. Set environment variables

```bash
export OPENAI_API_KEY="sk-..."
```

### 2. Start the Python server

Run from the **parent directory** of `nodegraph/` (i.e. `/Users/robertpringle/development/`) so Python resolves `nodegraph` as a package:

```bash
cd /Users/robertpringle/development
/usr/local/bin/python3 -m uvicorn nodegraph.python.server.main:socket_app \
    --port 3001 \
    --reload
```

`--reload` watches for file changes and restarts automatically — useful during development.

### 3. Start the frontend

```bash
cd /Users/robertpringle/development/nodegraph/typescript/ui
npm run dev
```

Vite will print a URL, typically `http://localhost:5173`.

### 4. Open the UI

Navigate to `http://localhost:5173`. The root graph loads automatically.  
Click into `LLMPipeline`, `AgentDemo`, or `EmbedSimilarity` to see the LangChain subnetworks.  
Hit **Execute** to run — the Parameter Pane will show live streaming output or agent tool-call steps as they happen.

---

## UI Trace Panels (Parameter Pane)

When a LangChain node is selected and executing:

**LLMStreamNode** — live token streaming panel appears:
```
⟳ STREAMING
A node graph is a directed acyclic graph where...
```

**ToolAgentNode** — agent step log appears:
```
AGENT STEPS
Step 1 — calculator
  in:  123 * 456
  out: 56088
Step 2 — word_count
  in:  56088
  out: 1
```

**All LangChain nodes** — detail badge strip appears at bottom:
```
model: gpt-4o-mini    tokens: 47    durationMs: 1243.5
```

---

## Design Decisions

### Why keep the existing Executor?

LangChain nodes are **opaque black boxes** to the executor — it just calls `compute()` and waits. The existing executor is kept because:

1. Non-LLM nodes (`ForLoopNode`, `DotProductNode`, etc.) don't benefit from LangGraph's state model
2. Your port system (typed, directional, control ports) is richer than LangGraph's flat `TypedDict` state
3. Step mode with port-level value inspection would be lost if replaced with LangGraph's `interrupt_before`
4. `ForLoopNode`'s `_loop_index` private state and `ExecutionCheckpoint` are more granular than LangGraph checkpointing

### Why not LangGraph for agent nodes?

LangGraph's `StateGraph` running **inside** a `LangGraphAgentNode` is the right next step for complex multi-step agents that need:
- Human-in-the-loop approval (`interrupt_before`)
- Cross-request conversation persistence (`thread_id` checkpointing)
- Dynamic fan-out via `send()`

The current `ToolAgentNode` uses LangChain's `AgentExecutor` (simpler, synchronous-ish model). Upgrade path: replace the `AgentExecutor` call inside `compute()` with a `StateGraph`, bridge LangGraph's `astream_events` into `global_tracer`, and pass `thread_id` through as a port value.

### Trace event bridge

LangChain's internal steps are normally invisible to external systems. The nodes explicitly bridge them:

```
LangChain internals         global_tracer.fire()        Socket.IO → UI
─────────────────────       ─────────────────────       ─────────────────
llm.astream() chunks    →   STREAM_CHUNK event      →   live text panel
tool call completes     →   AGENT_STEP event        →   step log entry
compute() finishes      →   NODE_DETAIL event       →   badge strip
```

---

## Known Gaps

| Gap | Notes |
|---|---|
| Checkpoint continuity | LangGraph internal state is lost on server restart; outer `ExecutionCheckpoint` is unaffected |
| No shared state between agent nodes | Data flows point-to-point via edges; use a shared `ConstantNode` as a context store if needed |
| LangSmith ↔ UI trace disconnect | Both work independently; no cross-correlation without a custom callback bridge |
| Human-in-the-loop | Not supported in current `AgentExecutor` approach; requires upgrading to `StateGraph` with `interrupt_before` |
| `web_search` tool | Requires `langchain-community` and a working internet connection; silently skipped if not installed |
