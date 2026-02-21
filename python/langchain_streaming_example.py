"""
LangChain Streaming Example
----------------------------
Demonstrates LLMStreamNode behaving exactly like ForLoopNode:

  PromptTemplateNode
       │ prompt (data)
       ▼
  LLMStreamNode ──── loop_body ──► ChunkPrinterNode
       │  (LOOP_AGAIN per token)
       └── completed

Each call to LLMStreamNode.compute() pulls ONE token chunk from the OpenAI
stream and returns LOOP_AGAIN, driving ChunkPrinterNode once per token — the
same pattern as ForLoopNode → AccumulatorNode.  When the stream is exhausted,
COMPLETED is returned and the loop ends.

Run from the project root:

    cd /Users/robertpringle/development/nodegraph
    /usr/local/bin/python3 python/langchain_streaming_example.py

Requirements:
    pip install langchain langchain-openai langchain-core
    OPENAI_API_KEY must be set in .env at the project root.
"""
from __future__ import annotations

import asyncio
import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))    # .../nodegraph/python
_NODEGRAPH   = os.path.abspath(os.path.join(_HERE, ".."))    # .../nodegraph
_IMPORT_ROOT = os.path.abspath(os.path.join(_HERE, "../..")) # .../development

for _p in (_IMPORT_ROOT, _NODEGRAPH, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Load .env ─────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_NODEGRAPH, ".env"))
except ImportError:
    pass

# ── Core imports ──────────────────────────────────────────────────────────────
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodePort import (
    InputControlPort,
    InputDataPort,
    OutputControlPort,
    OutputDataPort,
)
from nodegraph.python.core.Types import ValueType
from nodegraph.python.core.Executor import Executor, ExecutionResult, ExecCommand

# Side-effect: registers all LangChain node types (including new LLMStreamNode)
import nodegraph.python.server.langchain_nodes  # noqa: F401
# Side-effect: registers PrintNode, AccumulatorNode, etc.
import nodegraph.python.server.node_definitions  # noqa: F401

from nodegraph.python.server.trace.trace_emitter import global_tracer


# ── ChunkPrinterNode ──────────────────────────────────────────────────────────
# Inline flow-control node wired to LLMStreamNode's loop_body port.
# Fires once per token, just like AccumulatorNode fires once per loop index.

def _register_chunk_printer():
    if "ChunkPrinterNode" in Node._node_registry:
        return

    class ChunkPrinterNode(Node):
        def __init__(self, name: str, type: str = "ChunkPrinterNode", **kwargs):
            super().__init__(name, type, **kwargs)
            self.is_flow_control_node = True
            self.inputs["exec"]   = InputControlPort(self.id, "exec")
            self.inputs["chunk"]  = InputDataPort(self.id, "chunk", ValueType.STRING)
            self.outputs["next"]  = OutputControlPort(self.id, "next")

        async def compute(self, executionContext=None) -> ExecutionResult:
            chunk = self.inputs["chunk"].value or ""
            print(chunk, end="", flush=True)
            result = ExecutionResult(ExecCommand.CONTINUE)
            result.control_outputs["next"] = True
            return result

    Node._node_registry["ChunkPrinterNode"] = ChunkPrinterNode

_register_chunk_printer()


# ── Trace listener ────────────────────────────────────────────────────────────

def _on_trace(event: dict) -> None:
    t = event.get("type", "")
    if t == "NODE_DETAIL":
        d = event.get("detail", {})
        print(
            f"\n\n[DONE] model={d.get('model')}  "
            f"chunks={d.get('chunks')}  "
            f"chars={d.get('characters')}"
        )
    elif t == "NODE_ERROR":
        print(f"\n[ERROR] {event.get('error', '')}", flush=True)


global_tracer.on_trace(_on_trace)


# ── Build the graph ───────────────────────────────────────────────────────────
#
#   PromptTemplateNode  (data node — resolves template)
#        │ prompt
#        ▼
#   LLMStreamNode  ──── loop_body (control) ──► ChunkPrinterNode
#        └──────────── chunk (data) ──────────────┘
#        └── completed  (loop ends)

def build_network():
    net   = NodeNetwork.createRootNetwork("streaming-demo", "NodeNetworkSystem")
    graph = net.graph

    # 1. PromptTemplateNode
    tmpl = net.createNode("Template", "PromptTemplateNode")
    tmpl.inputs["template"].value  = (
        "You are a concise technical writer. "
        "Answer in 3-4 sentences: {question}"
    )
    tmpl.inputs["variables"].value = {
        "question": "What is a node graph and how does it enable data-flow programming?"
    }

    # 2. LLMStreamNode — LOOP_AGAIN once per token, COMPLETED when done
    stream = net.createNode("StreamLLM", "LLMStreamNode")
    stream.inputs["model"].value         = "gpt-4o-mini"
    stream.inputs["system_prompt"].value = "You are a helpful assistant."

    # 3. ChunkPrinterNode — runs once per loop iteration (per token)
    printer = net.createNode("Printer", "ChunkPrinterNode")

    # Data edge: template fills the prompt
    graph.add_edge(tmpl.id,   "prompt",    stream.id,  "prompt")
    # Control edge: loop_body fires the printer on every LOOP_AGAIN
    graph.add_edge(stream.id, "loop_body", printer.id, "exec")
    # Data edge: current token chunk flows to the printer
    graph.add_edge(stream.id, "chunk",     printer.id, "chunk")

    return net, stream


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    net, stream_node = build_network()
    executor = Executor(net.graph)

    print("=" * 60)
    print("NodeGraph · LangChain Streaming Demo (ForLoop-style)")
    print("=" * 60)
    print()
    print("Graph:")
    print("  PromptTemplateNode")
    print("       │ prompt")
    print("       ▼")
    print("  LLMStreamNode ── loop_body ──► ChunkPrinterNode")
    print("       └── completed")
    print()
    print("─" * 60)
    print("Response (one token per executor loop iteration):")
    print()

    # Flow-control path — LLMStreamNode drives the loop via LOOP_AGAIN
    await executor.cook_flow_control_nodes(stream_node)

    print()
    print("─" * 60)
    print("Accumulated response (from stream_node.outputs['response']):")
    print(stream_node.outputs["response"].value)


if __name__ == "__main__":
    asyncio.run(main())
