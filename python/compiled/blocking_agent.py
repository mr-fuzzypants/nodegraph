#!/usr/bin/env python3
"""
Compiled from NodeGraph: blocking-agent-simple
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

async def _run_agent(task: str, tool_names: list, model: str = "gpt-4o-mini") -> dict:
    """Run a blocking LangChain ReAct agent and return the result dict."""
    from langchain.agents import create_agent
    _tools = [_TOOLS[t] for t in tool_names if t in _TOOLS]
    agent  = create_agent(
        model=f"openai:{model}",
        tools=_tools,
        system_prompt="You are a helpful assistant that uses tools to complete tasks.",
    )
    output   = await agent.ainvoke({"messages": [{"role": "user", "content": task}]})
    messages = output.get("messages", [])
    tool_call_log, step_counter = [], 0
    tool_outputs: dict = {}
    for msg in messages:
        if type(msg).__name__ == "ToolMessage":
            tool_outputs[getattr(msg, "tool_call_id", "")] = str(msg.content)[:200]
    for msg in messages:
        if type(msg).__name__ == "AIMessage":
            for tc in getattr(msg, "tool_calls", []):
                step_counter += 1
                tname = tc.get("name", "")
                tid   = tc.get("id",   "")
                inp   = tc.get("args", {})
                out   = tool_outputs.get(tid, "")
                tool_call_log.append({"tool": tname, "input": inp, "output": out, "step": step_counter})
    final_content = ""
    if messages:
        last = messages[-1]
        final_content = last.content if hasattr(last, "content") else str(last)
    return {"result": final_content, "tool_calls": tool_call_log, "steps": step_counter}


# ── Graph: blocking-agent-simple ─────────────────────────────
async def run() -> None:
    # Node: Task (ConstantNode)
    task_out = 'What is 123 * 456? Then count the words in the answer.'

    # Node: Agent (ToolAgentNode — blocking)
    _agent_out    = await _run_agent(
        task=task_out,
        tool_names=['calculator', 'word_count'],
        model='gpt-4o-mini',
    )
    agent_result     = _agent_out["result"]
    agent_tool_calls = _agent_out["tool_calls"]
    agent_steps       = _agent_out["steps"]

    # Node: Output (PrintNode)
    print(f'[Output] ' + str(agent_result))



if __name__ == "__main__":
    asyncio.run(run())
