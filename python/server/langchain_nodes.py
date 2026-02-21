"""
LangChain node types — Approach 3 + 4.

These nodes behave like any other node in the executor's view: they receive
inputs via ports and write outputs when compute() finishes.  Internally they
drive LangChain / OpenAI APIs and bridge internal events into global_tracer so
the UI trace overlay shows per-step activity.

Requirements (install via pip):
    langchain langchain-openai langchain-community langchain-text-splitters

Environment variable:
    OPENAI_API_KEY  — standard OpenAI env var consumed by langchain-openai.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from nodegraph.python.core.Executor import ExecCommand, ExecutionResult
from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodePort import (
    InputControlPort,
    InputDataPort,
    OutputControlPort,
    OutputDataPort,
)
from nodegraph.python.core.Types import ValueType
from nodegraph.python.server.trace.trace_emitter import global_tracer


# ── Registration helper (matches node_definitions.py pattern) ─────────────────

def _safe_register(type_name: str):
    def decorator(cls):
        if type_name not in Node._node_registry:
            Node._node_registry[type_name] = cls
        return cls
    return decorator


# ── Trace helpers ─────────────────────────────────────────────────────────────

def _fire(node: Node, event_type: str, **kwargs) -> None:
    global_tracer.fire({"type": event_type, "nodeId": node.id, **kwargs})


def _fire_edge(node: Node, from_port: str, to_port: str, value) -> None:
    global_tracer.fire({
        "type":       "EDGE_ACTIVE",
        "fromNodeId": node.id,
        "fromPort":   from_port,
        "toNodeId":   node.id,
        "toPort":     to_port,
        "value":      str(value)[:300],
    })


# ── 1. PromptTemplateNode ──────────────────────────────────────────────────────
# Fills a LangChain PromptTemplate with a dict of variables.
# Input:  template (str)  e.g. "Answer this: {question}"
#         variables (any) dict (or JSON string)  e.g. {"question": "..."}
# Output: prompt (str)    the rendered prompt string

@_safe_register("PromptTemplateNode")
class PromptTemplateNode(Node):
    def __init__(self, name: str, type: str = "PromptTemplateNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["template"]  = InputDataPort(self.id, "template",  ValueType.STRING)
        self.inputs["variables"] = InputDataPort(self.id, "variables", ValueType.ANY)
        self.outputs["prompt"]   = OutputDataPort(self.id, "prompt",   ValueType.STRING)

        self.inputs["template"].value  = "Answer the following question: {question}"
        self.inputs["variables"].value = {"question": "What is a node graph?"}
        self.outputs["prompt"].value   = ""

    async def compute(self, executionContext=None) -> ExecutionResult:
        from langchain_core.prompts import PromptTemplate

        ctx   = (executionContext or {}).get("data_inputs", {})
        tmpl  = ctx.get("template",  self.inputs["template"].value)  or "{input}"
        variables = ctx.get("variables", self.inputs["variables"].value) or {}

        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except json.JSONDecodeError:
                variables = {}

        rendered = PromptTemplate.from_template(tmpl).format(**variables)
        self.outputs["prompt"].value = rendered
        _fire_edge(self, "template", "rendered_prompt", rendered[:120])

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["prompt"] = rendered
        return result


# ── 2. LLMNode ─────────────────────────────────────────────────────────────────
# Single-shot blocking LLM call via OpenAI chat completion.
# Inputs:  prompt, system_prompt, model, temperature
# Outputs: response (str), model_used (str), tokens_used (int)

@_safe_register("LLMNode")
class LLMNode(Node):
    def __init__(self, name: str, type: str = "LLMNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["prompt"]        = InputDataPort(self.id, "prompt",        ValueType.STRING)
        self.inputs["system_prompt"] = InputDataPort(self.id, "system_prompt", ValueType.STRING)
        self.inputs["model"]         = InputDataPort(self.id, "model",         ValueType.STRING)
        self.inputs["temperature"]   = InputDataPort(self.id, "temperature",   ValueType.FLOAT)
        self.outputs["response"]     = OutputDataPort(self.id, "response",     ValueType.STRING)
        self.outputs["model_used"]   = OutputDataPort(self.id, "model_used",   ValueType.STRING)
        self.outputs["tokens_used"]  = OutputDataPort(self.id, "tokens_used",  ValueType.INT)

        self.inputs["model"].value         = "gpt-4o-mini"
        self.inputs["temperature"].value   = 0.7
        self.inputs["system_prompt"].value = "You are a helpful assistant."
        self.outputs["response"].value     = ""
        self.outputs["model_used"].value   = "gpt-4o-mini"
        self.outputs["tokens_used"].value  = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        ctx         = (executionContext or {}).get("data_inputs", {})
        prompt      = ctx.get("prompt",        self.inputs["prompt"].value)        or ""
        system      = ctx.get("system_prompt", self.inputs["system_prompt"].value) or "You are a helpful assistant."
        model_name  = ctx.get("model",         self.inputs["model"].value)         or "gpt-4o-mini"
        temperature = float(ctx.get("temperature", self.inputs["temperature"].value) or 0.7)

        _fire_edge(self, "prompt", "llm_input", prompt[:120])

        llm      = ChatOpenAI(model=model_name, temperature=temperature)
        messages = [SystemMessage(content=system), HumanMessage(content=prompt)]

        t0       = time.time()
        response = await llm.ainvoke(messages)
        duration = (time.time() - t0) * 1000

        content     = response.content
        tokens_used = 0
        if response.usage_metadata:
            tokens_used = response.usage_metadata.get("total_tokens", 0)

        self.outputs["response"].value    = content
        self.outputs["model_used"].value  = model_name
        self.outputs["tokens_used"].value = tokens_used

        _fire_edge(self, "llm_output", "response", content[:120])
        _fire(self, "NODE_DETAIL", detail={
            "model":      model_name,
            "tokens":     tokens_used,
            "durationMs": round(duration, 1),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["response"]    = content
        result.data_outputs["model_used"]  = model_name
        result.data_outputs["tokens_used"] = tokens_used
        return result


# ── 3. LLMStreamNode ───────────────────────────────────────────────────────────
# ForLoop-style streaming LLM node.
#
# Behaves identically to ForLoopNode:
#   - First compute() call opens the OpenAI stream and pulls the first chunk.
#   - Returns LOOP_AGAIN + fires loop_body → downstream nodes run per chunk.
#   - When StopAsyncIteration is raised, returns COMPLETED + fires completed.
#
# Control ports:  exec (in)  |  loop_body (out)  |  completed (out)
# Data ports:     prompt, system_prompt, model (in)
#                 chunk, accumulated, chunk_count, response (out)

@_safe_register("LLMStreamNode")
class LLMStreamNode(Node):
    def __init__(self, name: str, type: str = "LLMStreamNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True

        # ── Stream state (persists across LOOP_AGAIN calls) ───────────────
        self._stream_iter  = None   # async generator from llm.astream()
        self._accumulated  = ""
        self._chunk_count  = 0
        self._stream_active = False

        # ── Control ports ─────────────────────────────────────────────────
        self.inputs["exec"]        = InputControlPort(self.id, "exec")
        self.outputs["loop_body"]  = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"]  = OutputControlPort(self.id, "completed")

        # ── Data ports ────────────────────────────────────────────────────
        self.inputs["prompt"]        = InputDataPort(self.id, "prompt",        ValueType.STRING)
        self.inputs["system_prompt"] = InputDataPort(self.id, "system_prompt", ValueType.STRING)
        self.inputs["model"]         = InputDataPort(self.id, "model",         ValueType.STRING)
        self.outputs["chunk"]        = OutputDataPort(self.id, "chunk",        ValueType.STRING)
        self.outputs["accumulated"]  = OutputDataPort(self.id, "accumulated",  ValueType.STRING)
        self.outputs["chunk_count"]  = OutputDataPort(self.id, "chunk_count",  ValueType.INT)
        self.outputs["response"]     = OutputDataPort(self.id, "response",     ValueType.STRING)

        self.inputs["model"].value         = "gpt-4o-mini"
        self.inputs["system_prompt"].value = "You are a helpful assistant."
        self.outputs["chunk"].value        = ""
        self.outputs["accumulated"].value  = ""
        self.outputs["chunk_count"].value  = 0
        self.outputs["response"].value     = ""

    async def compute(self, executionContext=None) -> ExecutionResult:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage

        # ── First entry: open the stream ──────────────────────────────────
        if not self._stream_active:
            ctx    = (executionContext or {}).get("data_inputs", {})
            prompt = ctx.get("prompt",        self.inputs["prompt"].value)        or ""
            system = ctx.get("system_prompt", self.inputs["system_prompt"].value) or "You are a helpful assistant."
            model  = ctx.get("model",         self.inputs["model"].value)         or "gpt-4o-mini"

            llm      = ChatOpenAI(model=model, streaming=True)
            messages = [SystemMessage(content=system), HumanMessage(content=prompt)]

            self._stream_iter   = llm.astream(messages)
            self._accumulated   = ""
            self._chunk_count   = 0
            self._stream_active = True
            _fire_edge(self, "prompt", "llm_input", prompt[:120])

        # ── Each call: pull one chunk ─────────────────────────────────────
        try:
            chunk_msg = await self._stream_iter.__anext__()
            piece = chunk_msg.content or ""

            self._accumulated += piece
            self._chunk_count += 1

            self.outputs["chunk"].value       = piece
            self.outputs["accumulated"].value = self._accumulated
            self.outputs["chunk_count"].value = self._chunk_count

            global_tracer.fire({
                "type":        "STREAM_CHUNK",
                "nodeId":      self.id,
                "chunk":       piece,
                "accumulated": self._accumulated,
            })

            result = ExecutionResult(ExecCommand.LOOP_AGAIN)
            result.data_outputs["chunk"]       = piece
            result.data_outputs["accumulated"] = self._accumulated
            result.data_outputs["chunk_count"] = self._chunk_count
            result.control_outputs["loop_body"] = True
            result.control_outputs["completed"] = False
            return result

        except StopAsyncIteration:
            # ── Stream exhausted: finalise ────────────────────────────────
            self.outputs["response"].value    = self._accumulated
            self.outputs["chunk"].value       = ""
            self.outputs["chunk_count"].value = self._chunk_count

            _fire_edge(self, "llm_output", "response", self._accumulated[:120])
            _fire(self, "NODE_DETAIL", detail={
                "model":      self.inputs["model"].value,
                "chunks":     self._chunk_count,
                "characters": len(self._accumulated),
            })

            # Reset state for next execution
            self._stream_iter   = None
            self._accumulated   = ""
            self._chunk_count   = 0
            self._stream_active = False

            result = ExecutionResult(ExecCommand.COMPLETED)
            result.data_outputs["response"]     = self.outputs["response"].value
            result.control_outputs["completed"] = True
            result.control_outputs["loop_body"] = False
            return result


# ── 4. ToolAgentNode ───────────────────────────────────────────────────────────
# ReAct-style agent with access to built-in tools (calculator, word_count).
# Each tool call fires an AGENT_STEP trace event visible in the UI.
# Inputs:  task (str), tools (any: list[str]), model (str)
# Outputs: result (str), tool_calls (any: list[dict]), steps (int)

# ── Built-in tool registry ────────────────────────────────────────────────────

_TOOL_REGISTRY: dict = {}

def _init_tools() -> None:
    """Populate _TOOL_REGISTRY lazily so import errors don't crash server startup."""
    try:
        from langchain_core.tools import tool

        @tool
        def calculator(expression: str) -> str:   # noqa: F811
            """Evaluate a simple Python maths expression. Input: an expression string e.g. '2 + 3 * 4'."""
            try:
                return str(eval(expression, {"__builtins__": {}}, {}))
            except Exception as exc:
                return f"Error: {exc}"

        @tool
        def word_count(text: str) -> str:          # noqa: F811
            """Count the number of words in a text string."""
            return str(len(text.split()))

        _TOOL_REGISTRY["calculator"] = calculator
        _TOOL_REGISTRY["word_count"] = word_count

        try:
            from langchain_community.tools import DuckDuckGoSearchRun
            _TOOL_REGISTRY["web_search"] = DuckDuckGoSearchRun()
        except ImportError:
            pass  # optional

        print(f"[langchain_nodes] tools registered: {list(_TOOL_REGISTRY.keys())}")
    except ImportError as exc:
        print(f"[langchain_nodes] tool init skipped: {exc}")

_init_tools()


@_safe_register("ToolAgentNode")
class ToolAgentNode(Node):
    def __init__(self, name: str, type: str = "ToolAgentNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["task"]        = InputDataPort(self.id, "task",       ValueType.STRING)
        self.inputs["tools"]       = InputDataPort(self.id, "tools",      ValueType.ANY)
        self.inputs["model"]       = InputDataPort(self.id, "model",      ValueType.STRING)
        self.outputs["result"]     = OutputDataPort(self.id, "result",    ValueType.STRING)
        self.outputs["tool_calls"] = OutputDataPort(self.id, "tool_calls",ValueType.ANY)
        self.outputs["steps"]      = OutputDataPort(self.id, "steps",     ValueType.INT)

        self.inputs["model"].value       = "gpt-4o-mini"
        self.inputs["tools"].value       = ["calculator", "word_count"]
        self.outputs["result"].value     = ""
        self.outputs["tool_calls"].value = []
        self.outputs["steps"].value      = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        # LangChain 1.x API: create_agent returns a CompiledStateGraph
        from langchain.agents import create_agent

        ctx        = (executionContext or {}).get("data_inputs", {})
        task       = ctx.get("task",  self.inputs["task"].value)  or ""
        tool_names = ctx.get("tools", self.inputs["tools"].value) or ["calculator"]
        model_name = ctx.get("model", self.inputs["model"].value) or "gpt-4o-mini"

        if isinstance(tool_names, str):
            try:
                tool_names = json.loads(tool_names)
            except json.JSONDecodeError:
                tool_names = [tool_names]

        tools = [_TOOL_REGISTRY[t] for t in tool_names if t in _TOOL_REGISTRY]
        if not tools:
            raise ValueError(
                f"No valid tools. Available: {list(_TOOL_REGISTRY.keys())}"
            )

        _fire_edge(self, "task", "agent_input", task[:120])

        # create_agent accepts "openai:<model>" strings or ChatModel instances
        agent = create_agent(
            model=f"openai:{model_name}",
            tools=tools,
            system_prompt="You are a helpful assistant that uses tools to complete tasks.",
        )

        t0 = time.time()

        # ainvoke returns AgentState with a 'messages' list
        output = await agent.ainvoke(
            {"messages": [{"role": "user", "content": task}]}
        )

        # --- Extract tool calls from the message history ---
        messages        = output.get("messages", [])
        tool_call_log   = []
        step_counter    = 0
        final_content   = ""

        # pending_outputs maps tool_call_id → ToolMessage content
        tool_outputs: dict[str, str] = {}
        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type == "ToolMessage":
                tool_id = getattr(msg, "tool_call_id", "") or ""
                tool_outputs[tool_id] = str(msg.content)[:200]

        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type == "AIMessage":
                tcs = getattr(msg, "tool_calls", []) or []
                for tc in tcs:
                    step_counter += 1
                    tool_id  = tc.get("id",   "")
                    tool_nm  = tc.get("name", "unknown")
                    tool_inp = str(tc.get("args", {}))[:200]
                    tool_out = tool_outputs.get(tool_id, "")
                    step = {
                        "step":   step_counter,
                        "tool":   tool_nm,
                        "input":  tool_inp,
                        "output": tool_out,
                    }
                    tool_call_log.append(step)
                    global_tracer.fire({"type": "AGENT_STEP", "nodeId": self.id, **step})
                    _fire_edge(self, f"tool_{tool_nm}", f"tool_result_{step_counter}", tool_out)

        if messages:
            last = messages[-1]
            final_content = last.content if hasattr(last, "content") else str(last)

        self.outputs["result"].value     = final_content
        self.outputs["tool_calls"].value = tool_call_log
        self.outputs["steps"].value      = step_counter

        _fire_edge(self, "agent_output", "result", final_content[:120])
        _fire(self, "NODE_DETAIL", detail={
            "steps":      step_counter,
            "durationMs": round((time.time() - t0) * 1000, 1),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["result"]     = final_content
        result.data_outputs["tool_calls"] = tool_call_log
        result.data_outputs["steps"]      = step_counter
        return result


# ── 4b. ToolAgentStreamNode ───────────────────────────────────────────────────
# ForLoop-style streaming agent — one executor loop iteration per reasoning step.
#
# Uses agent.astream_events() filtered to meaningful steps:
#   on_tool_start  → step_type="tool_call"
#   on_tool_end    → step_type="tool_result"
#   on_chain_end   → step_type="final" → returns COMPLETED
#
# Control ports:  exec (in)  |  loop_body (out)  |  completed (out)
# Data ports:     task, tools, model (in)
#                 step_type, step_content, tool_name, step_count (out per loop)
#                 result (out — set on COMPLETED)

async def _filtered_agent_events(raw_stream):
    """Yield only the meaningful steps from astream_events, skipping LLM token noise."""
    async for event in raw_stream:
        kind = event.get("event", "")
        name = event.get("name", "")
        data = event.get("data", {})

        if kind == "on_tool_start":
            inp = data.get("input", {})
            yield {"step_type": "tool_call",   "tool_name": name, "content": str(inp)[:300]}

        elif kind == "on_tool_end":
            out = data.get("output", "")
            if hasattr(out, "content"):  # ToolMessage
                out = out.content
            yield {"step_type": "tool_result", "tool_name": name, "content": str(out)[:300]}

        elif kind == "on_chain_end" and name == "LangGraph":
            msgs  = (data.get("output") or {}).get("messages", [])
            final = ""
            if msgs:
                last = msgs[-1]
                final = last.content if hasattr(last, "content") else str(last)
            yield {"step_type": "final", "tool_name": "", "content": final}


@_safe_register("ToolAgentStreamNode")
class ToolAgentStreamNode(Node):
    def __init__(self, name: str, type: str = "ToolAgentStreamNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True

        # ── Stream state ───────────────────────────────────────────────────────
        self._event_stream  = None
        self._step_counter  = 0
        self._stream_active = False

        # ── Control ports ──────────────────────────────────────────────────────
        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"] = OutputControlPort(self.id, "completed")

        # ── Data ports ─────────────────────────────────────────────────────────
        self.inputs["task"]          = InputDataPort(self.id, "task",         ValueType.STRING)
        self.inputs["tools"]         = InputDataPort(self.id, "tools",        ValueType.ANY)
        self.inputs["model"]         = InputDataPort(self.id, "model",        ValueType.STRING)
        self.outputs["step_type"]    = OutputDataPort(self.id, "step_type",   ValueType.STRING)
        self.outputs["step_content"] = OutputDataPort(self.id, "step_content",ValueType.STRING)
        self.outputs["tool_name"]    = OutputDataPort(self.id, "tool_name",   ValueType.STRING)
        self.outputs["step_count"]   = OutputDataPort(self.id, "step_count",  ValueType.INT)
        self.outputs["result"]       = OutputDataPort(self.id, "result",      ValueType.STRING)

        self.inputs["model"].value       = "gpt-4o-mini"
        self.inputs["tools"].value       = ["calculator", "word_count"]
        self.outputs["step_type"].value  = ""
        self.outputs["step_content"].value = ""
        self.outputs["tool_name"].value  = ""
        self.outputs["step_count"].value = 0
        self.outputs["result"].value     = ""

    async def compute(self, executionContext=None) -> ExecutionResult:
        from langchain.agents import create_agent

        # ── First entry: open the event stream ────────────────────────────────
        if not self._stream_active:
            ctx        = (executionContext or {}).get("data_inputs", {})
            task       = ctx.get("task",  self.inputs["task"].value)  or ""
            tool_names = ctx.get("tools", self.inputs["tools"].value) or ["calculator"]
            model_name = ctx.get("model", self.inputs["model"].value) or "gpt-4o-mini"

            if isinstance(tool_names, str):
                try:
                    import json as _json
                    tool_names = _json.loads(tool_names)
                except Exception:
                    tool_names = [tool_names]

            tools = [_TOOL_REGISTRY[t] for t in tool_names if t in _TOOL_REGISTRY]
            if not tools:
                raise ValueError(f"No valid tools. Available: {list(_TOOL_REGISTRY.keys())}")

            agent = create_agent(
                model=f"openai:{model_name}",
                tools=tools,
                system_prompt="You are a helpful assistant that uses tools to complete tasks.",
            )

            raw = agent.astream_events(
                {"messages": [{"role": "user", "content": task}]},
                version="v2",
            )
            self._event_stream  = _filtered_agent_events(raw)
            self._step_counter  = 0
            self._stream_active = True
            _fire_edge(self, "task", "agent_input", task[:120])

        # ── Each call: pull one meaningful step ───────────────────────────────
        try:
            step = await self._event_stream.__anext__()
            self._step_counter += 1

            stype   = step["step_type"]
            content = step["content"]
            tname   = step["tool_name"]

            self.outputs["step_type"].value    = stype
            self.outputs["step_content"].value = content
            self.outputs["tool_name"].value    = tname
            self.outputs["step_count"].value   = self._step_counter

            global_tracer.fire({
                "type":    "AGENT_STEP",
                "nodeId":  self.id,
                "step":    self._step_counter,
                "tool":    tname,
                "input":   content if stype == "tool_call"   else "",
                "output":  content if stype == "tool_result" else "",
            })

            if stype == "final":
                # Final answer — fire completed, not loop_body
                self.outputs["result"].value = content
                _fire(self, "NODE_DETAIL", detail={
                    "steps":    self._step_counter - 1,  # exclude the final step
                    "model":    self.inputs["model"].value,
                })
                self._event_stream  = None
                self._step_counter  = 0
                self._stream_active = False
                result = ExecutionResult(ExecCommand.COMPLETED)
                result.data_outputs["result"]       = content
                result.data_outputs["step_count"]   = self.outputs["step_count"].value
                result.control_outputs["completed"] = True
                result.control_outputs["loop_body"] = False
                return result

            result = ExecutionResult(ExecCommand.LOOP_AGAIN)
            result.data_outputs["step_type"]    = stype
            result.data_outputs["step_content"] = content
            result.data_outputs["tool_name"]    = tname
            result.data_outputs["step_count"]   = self._step_counter
            result.control_outputs["loop_body"] = True
            result.control_outputs["completed"] = False
            return result

        except StopAsyncIteration:
            # Fallback if stream ends without a "final" chain_end event
            self._stream_active = False
            result = ExecutionResult(ExecCommand.COMPLETED)
            result.control_outputs["completed"] = True
            result.control_outputs["loop_body"] = False
            return result


# ── 5. EmbeddingNode ───────────────────────────────────────────────────────────
# Converts text to a vector embedding (list[float]).
# Plugs directly into existing DotProductNode for similarity comparisons.
# Inputs:  text (str), model (str)
# Outputs: embedding (vector), dimensions (int)

@_safe_register("EmbeddingNode")
class EmbeddingNode(Node):
    def __init__(self, name: str, type: str = "EmbeddingNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["text"]        = InputDataPort(self.id, "text",       ValueType.STRING)
        self.inputs["model"]       = InputDataPort(self.id, "model",      ValueType.STRING)
        self.outputs["embedding"]  = OutputDataPort(self.id, "embedding", ValueType.VECTOR)
        self.outputs["dimensions"] = OutputDataPort(self.id, "dimensions",ValueType.INT)

        self.inputs["model"].value        = "text-embedding-3-small"
        self.outputs["embedding"].value   = []
        self.outputs["dimensions"].value  = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        from langchain_openai import OpenAIEmbeddings

        ctx   = (executionContext or {}).get("data_inputs", {})
        text  = ctx.get("text",  self.inputs["text"].value)  or ""
        model = ctx.get("model", self.inputs["model"].value) or "text-embedding-3-small"

        _fire_edge(self, "text", "embedder_input", text[:80])

        embedder  = OpenAIEmbeddings(model=model)
        t0        = time.time()
        embedding = await embedder.aembed_query(text)

        self.outputs["embedding"].value  = embedding
        self.outputs["dimensions"].value = len(embedding)

        _fire_edge(self, "embedder_output", "embedding", f"[{len(embedding)}d vector]")
        _fire(self, "NODE_DETAIL", detail={
            "model":      model,
            "dimensions": len(embedding),
            "durationMs": round((time.time() - t0) * 1000, 1),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["embedding"]  = embedding
        result.data_outputs["dimensions"] = len(embedding)
        return result


# ── 6. TextSplitterNode ────────────────────────────────────────────────────────
# Splits long text into overlapping chunks suited for embedding + retrieval.
# Useful as the first stage of a RAG pipeline.
# Inputs:  text (str), chunk_size (int), chunk_overlap (int)
# Outputs: chunks (any: list[str]), chunk_count (int)

@_safe_register("TextSplitterNode")
class TextSplitterNode(Node):
    def __init__(self, name: str, type: str = "TextSplitterNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["text"]          = InputDataPort(self.id, "text",          ValueType.STRING)
        self.inputs["chunk_size"]    = InputDataPort(self.id, "chunk_size",    ValueType.INT)
        self.inputs["chunk_overlap"] = InputDataPort(self.id, "chunk_overlap", ValueType.INT)
        self.outputs["chunks"]       = OutputDataPort(self.id, "chunks",       ValueType.ANY)
        self.outputs["chunk_count"]  = OutputDataPort(self.id, "chunk_count",  ValueType.INT)

        self.inputs["chunk_size"].value    = 512
        self.inputs["chunk_overlap"].value = 64
        self.outputs["chunks"].value       = []
        self.outputs["chunk_count"].value  = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        ctx     = (executionContext or {}).get("data_inputs", {})
        text    = ctx.get("text",          self.inputs["text"].value)          or ""
        size    = int(ctx.get("chunk_size",    self.inputs["chunk_size"].value)    or 512)
        overlap = int(ctx.get("chunk_overlap", self.inputs["chunk_overlap"].value) or 64)

        splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
        chunks   = splitter.split_text(text)

        self.outputs["chunks"].value      = chunks
        self.outputs["chunk_count"].value = len(chunks)

        _fire(self, "NODE_DETAIL", detail={
            "chunkCount":  len(chunks),
            "chunkSize":   size,
            "overlap":     overlap,
            "totalChars":  len(text),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["chunks"]      = chunks
        result.data_outputs["chunk_count"] = len(chunks)
        return result


# ── ImageGenNode ──────────────────────────────────────────────────────────────
# Calls the OpenAI image-generation API (DALL-E 3) and returns the URL.
#
# Data ports:  prompt (in str)  |  model (in str, default dall-e-3)
#              size   (in str)  |  url (out str)  |  revised_prompt (out str)

@_safe_register("ImageGenNode")
class ImageGenNode(Node):
    def __init__(self, name: str, type: str = "ImageGenNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["prompt"]  = InputDataPort(self.id, "prompt",  ValueType.STRING)
        self.inputs["model"]   = InputDataPort(self.id, "model",   ValueType.STRING)
        self.inputs["size"]    = InputDataPort(self.id, "size",    ValueType.STRING)
        self.outputs["url"]            = OutputDataPort(self.id, "url",            ValueType.STRING)
        self.outputs["revised_prompt"] = OutputDataPort(self.id, "revised_prompt", ValueType.STRING)

        self.inputs["prompt"].value  = "A red fox in a snow-covered forest, digital art"
        self.inputs["model"].value   = "dall-e-3"
        self.inputs["size"].value    = "1024x1024"
        self.outputs["url"].value            = ""
        self.outputs["revised_prompt"].value = ""

    async def compute(self, executionContext=None) -> ExecutionResult:
        import openai

        ctx    = (executionContext or {}).get("data_inputs", {})
        prompt = ctx.get("prompt", self.inputs["prompt"].value) or "a beautiful landscape"
        model  = ctx.get("model",  self.inputs["model"].value)  or "dall-e-3"
        size   = ctx.get("size",   self.inputs["size"].value)   or "1024x1024"

        _fire_edge(self, "prompt", "image_gen_input", prompt[:120])

        client = openai.AsyncOpenAI()
        t0 = time.time()
        resp = await client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            response_format="url",
            n=1,
        )
        duration = (time.time() - t0) * 1000

        url            = resp.data[0].url or ""
        revised_prompt = getattr(resp.data[0], "revised_prompt", "") or ""

        self.outputs["url"].value            = url
        self.outputs["revised_prompt"].value = revised_prompt

        _fire_edge(self, "url", "image_gen_output", url[:120])
        _fire(self, "NODE_DETAIL", detail={
            "url":            url,
            "model":          model,
            "size":           size,
            "durationMs":     round(duration, 1),
            "revised_prompt": revised_prompt[:200] if revised_prompt else "",
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["url"]            = url
        result.data_outputs["revised_prompt"] = revised_prompt
        return result


# ── GPT4VisionNode ────────────────────────────────────────────────────────────
# Sends an image URL to GPT-4o vision and returns a text critique/answer.
#
# Data ports:  url (in str)  |  question (in str)  |  model (in str)
#              critique (out str)

@_safe_register("GPT4VisionNode")
class GPT4VisionNode(Node):
    def __init__(self, name: str, type: str = "GPT4VisionNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["url"]      = InputDataPort(self.id, "url",      ValueType.STRING)
        self.inputs["question"] = InputDataPort(self.id, "question", ValueType.STRING)
        self.inputs["model"]    = InputDataPort(self.id, "model",    ValueType.STRING)
        self.outputs["critique"] = OutputDataPort(self.id, "critique", ValueType.STRING)

        self.inputs["url"].value      = ""
        self.inputs["question"].value = (
            "Critique this image in detail. What elements are missing, "
            "incorrect, or could be improved? Be specific and constructive."
        )
        self.inputs["model"].value    = "gpt-4o"
        self.outputs["critique"].value = ""

    async def compute(self, executionContext=None) -> ExecutionResult:
        import openai

        ctx      = (executionContext or {}).get("data_inputs", {})
        url      = ctx.get("url",      self.inputs["url"].value)      or ""
        question = ctx.get("question", self.inputs["question"].value) or "Describe this image."
        model    = ctx.get("model",    self.inputs["model"].value)    or "gpt-4o"

        if not url:
            self.outputs["critique"].value = "[no image url provided]"
            result = ExecutionResult(ExecCommand.CONTINUE)
            result.data_outputs["critique"] = "[no image url provided]"
            return result

        _fire_edge(self, "url", "vision_input", url[:120])

        client = openai.AsyncOpenAI()
        t0 = time.time()
        response = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text",      "text": question},
                ],
            }],
            max_tokens=500,
        )
        duration = (time.time() - t0) * 1000

        critique = response.choices[0].message.content or ""
        self.outputs["critique"].value = critique

        _fire_edge(self, "critique", "vision_output", critique[:120])
        _fire(self, "NODE_DETAIL", detail={
            "critique":   critique[:400],
            "model":      model,
            "durationMs": round(duration, 1),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["critique"] = critique
        return result


# ── PromptRefinerNode ─────────────────────────────────────────────────────────
# Calls an LLM to rewrite an image-gen prompt based on a vision critique.
#
# Data ports:  original_prompt (in str)  |  critique (in str)  |  model (in str)
#              refined_prompt (out str)

@_safe_register("PromptRefinerNode")
class PromptRefinerNode(Node):
    def __init__(self, name: str, type: str = "PromptRefinerNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["original_prompt"] = InputDataPort(self.id, "original_prompt", ValueType.STRING)
        self.inputs["critique"]        = InputDataPort(self.id, "critique",        ValueType.STRING)
        self.inputs["model"]           = InputDataPort(self.id, "model",           ValueType.STRING)
        self.outputs["refined_prompt"] = OutputDataPort(self.id, "refined_prompt", ValueType.STRING)

        self.inputs["original_prompt"].value = ""
        self.inputs["critique"].value        = ""
        self.inputs["model"].value           = "gpt-4o-mini"
        self.outputs["refined_prompt"].value  = ""

    async def compute(self, executionContext=None) -> ExecutionResult:
        import openai

        ctx             = (executionContext or {}).get("data_inputs", {})
        original_prompt = ctx.get("original_prompt", self.inputs["original_prompt"].value) or ""
        critique        = ctx.get("critique",        self.inputs["critique"].value)        or ""
        model           = ctx.get("model",           self.inputs["model"].value)           or "gpt-4o-mini"

        system = (
            "You are an expert image prompt engineer for DALL-E 3. "
            "Given an original image generation prompt and a critique of the resulting image, "
            "rewrite the prompt to address every issue raised in the critique. "
            "Output ONLY the improved prompt — no explanation, no preamble, no quotes."
        )
        user_msg = (
            f"Original prompt:\n{original_prompt}\n\n"
            f"Critique of the generated image:\n{critique}\n\n"
            "Rewrite the prompt to fix the issues described."
        )

        client = openai.AsyncOpenAI()
        t0 = time.time()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user_msg},
            ],
            max_tokens=300,
        )
        duration = (time.time() - t0) * 1000

        refined = (response.choices[0].message.content or original_prompt).strip()
        self.outputs["refined_prompt"].value = refined

        _fire_edge(self, "refined_prompt", "refiner_output", refined[:120])
        _fire(self, "NODE_DETAIL", detail={
            "refined_prompt": refined[:400],
            "model":          model,
            "durationMs":     round(duration, 1),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["refined_prompt"] = refined
        return result


# ── AnonymizerNode ────────────────────────────────────────────────────────────
# Detects and anonymizes PII in text using Microsoft Presidio.
#
# Requirements (optional — loaded lazily at execute time):
#   pip install presidio-analyzer presidio-anonymizer
#   python -m spacy download en_core_web_lg
#
# Inputs:
#   text               (STRING) — raw text that may contain PII
#   language           (STRING) — ISO language code, default "en"
#   entities_to_detect (ANY)    — list of entity types to redact;
#                                 None / [] = detect all supported types
#   operator           (STRING) — "replace" | "redact" | "hash" | "mask"
#                                 default "replace" → <PERSON>, <EMAIL_ADDRESS>, …
# Outputs:
#   anonymized   (STRING) — text with PII handled by the chosen operator
#   entities     (ANY)    — list of {type, score, start, end, text} dicts
#   entity_count (INT)    — number of PII entities detected

_DEFAULT_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
    "US_SSN", "IP_ADDRESS", "LOCATION", "DATE_TIME",
    "URL", "NRP", "MEDICAL_LICENSE", "IBAN_CODE",
]


@_safe_register("AnonymizerNode")
class AnonymizerNode(Node):
    def __init__(self, name: str, type: str = "AnonymizerNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["text"]               = InputDataPort(self.id, "text",               ValueType.STRING)
        self.inputs["language"]           = InputDataPort(self.id, "language",           ValueType.STRING)
        self.inputs["entities_to_detect"] = InputDataPort(self.id, "entities_to_detect", ValueType.ANY)
        self.inputs["operator"]           = InputDataPort(self.id, "operator",           ValueType.STRING)
        self.outputs["anonymized"]        = OutputDataPort(self.id, "anonymized",        ValueType.STRING)
        self.outputs["entities"]          = OutputDataPort(self.id, "entities",          ValueType.ANY)
        self.outputs["entity_count"]      = OutputDataPort(self.id, "entity_count",      ValueType.INT)

        self.inputs["language"].value           = "en"
        self.inputs["entities_to_detect"].value = _DEFAULT_ENTITIES
        self.inputs["operator"].value           = "replace"
        self.outputs["anonymized"].value        = ""
        self.outputs["entities"].value          = []
        self.outputs["entity_count"].value      = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        try:
            from presidio_analyzer         import AnalyzerEngine
            from presidio_anonymizer       import AnonymizerEngine
            from presidio_anonymizer.entities import OperatorConfig
        except ImportError:
            raise ImportError(
                "AnonymizerNode requires presidio-analyzer and presidio-anonymizer.\n"
                "Install with:\n"
                "  pip install presidio-analyzer presidio-anonymizer\n"
                "  python -m spacy download en_core_web_lg"
            )

        ctx      = (executionContext or {}).get("data_inputs", {}) if executionContext else {}
        text     = ctx.get("text",               self.inputs["text"].value)               or ""
        language = ctx.get("language",           self.inputs["language"].value)           or "en"
        entities = ctx.get("entities_to_detect", self.inputs["entities_to_detect"].value)
        operator = ctx.get("operator",           self.inputs["operator"].value)           or "replace"

        # Empty list → detect all; None → detect all
        entity_filter = entities if entities else None

        t0 = time.time()
        _fire(self, "NODE_START")

        analyzer   = AnalyzerEngine()
        anonymizer = AnonymizerEngine()

        analysis_results  = analyzer.analyze(
            text=text,
            language=language,
            entities=entity_filter,
        )
        anonymized_result = anonymizer.anonymize(
            text=text,
            analyzer_results=analysis_results,
            operators={"DEFAULT": OperatorConfig(operator)},
        )
        duration = (time.time() - t0) * 1000

        anonymized_text = anonymized_result.text
        entity_list = [
            {
                "type":  r.entity_type,
                "score": round(r.score, 3),
                "start": r.start,
                "end":   r.end,
                "text":  text[r.start:r.end],
            }
            for r in sorted(analysis_results, key=lambda r: r.start)
        ]

        self.outputs["anonymized"].value   = anonymized_text
        self.outputs["entities"].value     = entity_list
        self.outputs["entity_count"].value = len(entity_list)

        _fire(self, "NODE_DETAIL", detail={
            "entity_count": len(entity_list),
            "entities":     [e["type"] for e in entity_list],
            "operator":     operator,
            "durationMs":   round(duration, 1),
        })
        _fire_edge(self, "anonymized", "anonymizer_output", anonymized_text[:200])

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["anonymized"]   = anonymized_text
        result.data_outputs["entities"]     = entity_list
        result.data_outputs["entity_count"] = len(entity_list)
        return result


# ── SummarizerNode ────────────────────────────────────────────────────────────
# Summarizes text using an OpenAI chat model.
# Intended to receive anonymized text from AnonymizerNode so PII never
# reaches the LLM in the prompt.
#
# Inputs:
#   text       (STRING) — text to summarize (ideally already anonymized)
#   max_length (INT)    — target maximum word count for the summary, default 150
#   style      (STRING) — "paragraph" | "bullet" | "headline", default "paragraph"
#   model      (STRING) — OpenAI model name, default "gpt-4o-mini"
# Outputs:
#   summary           (STRING) — the generated summary
#   word_count        (INT)    — word count of the summary
#   compression_ratio (FLOAT)  — len(summary) / len(input_text)

@_safe_register("SummarizerNode")
class SummarizerNode(Node):
    def __init__(self, name: str, type: str = "SummarizerNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.inputs["text"]       = InputDataPort(self.id, "text",       ValueType.STRING)
        self.inputs["max_length"] = InputDataPort(self.id, "max_length", ValueType.INT)
        self.inputs["style"]      = InputDataPort(self.id, "style",      ValueType.STRING)
        self.inputs["model"]      = InputDataPort(self.id, "model",      ValueType.STRING)
        self.outputs["summary"]           = OutputDataPort(self.id, "summary",           ValueType.STRING)
        self.outputs["word_count"]        = OutputDataPort(self.id, "word_count",        ValueType.INT)
        self.outputs["compression_ratio"] = OutputDataPort(self.id, "compression_ratio", ValueType.FLOAT)

        self.inputs["text"].value       = ""
        self.inputs["max_length"].value = 150
        self.inputs["style"].value      = "paragraph"   # paragraph | bullet | headline
        self.inputs["model"].value      = "gpt-4o-mini"
        self.outputs["summary"].value           = ""
        self.outputs["word_count"].value        = 0
        self.outputs["compression_ratio"].value = 0.0

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx        = (executionContext or {}).get("data_inputs", {}) if executionContext else {}
        text       = ctx.get("text",       self.inputs["text"].value)       or ""
        max_length = ctx.get("max_length", self.inputs["max_length"].value) or 150
        style      = ctx.get("style",      self.inputs["style"].value)      or "paragraph"
        model      = ctx.get("model",      self.inputs["model"].value)      or "gpt-4o-mini"

        style_instruction = {
            "bullet":    f"Summarise in concise bullet points. Maximum {max_length} words total.",
            "headline":  f"Summarise in a single headline sentence. Maximum {max_length} words.",
            "paragraph": f"Summarise in flowing prose. Maximum {max_length} words.",
        }.get(style, f"Summarise in maximum {max_length} words.")

        system_msg = (
            "You are a professional summariser. "
            "Produce a concise, accurate summary of the provided text. "
            f"{style_instruction} "
            "Do not add information not present in the source text. "
            "Output ONLY the summary — no preamble, no labels, no explanations."
        )

        import openai

        t0 = time.time()
        _fire(self, "NODE_START")

        client   = openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": text},
            ],
        )
        duration = (time.time() - t0) * 1000

        summary   = (response.choices[0].message.content or "").strip()
        wc        = len(summary.split())
        ratio     = round(len(summary) / max(len(text), 1), 3)

        self.outputs["summary"].value           = summary
        self.outputs["word_count"].value        = wc
        self.outputs["compression_ratio"].value = ratio

        _fire(self, "NODE_DETAIL", detail={
            "word_count":        wc,
            "compression_ratio": ratio,
            "style":             style,
            "durationMs":        round(duration, 1),
        })
        _fire_edge(self, "summary", "summarizer_output", summary[:200])

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["summary"]           = summary
        result.data_outputs["word_count"]        = wc
        result.data_outputs["compression_ratio"] = ratio
        return result
