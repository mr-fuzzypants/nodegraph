"""
LangChain ToolAgent Example
----------------------------
Demonstrates a ToolAgentNode graph running through the NodeGraph executor:

    ConstantNode (task)
         │ out → task
         ▼
    ToolAgentNode  ── AGENT_STEP trace events per tool call ──►  (live log)
         │ result
         ▼
    PrintNode

The agent is given two tasks that exercise all built-in tools:
  1. Maths + word count  ("calculator" + "word_count")
  2. Pure maths chain    ("calculator")

Each tool call is printed live as it fires via the AGENT_STEP trace event,
and the full tool call log is printed at the end.

Run from the project root:

    cd /Users/robertpringle/development/nodegraph
    /usr/local/bin/python3 python/langchain_agent_example.py

Requirements:
    pip install langchain langchain-openai langchain-core langchain-community
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
from nodegraph.python.core.Executor import Executor

# Side-effect: registers all LangChain node types + built-in tools
import nodegraph.python.server.langchain_nodes  # noqa: F401
# Side-effect: registers ConstantNode, PrintNode, etc.
import nodegraph.python.server.node_definitions  # noqa: F401

from nodegraph.python.server.trace.trace_emitter import global_tracer


# ── Trace listener ────────────────────────────────────────────────────────────
# AGENT_STEP fires once per tool call — printed live as the agent reasons.

_step_seen: list[dict] = []

def _on_trace(event: dict) -> None:
    t = event.get("type", "")

    if t == "AGENT_STEP":
        step = event.get("step", "?")
        tool = event.get("tool", "?")
        inp  = event.get("input",  "")
        out  = event.get("output", "")
        print(f"  [{step}] {tool}")
        print(f"       input  → {inp}")
        print(f"       output → {out}")
        _step_seen.append(event)

    elif t == "NODE_DETAIL":
        d = event.get("detail", {})
        print(f"\n  Agent finished: {d.get('steps')} tool step(s) in {d.get('durationMs')}ms")

    elif t == "NODE_ERROR":
        print(f"\n[ERROR] {event.get('error', '')}", flush=True)


global_tracer.on_trace(_on_trace)


# ── Build the graph ───────────────────────────────────────────────────────────
#
#   ConstantNode("task")
#        │ out → task
#        ▼
#   ToolAgentNode
#        │ result → value
#        ▼
#   PrintNode

def build_network(task: str, tools: list[str]) -> tuple:
    net   = NodeNetwork.createRootNetwork("agent-demo", "NodeNetworkSystem")
    graph = net.graph

    # 1. Task source — a ConstantNode holding the task string
    task_node = net.createNode("Task", "ConstantNode")
    task_node.outputs["out"].value = task

    # 2. ToolAgentNode
    agent = net.createNode("Agent", "ToolAgentNode")
    agent.inputs["tools"].value = tools
    agent.inputs["model"].value = "gpt-4o-mini"

    # 3. PrintNode — displays the final agent response
    printer = net.createNode("Print", "PrintNode")

    # Wire up
    graph.add_edge(task_node.id, "out",    agent.id,   "task")
    graph.add_edge(agent.id,     "result", printer.id, "value")

    return net, agent


# ── Run one scenario ──────────────────────────────────────────────────────────

async def run_scenario(title: str, task: str, tools: list[str]) -> None:
    print("=" * 60)
    print(f"Scenario: {title}")
    print(f"Tools:    {tools}")
    print(f"Task:     {task}")
    print("─" * 60)
    print("Tool calls (live):")

    _step_seen.clear()

    net, agent_node = build_network(task, tools)
    executor = Executor(net.graph)

    # ToolAgentNode is a data node — use cook_data_nodes
    await executor.cook_data_nodes(agent_node)

    print()
    print("Final response:")
    print(f"  {agent_node.outputs['result'].value}")
    print()
    print(f"Tool call log ({agent_node.outputs['steps'].value} steps):")
    for step in agent_node.outputs["tool_calls"].value:
        print(f"  step {step['step']:>2}  {step['tool']:<15}  {step['input']}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print()
    print("NodeGraph · LangChain ToolAgent Demo")
    print()

    await run_scenario(
        title="Maths + word count",
        task=(
            "What is 123 * 456? "
            "Then count the number of words in your answer."
        ),
        tools=["calculator", "word_count"],
    )

    await run_scenario(
        title="Multi-step maths chain",
        task=(
            "Calculate (17 * 23) + (88 / 4). "
            "Then take that result and multiply it by 3."
        ),
        tools=["calculator"],
    )


if __name__ == "__main__":
    asyncio.run(main())
