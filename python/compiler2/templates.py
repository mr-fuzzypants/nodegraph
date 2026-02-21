"""
NodeGraph Compiler v2 — Node Code Templates
============================================
A NodeTemplate provides two emission hooks:

  preamble(node)
      Returns a list of top-level source lines emitted once before the main
      run() function.  Used for: tool definitions, async helper generators,
      import statements.

  emit_inline(node, writer)
      Emits the inline logic for this node at the writer's current indent.
      Called inside the main run() function (or loop body).

  emit_loop_expr(node)  [loop-only]
      Returns the expression string for the `async for _step in <expr>:`
      header of a LoopBlock.  Only valid for templates that represent
      LOOP_AGAIN-style nodes.

  emit_loop_break(node, writer)  [loop-only]
      Emits the "break out on final step" if-block inside the loop.

Adding a new node type
----------------------
1. Subclass NodeTemplate (or DefaultTemplate).
2. Override the required hooks.
3. Register: TEMPLATE_REGISTRY["MyNodeType"] = MyNodeTemplate()

If a type is not registered, DefaultTemplate is used (emits a TODO comment).

Known inline tool definitions
------------------------------
Preambles for tool-using nodes pull from _TOOL_DEFS.  To add a new tool,
add an entry to that dict with the full Python function source.
"""

from __future__ import annotations

import textwrap
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from .scheduler import ScheduledNode


# ── Code writer ───────────────────────────────────────────────────────────────

class CodeWriter:
    """Simple indented string accumulator."""

    def __init__(self, indent: int = 0):
        self._lines: List[str] = []
        self._indent = indent

    def writeln(self, line: str = "") -> "CodeWriter":
        if line:
            self._lines.append("    " * self._indent + line)
        else:
            self._lines.append("")
        return self

    def blank(self) -> "CodeWriter":
        return self.writeln()

    def comment(self, text: str) -> "CodeWriter":
        return self.writeln(f"# {text}")

    def push(self) -> "CodeWriter":
        self._indent += 1
        return self

    def pop(self) -> "CodeWriter":
        self._indent = max(0, self._indent - 1)
        return self

    def extend(self, lines: List[str]) -> "CodeWriter":
        for line in lines:
            self.writeln(line)
        return self

    def lines(self) -> List[str]:
        return self._lines

    def result(self) -> str:
        return "\n".join(self._lines)


# ── Known tool source snippets ────────────────────────────────────────────────
# These are inlined into preambles by tool-using node templates.

_TOOL_DEFS: dict[str, str] = {
    "calculator": textwrap.dedent("""\
        @tool
        def calculator(expression: str) -> str:
            \"\"\"Evaluate a simple Python maths expression e.g. '2 + 3 * 4'.\"\"\"
            try:
                return str(eval(expression, {"__builtins__": {}}, {}))
            except Exception as exc:
                return f"Error: {exc}"
        """),
    "word_count": textwrap.dedent("""\
        @tool
        def word_count(text: str) -> str:
            \"\"\"Count the number of words in a text string.\"\"\"
            return str(len(text.split()))
        """),
    "web_search": textwrap.dedent("""\
        @tool
        def web_search(query: str) -> str:
            \"\"\"Search the web for a query string.\"\"\"
            try:
                from langchain_community.tools import DuckDuckGoSearchRun
                return DuckDuckGoSearchRun().run(query)
            except ImportError:
                return "web_search unavailable (install langchain-community)"
        """),
}


def _tool_names_from_expr(expr: str) -> List[str]:
    """
    Best-effort extraction of tool name strings from a repr() expression.
    Works for simple list literals like "['calculator', 'word_count']".
    """
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


# ── Base template ─────────────────────────────────────────────────────────────

class NodeTemplate:
    """
    Base class — subclass and override the hooks you need.
    All hooks have safe default implementations.
    """

    def preamble(self, node: "ScheduledNode") -> List[str]:
        return []

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        writer.comment(f"[{node.type_name}] {node.node_name} — no template registered")
        for var in node.output_vars.values():
            writer.writeln(f"{var} = None  # TODO: implement {node.type_name}")

    def emit_loop_expr(self, node: "ScheduledNode") -> str:
        raise NotImplementedError(f"{type(self).__name__} is not a loop driver")

    def emit_loop_break(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        """Override to emit the break-out condition inside the loop."""
        pass


# ── ConstantNode ──────────────────────────────────────────────────────────────

class ConstantNodeTemplate(NodeTemplate):
    """Emits a single variable assignment for the static output value."""

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        out_var = node.output_vars.get("out", f"{node.node_name.lower()}_out")
        val = node.output_port_values.get("out")
        writer.comment(f"Node: {node.node_name} (ConstantNode)")
        writer.writeln(f"{out_var} = {repr(val)}")


# ── PrintNode ─────────────────────────────────────────────────────────────────

class PrintNodeTemplate(NodeTemplate):
    """Emits a print() call using the wired value input."""

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        val_expr = node.input_exprs.get("value", '""')
        writer.comment(f"Node: {node.node_name} (PrintNode)")
        writer.writeln(f'print(f"[{node.node_name}] {{{{ {val_expr} }}}}")')

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        val_expr = node.input_exprs.get("value", '""')
        writer.comment(f"Node: {node.node_name} (PrintNode)")
        writer.writeln(f"print(f'[{node.node_name}] ' + str({val_expr}))")


# ── StepPrinterNode ───────────────────────────────────────────────────────────

class StepPrinterNodeTemplate(NodeTemplate):
    """Emits the inline step-printing logic from StepPrinterNode.compute()."""

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        st  = node.input_exprs.get("step_type",    '"unknown"')
        sc  = node.input_exprs.get("step_content", '""')
        tn  = node.input_exprs.get("tool_name",    '""')
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


# ── ForEachNode ─────────────────────────────────────────────────────────────

_FOREACH_HELPER = textwrap.dedent("""\
    async def _foreach_stream(items):
        \"\"\"Async generator — yields one dict per list element, then a done sentinel.\"\"\"
        _items = list(items) if items is not None else []
        _total = len(_items)
        for _i, _v in enumerate(_items):
            yield {"_done": False, "item": _v, "index": _i, "total": _total}
        yield {"_done": True, "item": None, "index": -1, "total": _total}
    """)


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


# ── ToolAgentNode (blocking) ─────────────────────────────────────────────────

_BLOCKING_AGENT_HELPER = textwrap.dedent("""\
    async def _run_agent(task: str, tool_names: list, model: str = "gpt-4o-mini") -> dict:
        \"\"\"Run a blocking LangChain ReAct agent and return the result dict.\"\"\"
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
    """)


class ToolAgentNodeTemplate(NodeTemplate):
    """Blocking ToolAgentNode — async call, waits for the full result."""

    def preamble(self, node: "ScheduledNode") -> List[str]:
        tool_names = _tool_names_from_expr(node.input_exprs.get("tools", "[]"))
        lines: List[str] = []
        lines.append("# ── LangChain tools ──────────────────────────────────────────────────────────")
        lines.append("from langchain_core.tools import tool")
        lines.append("")
        for tname in tool_names:
            if tname in _TOOL_DEFS:
                lines.extend(_TOOL_DEFS[tname].splitlines())
                lines.append("")
        lines.append("_TOOLS = {")
        for tname in tool_names:
            lines.append(f'    "{tname}": {tname},')
        lines.append("}")
        lines.append("")
        lines.extend(_BLOCKING_AGENT_HELPER.splitlines())
        lines.append("")
        return lines

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        task_expr  = node.input_exprs.get("task",  '""')
        tools_expr = node.input_exprs.get("tools", "[]")
        model_expr = node.input_exprs.get("model", '"gpt-4o-mini"')
        result_var      = node.output_vars.get("result",     f"{node.node_name.lower()}_result")
        tool_calls_var  = node.output_vars.get("tool_calls", f"{node.node_name.lower()}_tool_calls")
        steps_var        = node.output_vars.get("steps",     f"{node.node_name.lower()}_steps")

        writer.comment(f"Node: {node.node_name} (ToolAgentNode — blocking)")
        writer.writeln(f"_agent_out    = await _run_agent(")
        writer.push()
        writer.writeln(f"task={task_expr},")
        writer.writeln(f"tool_names={tools_expr},")
        writer.writeln(f"model={model_expr},")
        writer.pop()
        writer.writeln(f")")
        writer.writeln(f'{result_var}     = _agent_out["result"]')
        writer.writeln(f'{tool_calls_var} = _agent_out["tool_calls"]')
        writer.writeln(f'{steps_var}       = _agent_out["steps"]')


# ── ToolAgentStreamNode ───────────────────────────────────────────────────────

_STREAM_AGENT_HELPER = textwrap.dedent("""\
    async def _agent_event_stream(task: str, tool_names: list, model: str = "gpt-4o-mini"):
        \"\"\"
        Async generator over meaningful LangGraph reasoning steps.
        Yields dicts with keys: step_type, tool_name, content.
          step_type == "tool_call"   — agent is about to call a tool
          step_type == "tool_result" — tool returned a result
          step_type == "final"       — agent produced the final answer
        \"\"\"
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
    """)


class ToolAgentStreamNodeTemplate(NodeTemplate):
    """
    LOOP_AGAIN-style streaming agent.

    Preamble   → tool definitions + _agent_event_stream() async generator.
    Loop expr  → `_agent_event_stream(task=..., tool_names=..., model=...)`
    Loop break → `if step_type == "final": result = content; break`
    body nodes → StepPrinterNode etc. inlined inside the loop
    post nodes → PrintNode etc. after the loop
    """

    def preamble(self, node: "ScheduledNode") -> List[str]:
        tool_names = _tool_names_from_expr(node.input_exprs.get("tools", "[]"))
        lines: List[str] = []
        lines.append("# ── LangChain tools ──────────────────────────────────────────────────────────")
        lines.append("from langchain_core.tools import tool")
        lines.append("")
        for tname in tool_names:
            if tname in _TOOL_DEFS:
                lines.extend(_TOOL_DEFS[tname].splitlines())
                lines.append("")
        lines.append("_TOOLS = {")
        for tname in tool_names:
            lines.append(f'    "{tname}": {tname},')
        lines.append("}")
        lines.append("")
        lines.extend(_STREAM_AGENT_HELPER.splitlines())
        lines.append("")
        return lines

    def emit_loop_expr(self, node: "ScheduledNode") -> str:
        task_expr  = node.input_exprs.get("task",  '""')
        tools_expr = node.input_exprs.get("tools", "[]")
        model_expr = node.input_exprs.get("model", '"gpt-4o-mini"')
        return (
            f"_agent_event_stream(\n"
            f"        task={task_expr},\n"
            f"        tool_names={tools_expr},\n"
            f"        model={model_expr},\n"
            f"    )"
        )

    def emit_loop_break(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        """Emit the step-type dispatch at the top of the loop body."""
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


# ── LLMStreamNode ─────────────────────────────────────────────────────────────

_STREAM_LLM_HELPER = textwrap.dedent("""\
    async def _llm_token_stream(prompt: str, system_prompt: str = "You are a helpful assistant.",
                                model: str = "gpt-4o-mini", temperature: float = 0.7):
        \"\"\"Async generator that yields one token string at a time.\"\"\"
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
        llm = ChatOpenAI(model=model, temperature=temperature, streaming=True)
        async for chunk in llm.astream([SystemMessage(content=system_prompt),
                                        HumanMessage(content=prompt)]):
            if chunk.content:
                yield chunk.content
    """)


class LLMStreamNodeTemplate(NodeTemplate):
    """LLMStreamNode — streams one token per loop iteration."""

    def preamble(self, node: "ScheduledNode") -> List[str]:
        return _STREAM_LLM_HELPER.splitlines() + [""]

    def emit_loop_expr(self, node: "ScheduledNode") -> str:
        prompt_expr = node.input_exprs.get("prompt",        '""')
        system_expr = node.input_exprs.get("system_prompt", '"You are a helpful assistant."')
        model_expr  = node.input_exprs.get("model",         '"gpt-4o-mini"')
        temp_expr   = node.input_exprs.get("temperature",   "0.7")
        return (
            f"_llm_token_stream(\n"
            f"        prompt={prompt_expr},\n"
            f"        system_prompt={system_expr},\n"
            f"        model={model_expr},\n"
            f"        temperature={temp_expr},\n"
            f"    )"
        )

    def emit_loop_break(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        chunk_var       = node.output_vars.get("chunk",       "_chunk")
        accumulated_var = node.output_vars.get("accumulated", "_accumulated")
        count_var       = node.output_vars.get("chunk_count", "_chunk_count")
        writer.writeln(f"{chunk_var}        = _step")
        writer.writeln(f"{accumulated_var} += _step")
        writer.writeln(f"{count_var}       += 1")


# ── Default (unknown type) ────────────────────────────────────────────────────

class DefaultTemplate(NodeTemplate):
    """Fallback for unregistered node types — emits a clearly marked TODO."""

    def emit_inline(self, node: "ScheduledNode", writer: CodeWriter) -> None:
        writer.blank()
        writer.comment(
            f"TODO: no template for '{node.type_name}' (node: {node.node_name})"
        )
        writer.comment(
            "      Implement a NodeTemplate subclass and register it in TEMPLATE_REGISTRY."
        )
        for var in node.output_vars.values():
            writer.writeln(f"{var} = None")
        writer.blank()


# ── Registry ──────────────────────────────────────────────────────────────────

TEMPLATE_REGISTRY: dict[str, NodeTemplate] = {
    "ConstantNode":          ConstantNodeTemplate(),
    "PrintNode":             PrintNodeTemplate(),
    "StepPrinterNode":       StepPrinterNodeTemplate(),
    "ForEachNode":           ForEachNodeTemplate(),
    "ToolAgentNode":         ToolAgentNodeTemplate(),
    "ToolAgentStreamNode":   ToolAgentStreamNodeTemplate(),
    "LLMStreamNode":         LLMStreamNodeTemplate(),
}

_DEFAULT_TEMPLATE = DefaultTemplate()


def get_template(type_name: str) -> NodeTemplate:
    return TEMPLATE_REGISTRY.get(type_name, _DEFAULT_TEMPLATE)
