#!/usr/bin/env python3
"""
Compiled from NodeGraph: streaming-agent-multistep
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

async def _agent_event_stream(
    task: str,
    tool_schemas: list,
    model: str = "gpt-4o-mini",
    system_prompt: str = "You are a helpful assistant that uses tools to complete tasks.",
):
    """
    Async generator over reasoning steps using the raw OpenAI API.
    No langchain, no langgraph — just openai.

    Yields dicts with keys: step_type, tool_name, content.
      step_type == "tool_call"   — agent is about to call a tool
      step_type == "tool_result" — tool returned a result
      step_type == "final"       — agent produced the final answer
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": task},
    ]

    while True:
        response = await _client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas if tool_schemas else [],
            tool_choice="auto" if tool_schemas else "none",
        )
        msg = response.choices[0].message

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
            yield {
                "step_type": "final",
                "tool_name": "",
                "content":   msg.content or "",
            }
            return

        for tc in msg.tool_calls:
            name = tc.function.name
            args = _json.loads(tc.function.arguments or "{}")

            yield {
                "step_type": "tool_call",
                "tool_name": name,
                "content":   str(args),
            }

            output = _TOOLS[name](**args) if name in _TOOLS else f"Unknown tool: {name!r}"
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      output,
            })

            yield {
                "step_type": "tool_result",
                "tool_name": name,
                "content":   output,
            }


# ── Graph: streaming-agent-multistep ─────────────────────────
async def run() -> None:
    # Node: Task (ConstantNode)
    task_out = 'Calculate: ((10 + 5) * 3) - 7. Show each step as a separate calculation.'

    # Node: Agent (ToolAgentStreamNode)
    agent_step_type = ""
    agent_step_content = ""
    agent_tool_name = ""
    agent_step_count = 0
    agent_result = ""

    async for _step in _agent_event_stream(
        task=task_out,
        tool_schemas=_TOOL_SCHEMAS,
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
