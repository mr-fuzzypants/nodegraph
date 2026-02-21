"""
LangChain Streaming Agent Example
-----------------------------------
Demonstrates ToolAgentStreamNode alongside the original blocking ToolAgentNode
so you can compare the two side-by-side:

  BLOCKING  (ToolAgentNode)
      ConstantNode → ToolAgentNode → PrintNode
      Returns CONTINUE — entire ReAct loop runs internally, result at the end.

  STREAMING (ToolAgentStreamNode)
      ConstantNode → ToolAgentStreamNode ── loop_body ──► StepPrinterNode
                                         └── completed ──► PrintNode
      Returns LOOP_AGAIN per step — one executor iteration per tool_call /
      tool_result, then COMPLETED for the final answer.

Run from the project root:

    cd /Users/robertpringle/development/nodegraph
    /usr/local/bin/python3 python/langchain_agent_stream_example.py

Requirements:
    pip install langchain langchain-openai langchain-core langchain-community
    OPENAI_API_KEY must be set in .env at the project root.
"""
from __future__ import annotations

import asyncio
import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_NODEGRAPH   = os.path.abspath(os.path.join(_HERE, ".."))
_IMPORT_ROOT = os.path.abspath(os.path.join(_HERE, "../.."))

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
from nodegraph.python.core.Executor import Executor

import nodegraph.python.server.langchain_nodes  # noqa: F401  (LLM + agent nodes)
import nodegraph.python.server.node_definitions  # noqa: F401 (ConstantNode, PrintNode, StepPrinterNode)

from nodegraph.python.server.trace.trace_emitter import global_tracer


# ── Trace listener ────────────────────────────────────────────────────────────

def _on_trace(event: dict) -> None:
    t = event.get("type", "")
    if t == "NODE_ERROR":
        print(f"\n[ERROR] {event.get('error', '')}", flush=True)
    elif t == "NODE_DETAIL":
        d = event.get("detail", {})
        if "steps" in d:
            print(f"\n  Agent finished: {d['steps']} tool step(s)", flush=True)

global_tracer.on_trace(_on_trace)


# ── BLOCKING graph ────────────────────────────────────────────────────────────
#
#   ConstantNode
#        │ out → task
#        ▼
#   ToolAgentNode  (blocking — entire loop runs inside compute(), CONTINUE)
#        │ result → value
#        ▼
#   PrintNode

def build_blocking(task: str, tools: list[str]) -> tuple:
    net   = NodeNetwork.createRootNetwork("blocking-agent", "NodeNetworkSystem")
    graph = net.graph

    task_node = net.createNode("Task",   "ConstantNode")
    agent     = net.createNode("Agent",  "ToolAgentNode")
    printer   = net.createNode("Output", "PrintNode")

    task_node.outputs["out"].value = task
    agent.inputs["tools"].value    = tools
    agent.inputs["model"].value    = "gpt-4o-mini"

    graph.add_edge(task_node.id, "out",    agent.id,   "task")
    graph.add_edge(agent.id,     "result", printer.id, "value")
    return net, agent


# ── STREAMING graph ───────────────────────────────────────────────────────────
#
#   ConstantNode
#        │ out → task
#        ▼
#   ToolAgentStreamNode ── loop_body ──► StepPrinterNode  (per tool step)
#        └── completed ──────────────► PrintNode          (final answer)

def build_streaming(task: str, tools: list[str]) -> tuple:
    net   = NodeNetwork.createRootNetwork("streaming-agent", "NodeNetworkSystem")
    graph = net.graph

    task_node   = net.createNode("Task",        "ConstantNode")
    agent       = net.createNode("Agent",       "ToolAgentStreamNode")
    step_printer= net.createNode("StepPrinter", "StepPrinterNode")
    final_print = net.createNode("Output",      "PrintNode")

    task_node.outputs["out"].value = task
    agent.inputs["tools"].value    = tools
    agent.inputs["model"].value    = "gpt-4o-mini"

    graph.add_edge(task_node.id, "out",          agent.id,        "task")
    graph.add_edge(agent.id,     "loop_body",    step_printer.id, "exec")
    graph.add_edge(agent.id,     "step_type",    step_printer.id, "step_type")
    graph.add_edge(agent.id,     "step_content", step_printer.id, "step_content")
    graph.add_edge(agent.id,     "tool_name",    step_printer.id, "tool_name")
    graph.add_edge(agent.id,     "completed",    final_print.id,  "exec")
    graph.add_edge(agent.id,     "result",       final_print.id,  "value")

    return net, agent


# ── Run one comparison ────────────────────────────────────────────────────────

async def run_comparison(title: str, task: str, tools: list[str]) -> None:
    print("=" * 60)
    print(f"Task:  {task}")
    print(f"Tools: {tools}")
    print("=" * 60)

    # ── Blocking ─────────────────────────────────────────────────────────────
    print("\n[BLOCKING]  ToolAgentNode → waits for full result")
    print("─" * 40)
    b_net, b_agent = build_blocking(task, tools)
    b_exec = Executor(b_net.graph)
    await b_exec.cook_data_nodes(b_agent)
    print(f"\n  Final:  {b_agent.outputs['result'].value}")
    print(f"  Steps:  {b_agent.outputs['steps'].value}")

    # ── Streaming ─────────────────────────────────────────────────────────────
    print("\n[STREAMING] ToolAgentStreamNode → one step per loop iteration")
    print("─" * 40)
    s_net, s_agent = build_streaming(task, tools)
    s_exec = Executor(s_net.graph)
    await s_exec.cook_flow_control_nodes(s_agent)
    print(f"\n  Final:  {s_agent.outputs['result'].value}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print()
    print("NodeGraph · ToolAgent Blocking vs Streaming Comparison")
    print()

    await run_comparison(
        title="Maths + word count",
        task="What is 123 * 456? Then count the words in the answer.",
        tools=["calculator", "word_count"],
    )

    await run_comparison(
        title="Multi-step calculator chain",
        task=(
            "Calculate (17 * 23) + (88 / 4). "
            "Then take that result and multiply it by 3."
        ),
        tools=["calculator"],
    )


if __name__ == "__main__":
    asyncio.run(main())
