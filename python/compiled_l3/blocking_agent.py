#!/usr/bin/env python3
"""
Compiled from NodeGraph: blocking-agent-simple
Generated:  2026-02-21

Level 3 / Zero-Framework output.
Dependencies: pip install openai python-dotenv
No langchain, langgraph, or nodegraph runtime required.

This file was produced by nodegraph.python.compiler3.
Do not edit by hand — re-run compile_graph_l3() to regenerate.
"""
from __future__ import annotations

import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — set OPENAI_API_KEY in environment manually

import json as _json
from openai import AsyncOpenAI as _AsyncOpenAI

_client = _AsyncOpenAI()

# ── Tools ───────────────────────────────────────────────────────────────────────
def calculator(expression: str) -> str:
    """Evaluate a simple Python maths expression e.g. '2 + 3 * 4'."""
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as exc:
        return f"Error: {exc}"

def word_count(text: str) -> str:
    """Count the number of words in a text string."""
    return str(len(text.split()))

_TOOLS = {
    "calculator": calculator,
    "word_count": word_count,
}

_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a simple Python maths expression e.g. '2 + 3 * 4'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The maths expression to evaluate."}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "word_count",
            "description": "Count the number of words in a text string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to count words in."}
                },
                "required": ["text"]
            }
        }
    },
]

async def _run_agent(
    task: str,
    tool_schemas: list,
    model: str = "gpt-4o-mini",
    system_prompt: str = "You are a helpful assistant that uses tools to complete tasks.",
) -> dict:
    """
    ReAct loop using the raw OpenAI chat completions API.
    No langchain, no langgraph — just openai.

    Returns: {"result": str, "tool_calls": list, "steps": int}
    """
    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": task},
    ]
    tool_call_log: list = []
    step_counter:  int  = 0

    while True:
        response = await _client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas if tool_schemas else [],
            tool_choice="auto" if tool_schemas else "none",
        )
        msg = response.choices[0].message

        # Append assistant turn (convert to dict for portability)
        assistant_turn: dict = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_turn["tool_calls"] = [
                {
                    "id":       tc.id,
                    "type":     "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_turn)

        if not msg.tool_calls:
            return {
                "result":     msg.content or "",
                "tool_calls": tool_call_log,
                "steps":      step_counter,
            }

        # Execute each tool call
        for tc in msg.tool_calls:
            step_counter += 1
            name   = tc.function.name
            args   = _json.loads(tc.function.arguments or "{}")
            output = _TOOLS[name](**args) if name in _TOOLS else f"Unknown tool: {name!r}"

            tool_call_log.append({
                "tool":   name,
                "input":  args,
                "output": output,
                "step":   step_counter,
            })

            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      output,
            })


# ── Graph: blocking-agent-simple ─────────────────────────────
async def run() -> None:
    # Node: Task (ConstantNode)
    task_out = 'What is 123 * 456? Then count the words in the answer.'

    # Node: Agent (ToolAgentNode — blocking, zero-framework)
    _agent_out = await _run_agent(
        task=task_out,
        tool_schemas=_TOOL_SCHEMAS,
        model='gpt-4o-mini',
    )
    agent_result     = _agent_out["result"]
    agent_tool_calls = _agent_out["tool_calls"]
    agent_steps       = _agent_out["steps"]

    # Node: Output (PrintNode)
    print(f'[Output] ' + str(agent_result))



if __name__ == "__main__":
    asyncio.run(run())
