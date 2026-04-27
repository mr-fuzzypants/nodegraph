#!/usr/bin/env python3
"""
Compiled from NodeGraph: streaming-agent-simple
Generated:  2026-02-21

This file was produced by nodegraph.python.compiler2.
Do not edit by hand — re-run compile_graph() to regenerate.
"""
from __future__ import annotations

import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional

# ── LangChain tools ──────────────────────────────────────────────────────────
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """Evaluate a simple Python maths expression e.g. '2 + 3 * 4'."""
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as exc:
        return f"Error: {exc}"

@tool
def word_count(text: str) -> str:
    """Count the number of words in a text string."""
    return str(len(text.split()))

_TOOLS = {
    "calculator": calculator,
    "word_count": word_count,
}

async def _agent_event_stream(task: str, tool_names: list, model: str = "gpt-4o-mini"):
    """
    Async generator over meaningful LangGraph reasoning steps.
    Yields dicts with keys: step_type, tool_name, content.
      step_type == "tool_call"   — agent is about to call a tool
      step_type == "tool_result" — tool returned a result
      step_type == "final"       — agent produced the final answer
    """
    from langchain.agents import create_agent
    _tools = [_TOOLS[t] for t in tool_names if t in _TOOLS]
    agent  = create_agent(
        model=f"openai:{model}",
        tools=_tools,
        system_prompt="You are a helpful assistant that uses tools to complete tasks.",
    )
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": task}]},
        version="v2",
    ):
        kind = event.get("event", "")
        name = event.get("name",  "")
        data = event.get("data",  {})

        if kind == "on_tool_start":
            yield {"step_type": "tool_call",   "tool_name": name,
                   "content":   str(data.get("input", {}))[:300]}

        elif kind == "on_tool_end":
            out = data.get("output", "")
            if hasattr(out, "content"):
                out = out.content
            yield {"step_type": "tool_result", "tool_name": name,
                   "content":   str(out)[:300]}

        elif kind == "on_chain_end" and name == "LangGraph":
            msgs  = (data.get("output") or {}).get("messages", [])
            final = ""
            if msgs:
                last  = msgs[-1]
                final = last.content if hasattr(last, "content") else str(last)
            yield {"step_type": "final", "tool_name": "", "content": final}


# ── Graph: streaming-agent-simple ────────────────────────────
async def run() -> None:
    # Node: Task (ConstantNode)
    task_out = 'What is 123 * 456? Then count the words in the answer.'

    # Node: Agent (ToolAgentStreamNode)
    agent_step_type = ""
    agent_step_content = ""
    agent_tool_name = ""
    agent_step_count = 0
    agent_result = ""

    async for _step in _agent_event_stream(
        task=task_out,
        tool_names=['calculator', 'word_count'],
        model='gpt-4o-mini',
    ):
        agent_step_type    = _step.get('step_type',  '')
        agent_step_content = _step.get('content',    '')
        agent_tool_name    = _step.get('tool_name',  '')
        agent_step_count  += 1

        if agent_step_type == 'final':
            agent_result = agent_step_content
            break

        # Node: StepPrinter (StepPrinterNode)
        if agent_step_type == 'tool_call':
            print(f'  → {agent_tool_name}({agent_step_content})', flush=True)
        elif agent_step_type == 'tool_result':
            print(f'  ← {agent_step_content}', flush=True)
        else:
            print(f'  [{agent_step_type}] {agent_step_content}', flush=True)


    # Node: Output (PrintNode)
    print(f'[Output] ' + str(agent_result))


if __name__ == "__main__":
    asyncio.run(run())
