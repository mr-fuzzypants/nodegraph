"""
NodeGraph Compiler v3 — Node Code Templates (Level 3 / Zero Framework)
=======================================================================
Same template contract as compiler2/templates.py, but all emitted code
targets the raw **openai** Python SDK only.

Dependencies of the compiled output:
    pip install openai python-dotenv

No langchain, no langgraph, no langchain-community required.

Key differences from compiler2 templates
-----------------------------------------
  compiler2 → langchain.agents.create_agent()  → astream_events()
  compiler3 → openai.AsyncOpenAI()             → chat.completions.create()

The ReAct loop (_run_agent, _agent_event_stream) is implemented manually
using OpenAI's native tool_calls message format:

    1. POST /chat/completions with tools=[...] and tool_choice="auto"
    2. If response has tool_calls → execute each, append ToolMessage, repeat
    3. If no tool_calls → final answer

Tool schemas
------------
Each tool requires an OpenAI-format function schema dict.  These are
hardcoded per tool name in _TOOL_SCHEMAS.  To add a new tool:
    1. Add the Python function to _TOOL_DEFS
    2. Add its schema to _TOOL_SCHEMAS
"""

from __future__ import annotations

import textwrap
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from nodegraph.python.compiler2.scheduler import ScheduledNode

# Re-use CodeWriter from compiler2 — it has no output-format coupling
from nodegraph.python.compiler2.templates import CodeWriter


# ── Tool Python source (inlined into compiled output) ─────────────────────────

_TOOL_DEFS: dict[str, str] = {
    "calculator": textwrap.dedent("""\
        def calculator(expression: str) -> str:
            \"\"\"Evaluate a simple Python maths expression e.g. '2 + 3 * 4'.\"\"\"
            try:
                return str(eval(expression, {"__builtins__": {}}, {}))
            except Exception as exc:
                return f"Error: {exc}"
        """),
    "word_count": textwrap.dedent("""\
        def word_count(text: str) -> str:
            \"\"\"Count the number of words in a text string.\"\"\"
            return str(len(text.split()))
        """),
    "web_search": textwrap.dedent("""\
        def web_search(query: str) -> str:
            \"\"\"Search the web (stub — replace with a real implementation).\"\"\"
            return f"web_search not implemented for standalone mode (query={query!r})"
        """),
}


# ── Tool OpenAI function schemas (inlined into compiled output) ───────────────

_TOOL_SCHEMAS: dict[str, str] = {
    "calculator": textwrap.dedent("""\
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
        }"""),
    "word_count": textwrap.dedent("""\
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
        }"""),
    "web_search": textwrap.dedent("""\
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for a query.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query."}
                    },
                    "required": ["query"]
                }
            }
        }"""),
}


def _tool_names_from_expr(expr: str) -> List[str]:
    import ast
    try:
        val = ast.literal_eval(expr)
        if isinstance(val, list):
            return [str(t) for t in val]
        if isinstance(val, str):
            return [val]
    except Exception:
        pass
    return []


# ── Client bootstrap preamble (emitted once at top-level) ─────────────────────

_CLIENT_PREAMBLE = textwrap.dedent("""\
    import json as _json
    from openai import AsyncOpenAI as _AsyncOpenAI

    _client = _AsyncOpenAI()
    """)


# ── Blocking agent helper ──────────────────────────────────────────────────────

_BLOCKING_AGENT_HELPER = textwrap.dedent("""\
    async def _run_agent(
        task: str,
        tool_schemas: list,
        model: str = "gpt-4o-mini",
        system_prompt: str = "You are a helpful assistant that uses tools to complete tasks.",
    ) -> dict:
        \"\"\"
        ReAct loop using the raw OpenAI chat completions API.
        No langchain, no langgraph — just openai.

        Returns: {"result": str, "tool_calls": list, "steps": int}
        \"\"\"
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
    """)


# ── Streaming agent helper ─────────────────────────────────────────────────────

_STREAM_AGENT_HELPER = textwrap.dedent("""\
    async def _agent_event_stream(
        task: str,
        tool_schemas: list,
        model: str = "gpt-4o-mini",
        system_prompt: str = "You are a helpful assistant that uses tools to complete tasks.",
    ):
        \"\"\"
        Async generator over reasoning steps using the raw OpenAI API.
        No langchain, no langgraph — just openai.

        Yields dicts with keys: step_type, tool_name, content.
          step_type == "tool_call"   — agent is about to call a tool
          step_type == "tool_result" — tool returned a result
          step_type == "final"       — agent produced the final answer
        \"\"\"
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
    """)


# ── Shared tool-block builder ─────────────────────────────────────────────────

def _build_tool_block(tool_names: List[str]) -> List[str]:
    """Emit: tool function defs + _TOOLS dict + _TOOL_SCHEMAS list."""
    lines: List[str] = []
    lines.append("# ── Tools ───────────────────────────────────────────────────────────────────────")
    for name in tool_names:
        if name in _TOOL_DEFS:
            lines.extend(_TOOL_DEFS[name].splitlines())
            lines.append("")

    lines.append(f"_TOOLS = {{")
    for name in tool_names:
        lines.append(f'    "{name}": {name},')
    lines.append("}")
    lines.append("")

    lines.append("_TOOL_SCHEMAS = [")
    for name in tool_names:
        if name in _TOOL_SCHEMAS:
            for schema_line in _TOOL_SCHEMAS[name].splitlines():
                lines.append("    " + schema_line)
            lines[-1] += ","  # trailing comma after closing }
    lines.append("]")
    lines.append("")
    return lines


# ── ForEach helper (preamble) ────────────────────────────────────────────────

_FOREACH_HELPER = textwrap.dedent("""\
    async def _foreach_stream(items):
        \"\"\"Async generator — yields one dict per list element, then a done sentinel.\"\"\"
        _items = list(items) if items is not None else []
        _total = len(_items)
        for _i, _v in enumerate(_items):
            yield {"_done": False, "item": _v, "index": _i, "total": _total}
        yield {"_done": True, "item": None, "index": -1, "total": _total}
    """)


# ── Base template ─────────────────────────────────────────────────────────────

class NodeTemplate:
    def preamble(self, node: "ScheduledNode") -> List[str]:
        return []

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        writer.comment(f"[{node.type_name}] {node.node_name} — no L3 template registered")
        for var in node.output_vars.values():
            writer.writeln(f"{var} = None  # TODO")

    def emit_loop_expr(self, node: "ScheduledNode") -> str:
        raise NotImplementedError

    def emit_loop_break(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        pass


# ── ConstantNode ──────────────────────────────────────────────────────────────

class ConstantNodeTemplate(NodeTemplate):
    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        out_var = node.output_vars.get("out", f"{node.node_name.lower()}_out")
        val     = node.output_port_values.get("out")
        writer.comment(f"Node: {node.node_name} (ConstantNode)")
        writer.writeln(f"{out_var} = {repr(val)}")


# ── PrintNode ─────────────────────────────────────────────────────────────────

class PrintNodeTemplate(NodeTemplate):
    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        val_expr = node.input_exprs.get("value", '""')
        writer.comment(f"Node: {node.node_name} (PrintNode)")
        writer.writeln(f"print(f'[{node.node_name}] ' + str({val_expr}))")


# ── StepPrinterNode ───────────────────────────────────────────────────────────

class StepPrinterNodeTemplate(NodeTemplate):
    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        st = node.input_exprs.get("step_type",    '"unknown"')
        sc = node.input_exprs.get("step_content", '""')
        tn = node.input_exprs.get("tool_name",    '""')
        writer.comment(f"Node: {node.node_name} (StepPrinterNode)")
        writer.writeln(f"if {st} == 'tool_call':")
        writer.push()
        writer.writeln(f"print(f'  → {{{tn}}}({{{sc}}})', flush=True)")
        writer.pop()
        writer.writeln(f"elif {st} == 'tool_result':")
        writer.push()
        writer.writeln(f"print(f'  ← {{{sc}}}', flush=True)")
        writer.pop()
        writer.writeln(f"else:")
        writer.push()
        writer.writeln(f"print(f'  [{{{st}}}] {{{sc}}}', flush=True)")
        writer.pop()


# ── ForEachNode — Level 3 ───────────────────────────────────────────────────

class ForEachNodeTemplate(NodeTemplate):
    """LOOP_AGAIN node — compiles to `async for _step in _foreach_stream(items):` """

    def preamble(self, node: "ScheduledNode") -> List[str]:
        return _FOREACH_HELPER.splitlines() + [""]

    def emit_loop_expr(self, node: "ScheduledNode") -> str:
        items_expr = node.input_exprs.get("items", "[]")
        return f"_foreach_stream({items_expr})"

    def emit_loop_break(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        item_var  = node.output_vars.get("item",  "_foreach_item")
        index_var = node.output_vars.get("index", "_foreach_index")
        total_var = node.output_vars.get("total", "_foreach_total")
        writer.writeln(f"{item_var}  = _step['item']")
        writer.writeln(f"{index_var} = _step['index']")
        writer.writeln(f"{total_var} = _step['total']")
        writer.writeln(f"if _step['_done']:")
        writer.push()
        writer.writeln("break")
        writer.pop()


# ── ToolAgentNode (blocking) — Level 3 ───────────────────────────────────────

class ToolAgentNodeTemplate(NodeTemplate):

    def preamble(self, node: "ScheduledNode") -> List[str]:
        tool_names = _tool_names_from_expr(node.input_exprs.get("tools", "[]"))
        lines = list(_CLIENT_PREAMBLE.splitlines()) + [""]
        lines += _build_tool_block(tool_names)
        lines += _BLOCKING_AGENT_HELPER.splitlines() + [""]
        return lines

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        task_expr   = node.input_exprs.get("task",  '""')
        model_expr  = node.input_exprs.get("model", '"gpt-4o-mini"')
        result_var     = node.output_vars.get("result",     f"{node.node_name.lower()}_result")
        tool_calls_var = node.output_vars.get("tool_calls", f"{node.node_name.lower()}_tool_calls")
        steps_var      = node.output_vars.get("steps",      f"{node.node_name.lower()}_steps")

        writer.comment(f"Node: {node.node_name} (ToolAgentNode — blocking, zero-framework)")
        writer.writeln(f"_agent_out = await _run_agent(")
        writer.push()
        writer.writeln(f"task={task_expr},")
        writer.writeln(f"tool_schemas=_TOOL_SCHEMAS,")
        writer.writeln(f"model={model_expr},")
        writer.pop()
        writer.writeln(f")")
        writer.writeln(f'{result_var}     = _agent_out["result"]')
        writer.writeln(f'{tool_calls_var} = _agent_out["tool_calls"]')
        writer.writeln(f'{steps_var}       = _agent_out["steps"]')


# ── ToolAgentStreamNode — Level 3 ────────────────────────────────────────────

class ToolAgentStreamNodeTemplate(NodeTemplate):

    def preamble(self, node: "ScheduledNode") -> List[str]:
        tool_names = _tool_names_from_expr(node.input_exprs.get("tools", "[]"))
        lines = list(_CLIENT_PREAMBLE.splitlines()) + [""]
        lines += _build_tool_block(tool_names)
        lines += _STREAM_AGENT_HELPER.splitlines() + [""]
        return lines

    def emit_loop_expr(self, node: "ScheduledNode") -> str:
        task_expr  = node.input_exprs.get("task",  '""')
        model_expr = node.input_exprs.get("model", '"gpt-4o-mini"')
        return (
            f"_agent_event_stream(\n"
            f"        task={task_expr},\n"
            f"        tool_schemas=_TOOL_SCHEMAS,\n"
            f"        model={model_expr},\n"
            f"    )"
        )

    def emit_loop_break(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        step_type_var    = node.output_vars.get("step_type",    "_step_type")
        step_content_var = node.output_vars.get("step_content", "_step_content")
        tool_name_var    = node.output_vars.get("tool_name",    "_tool_name")
        step_count_var   = node.output_vars.get("step_count",   "_step_count")
        result_var       = node.output_vars.get("result",       "_agent_result")

        writer.writeln(f"{step_type_var}    = _step.get('step_type',  '')")
        writer.writeln(f"{step_content_var} = _step.get('content',    '')")
        writer.writeln(f"{tool_name_var}    = _step.get('tool_name',  '')")
        writer.writeln(f"{step_count_var}  += 1")
        writer.blank()
        writer.writeln(f"if {step_type_var} == 'final':")
        writer.push()
        writer.writeln(f"{result_var} = {step_content_var}")
        writer.writeln("break")
        writer.pop()


# ── Registry ──────────────────────────────────────────────────────────────────

TEMPLATE_REGISTRY: dict[str, NodeTemplate] = {
    "ConstantNode":        ConstantNodeTemplate(),
    "PrintNode":           PrintNodeTemplate(),
    "StepPrinterNode":     StepPrinterNodeTemplate(),
    "ForEachNode":         ForEachNodeTemplate(),
    "ToolAgentNode":       ToolAgentNodeTemplate(),
    "ToolAgentStreamNode": ToolAgentStreamNodeTemplate(),
}

_DEFAULT = NodeTemplate()


def get_template(type_name: str) -> NodeTemplate:
    return TEMPLATE_REGISTRY.get(type_name, _DEFAULT)
