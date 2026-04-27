"""
pydantic-ai node types — drop-in replacements for langchain_nodes.py.

These nodes have identical type names and port layouts to the LangChain
equivalents so existing graphs continue to work.  Their compute() methods
use only:
  - pydantic-ai  (LLMNode, LLMStreamNode, ToolAgentNode, ToolAgentStreamNode)
  - openai       (EmbeddingNode — raw SDK, no LangChain)
  - pure Python  (PromptTemplateNode, TextSplitterNode)

Requirements:
    pydantic-ai openai

Environment variable:

    OPENAI_API_KEY
"""
from __future__ import annotations

import asyncio
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


# ── Registration helper ────────────────────────────────────────────────────────

def _safe_register(type_name: str):
    """Decorator that registers *cls* only when *type_name* is not yet in the registry."""
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


# ── Sentinel for async queue end-of-stream ────────────────────────────────────

_SENTINEL = object()


# ── 1. PromptTemplateNode ──────────────────────────────────────────────────────
# Pure-Python str.format_map() replacement — zero external dependencies.
# Input:  template (str)  e.g. "Answer this: {question}"
#         variables (any) dict or JSON string
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
        ctx       = (executionContext or {}).get("data_inputs", {})
        tmpl      = ctx.get("template",  self.inputs["template"].value)  or "{input}"
        variables = ctx.get("variables", self.inputs["variables"].value) or {}

        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except json.JSONDecodeError:
                variables = {}

        try:
            rendered = tmpl.format_map(variables)
        except KeyError:
            rendered = tmpl  # missing key → return template as-is

        self.outputs["prompt"].value = rendered
        _fire_edge(self, "template", "rendered_prompt", rendered[:120])

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["prompt"] = rendered
        return result


# ── 2. LLMNode ─────────────────────────────────────────────────────────────────
# Single-shot blocking LLM call via pydantic-ai Agent.
# Inputs:  prompt, system_prompt, model, temperature
# Outputs: response (str), model_used (str), tokens_used (int)

@_safe_register("LLMNode")
class LLMNode(Node):
    def __init__(self, name: str, type: str = "LLMNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_durable_step = True  # LLM calls are exactly-once via DBOS step
        self.inputs["prompt"]        = InputDataPort(self.id, "prompt",        ValueType.STRING)
        self.inputs["system_prompt"] = InputDataPort(self.id, "system_prompt", ValueType.STRING)
        self.inputs["model"]         = InputDataPort(self.id, "model",         ValueType.STRING)
        self.inputs["temperature"]   = InputDataPort(self.id, "temperature",   ValueType.FLOAT)
        self.outputs["response"]     = OutputDataPort(self.id, "response",     ValueType.STRING)
        self.outputs["model_used"]   = OutputDataPort(self.id, "model_used",   ValueType.STRING)
        self.outputs["tokens_used"]  = OutputDataPort(self.id, "tokens_used",  ValueType.INT)

        self.inputs["model"].value         = "openai:gpt-4o-mini"
        self.inputs["temperature"].value   = 0.7
        self.inputs["system_prompt"].value = "You are a helpful assistant."
        self.outputs["response"].value     = ""
        self.outputs["model_used"].value   = "openai:gpt-4o-mini"
        self.outputs["tokens_used"].value  = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        from pydantic_ai import Agent
        from pydantic_ai.settings import ModelSettings

        ctx         = (executionContext or {}).get("data_inputs", {})
        prompt      = ctx.get("prompt",        self.inputs["prompt"].value)        or ""
        system      = ctx.get("system_prompt", self.inputs["system_prompt"].value) or \
                      "You are a helpful assistant."
        model_name  = ctx.get("model",         self.inputs["model"].value)         or \
                      "openai:gpt-4o-mini"
        temperature = float(ctx.get("temperature", self.inputs["temperature"].value) or 0.7)

        _fire_edge(self, "prompt", "llm_input", prompt[:120])

        agent = Agent(model_name, instructions=system, output_type=str)

        t0         = time.time()
        result_obj = await agent.run(
            prompt,
            model_settings=ModelSettings(temperature=temperature),
        )
        duration   = (time.time() - t0) * 1000

        content     = result_obj.output or ""
        tokens_used = 0
        usage       = result_obj.usage()
        if usage:
            tokens_used = (usage.total_tokens or 0)

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
# ForLoop-style streaming LLM node — one text chunk per compute() call.
#
# Uses asyncio.Queue + background task to bridge pydantic-ai's context-manager
# streaming API into the LOOP_AGAIN execution model.
#
# Control ports:  exec (in)  |  loop_body (out)  |  completed (out)
# Data ports:     prompt, system_prompt, model (in)
#                 chunk, accumulated, chunk_count, response (out)

@_safe_register("LLMStreamNode")
class LLMStreamNode(Node):
    def __init__(self, name: str, type: str = "LLMStreamNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True  # LLM stream calls are exactly-once via DBOS step
        # ── Stream state ──────────────────────────────────────────────────
        self._queue:        asyncio.Queue | None = None
        self._task:         asyncio.Task  | None = None
        self._accumulated   = ""
        self._chunk_count   = 0
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

        self.inputs["model"].value         = "openai:gpt-4o-mini"
        self.inputs["system_prompt"].value = "You are a helpful assistant."
        self.outputs["chunk"].value        = ""
        self.outputs["accumulated"].value  = ""
        self.outputs["chunk_count"].value  = 0
        self.outputs["response"].value     = ""

    async def _run_stream(
        self, prompt: str, system: str, model: str, queue: asyncio.Queue
    ) -> None:
        """Background coroutine: streams text deltas into the queue."""
        try:
            from pydantic_ai import Agent
            agent = Agent(model, instructions=system, output_type=str)
            async with agent.run_stream(prompt) as run:
                async for delta in run.stream_text(delta=True):
                    await queue.put(delta)
        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(_SENTINEL)

    async def compute(self, executionContext=None) -> ExecutionResult:
        # ── First entry: open stream ───────────────────────────────────────
        if not self._stream_active:
            ctx    = (executionContext or {}).get("data_inputs", {})
            prompt = ctx.get("prompt",        self.inputs["prompt"].value)        or ""
            system = ctx.get("system_prompt", self.inputs["system_prompt"].value) or \
                     "You are a helpful assistant."
            model  = ctx.get("model",         self.inputs["model"].value)         or \
                     "openai:gpt-4o-mini"

            self._queue         = asyncio.Queue()
            self._accumulated   = ""
            self._chunk_count   = 0
            self._stream_active = True
            self._task          = asyncio.create_task(
                self._run_stream(prompt, system, model, self._queue)
            )
            _fire_edge(self, "prompt", "llm_input", prompt[:120])

        # ── Pull one chunk ─────────────────────────────────────────────────
        piece = await self._queue.get()

        if piece is _SENTINEL or isinstance(piece, Exception):
            # Stream exhausted or errored
            if isinstance(piece, Exception):
                self.outputs["response"].value = f"[Error: {piece}]"
            else:
                self.outputs["response"].value = self._accumulated
            self.outputs["chunk"].value       = ""
            self.outputs["chunk_count"].value = self._chunk_count

            _fire_edge(self, "llm_output", "response", self._accumulated[:120])
            _fire(self, "NODE_DETAIL", detail={
                "model":      self.inputs["model"].value,
                "chunks":     self._chunk_count,
                "characters": len(self._accumulated),
            })

            self._queue = self._task = None
            self._accumulated = ""
            self._chunk_count = 0
            self._stream_active = False

            result = ExecutionResult(ExecCommand.COMPLETED)
            result.data_outputs["response"]     = self.outputs["response"].value
            result.control_outputs["completed"] = True
            result.control_outputs["loop_body"] = False
            return result

        # ── Got a real chunk ───────────────────────────────────────────────
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
        result.data_outputs["chunk"]        = piece
        result.data_outputs["accumulated"]  = self._accumulated
        result.data_outputs["chunk_count"]  = self._chunk_count
        result.control_outputs["loop_body"] = True
        result.control_outputs["completed"] = False
        return result


# ── 4a. Tool builder ───────────────────────────────────────────────────────────

def _build_agent_with_tools(model: str, system: str, tool_names: list) -> "object":
    """
    Construct a pydantic-ai Agent, registering the requested built-in tools.
    Supported tool_names: "calculator", "word_count"
    """
    from pydantic_ai import Agent

    agent: Agent = Agent(model, instructions=system, output_type=str)

    if "calculator" in tool_names:
        @agent.tool_plain
        def calculator(expression: str) -> str:
            """Evaluate a simple Python maths expression. E.g. '2 + 3 * 4'."""
            try:
                return str(eval(expression, {"__builtins__": {}}, {}))
            except Exception as exc:
                return f"Error: {exc}"

    if "word_count" in tool_names:
        @agent.tool_plain
        def word_count(text: str) -> str:
            """Count the number of words in a text string."""
            return str(len(text.split()))

    return agent


# ── 4b. ToolAgentNode ──────────────────────────────────────────────────────────
# Single-shot ReAct agent — runs to completion, returns final answer.
# Uses run_stream_events() so each tool call fires a trace event incrementally.
# Inputs:  task (str), tools (any: list[str]), model (str)
# Outputs: result (str), tool_calls (any: list[dict]), steps (int)

@_safe_register("ToolAgentNode")
class ToolAgentNode(Node):
    def __init__(self, name: str, type: str = "ToolAgentNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_durable_step = True  # Agent tool calls are exactly-once via DBOS step
        self.inputs["task"]        = InputDataPort(self.id, "task",        ValueType.STRING)
        self.inputs["tools"]       = InputDataPort(self.id, "tools",       ValueType.ANY)
        self.inputs["model"]       = InputDataPort(self.id, "model",       ValueType.STRING)
        self.outputs["result"]     = OutputDataPort(self.id, "result",     ValueType.STRING)
        self.outputs["tool_calls"] = OutputDataPort(self.id, "tool_calls", ValueType.ANY)
        self.outputs["steps"]      = OutputDataPort(self.id, "steps",      ValueType.INT)

        self.inputs["model"].value       = "openai:gpt-4o-mini"
        self.inputs["tools"].value       = ["calculator", "word_count"]
        self.outputs["result"].value     = ""
        self.outputs["tool_calls"].value = []
        self.outputs["steps"].value      = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        from pydantic_ai import (
            FunctionToolCallEvent,
            FunctionToolResultEvent,
            AgentRunResultEvent,
        )

        ctx        = (executionContext or {}).get("data_inputs", {})
        task       = ctx.get("task",  self.inputs["task"].value)  or ""
        tool_names = ctx.get("tools", self.inputs["tools"].value) or ["calculator"]
        model_name = ctx.get("model", self.inputs["model"].value) or "openai:gpt-4o-mini"

        if isinstance(tool_names, str):
            try:
                tool_names = json.loads(tool_names)
            except json.JSONDecodeError:
                tool_names = [tool_names]

        _fire_edge(self, "task", "agent_input", task[:120])

        agent = _build_agent_with_tools(
            model_name,
            "You are a helpful assistant that uses tools to complete tasks.",
            tool_names,
        )

        t0            = time.time()
        tool_call_log: list[dict] = []
        step_counter  = 0
        final_content = ""

        # pending_call_ids maps tool_call_id → index in tool_call_log
        pending: dict[str, int] = {}

        async for event in agent.run_stream_events(task):
            if isinstance(event, FunctionToolCallEvent):
                step_counter += 1
                idx = len(tool_call_log)
                step = {
                    "step":   step_counter,
                    "tool":   event.part.tool_name,
                    "input":  str(event.part.args)[:200],
                    "output": "",
                }
                tool_call_log.append(step)
                pending[event.part.tool_call_id] = idx
                global_tracer.fire({"type": "AGENT_STEP", "nodeId": self.id, **step})
                _fire_edge(self, f"tool_{event.part.tool_name}", "tool_call", str(event.part.args)[:120])

            elif isinstance(event, FunctionToolResultEvent):
                content = str(event.result.content)[:200]
                idx = pending.get(event.tool_call_id)
                if idx is not None:
                    tool_call_log[idx]["output"] = content

            elif isinstance(event, AgentRunResultEvent):
                final_content = str(event.result.output or "")

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


# ── 4c. ToolAgentStreamNode ────────────────────────────────────────────────────
# ForLoop-style streaming agent — one step (tool_call/tool_result/final)
# per compute() call.
#
# Uses asyncio.Queue + background task to bridge pydantic-ai's async-for
# event stream into the LOOP_AGAIN execution model.
#
# Control ports:  exec (in)  |  loop_body (out)  |  completed (out)
# Data ports:     task, tools, model (in)
#                 step_type, step_content, tool_name, step_count (out per loop)
#                 result (out — set when step_type=="final")

@_safe_register("ToolAgentStreamNode")
class ToolAgentStreamNode(Node):
    def __init__(self, name: str, type: str = "ToolAgentStreamNode", **kwargs):
        super().__init__(name, type, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True  # Agent stream calls are exactly-once via DBOS step
        # ── Stream state ──────────────────────────────────────────────────────
        self._queue:         asyncio.Queue | None = None
        self._task:          asyncio.Task  | None = None
        self._step_counter   = 0
        self._stream_active  = False

        # ── Control ports ─────────────────────────────────────────────────────
        self.inputs["exec"]       = InputControlPort(self.id, "exec")
        self.outputs["loop_body"] = OutputControlPort(self.id, "loop_body")
        self.outputs["completed"] = OutputControlPort(self.id, "completed")

        # ── Data ports ────────────────────────────────────────────────────────
        self.inputs["task"]          = InputDataPort(self.id, "task",         ValueType.STRING)
        self.inputs["tools"]         = InputDataPort(self.id, "tools",        ValueType.ANY)
        self.inputs["model"]         = InputDataPort(self.id, "model",        ValueType.STRING)
        self.outputs["step_type"]    = OutputDataPort(self.id, "step_type",   ValueType.STRING)
        self.outputs["step_content"] = OutputDataPort(self.id, "step_content",ValueType.STRING)
        self.outputs["tool_name"]    = OutputDataPort(self.id, "tool_name",   ValueType.STRING)
        self.outputs["step_count"]   = OutputDataPort(self.id, "step_count",  ValueType.INT)
        self.outputs["result"]       = OutputDataPort(self.id, "result",      ValueType.STRING)

        self.inputs["model"].value         = "openai:gpt-4o-mini"
        self.inputs["tools"].value         = ["calculator", "word_count"]
        self.outputs["step_type"].value    = ""
        self.outputs["step_content"].value = ""
        self.outputs["tool_name"].value    = ""
        self.outputs["step_count"].value   = 0
        self.outputs["result"].value       = ""

    async def _run_agent_events(
        self,
        task: str,
        tool_names: list,
        model: str,
        queue: asyncio.Queue,
    ) -> None:
        """Background task: filters agent events and pushes steps to queue."""
        try:
            from pydantic_ai import (
                FunctionToolCallEvent,
                FunctionToolResultEvent,
                AgentRunResultEvent,
            )

            agent = _build_agent_with_tools(
                model,
                "You are a helpful assistant that uses tools to complete tasks.",
                tool_names,
            )

            async for event in agent.run_stream_events(task):
                if isinstance(event, FunctionToolCallEvent):
                    await queue.put({
                        "step_type": "tool_call",
                        "tool_name": event.part.tool_name,
                        "content":   str(event.part.args)[:300],
                    })
                elif isinstance(event, FunctionToolResultEvent):
                    await queue.put({
                        "step_type": "tool_result",
                        "tool_name": "",
                        "content":   str(event.result.content)[:300],
                    })
                elif isinstance(event, AgentRunResultEvent):
                    await queue.put({
                        "step_type": "final",
                        "tool_name": "",
                        "content":   str(event.result.output or ""),
                    })

        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(_SENTINEL)

    def _cleanup(self) -> None:
        """Reset stream state after a run ends."""
        self._queue        = None
        self._task         = None
        self._step_counter = 0
        self._stream_active = False

    async def compute(self, executionContext=None) -> ExecutionResult:
        # ── First call: launch background task ────────────────────────────
        if not self._stream_active:
            ctx        = (executionContext or {}).get("data_inputs", {})
            task       = ctx.get("task",  self.inputs["task"].value)  or ""
            tool_names = ctx.get("tools", self.inputs["tools"].value) or ["calculator"]
            model_name = ctx.get("model", self.inputs["model"].value) or "openai:gpt-4o-mini"

            if isinstance(tool_names, str):
                try:
                    tool_names = json.loads(tool_names)
                except json.JSONDecodeError:
                    tool_names = [tool_names]

            self._queue         = asyncio.Queue()
            self._step_counter  = 0
            self._stream_active = True
            self._task          = asyncio.create_task(
                self._run_agent_events(task, tool_names, model_name, self._queue)
            )
            _fire_edge(self, "task", "agent_input", task[:120])

        # ── Pull next step ─────────────────────────────────────────────────
        step = await self._queue.get()

        if step is _SENTINEL or isinstance(step, Exception):
            if isinstance(step, Exception):
                _fire(self, "NODE_DETAIL", detail={"error": str(step)})
            self._cleanup()
            result = ExecutionResult(ExecCommand.COMPLETED)
            result.control_outputs["completed"] = True
            result.control_outputs["loop_body"] = False
            return result

        self._step_counter += 1

        stype   = step["step_type"]
        content = step["content"]
        tname   = step["tool_name"]

        self.outputs["step_type"].value    = stype
        self.outputs["step_content"].value = content
        self.outputs["tool_name"].value    = tname
        self.outputs["step_count"].value   = self._step_counter

        global_tracer.fire({
            "type":   "AGENT_STEP",
            "nodeId": self.id,
            "step":   self._step_counter,
            "tool":   tname,
            "input":  content if stype == "tool_call"   else "",
            "output": content if stype == "tool_result" else "",
        })

        if stype == "final":
            self.outputs["result"].value = content
            _fire(self, "NODE_DETAIL", detail={
                "steps":    self._step_counter - 1,  # exclude the final step itself
                "model":    self.inputs["model"].value,
            })
            step_count = self._step_counter
            self._cleanup()

            result = ExecutionResult(ExecCommand.COMPLETED)
            result.data_outputs["result"]       = content
            result.data_outputs["step_count"]   = step_count
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


# ── 5. EmbeddingNode ───────────────────────────────────────────────────────────
# Pure openai SDK — identical ports to the LangChain version.
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

        self.inputs["model"].value       = "text-embedding-3-small"
        self.outputs["embedding"].value  = []
        self.outputs["dimensions"].value = 0

    async def compute(self, executionContext=None) -> ExecutionResult:
        import openai

        ctx   = (executionContext or {}).get("data_inputs", {})
        text  = ctx.get("text",  self.inputs["text"].value)  or ""
        model = ctx.get("model", self.inputs["model"].value) or "text-embedding-3-small"

        _fire_edge(self, "text", "embedder_input", text[:80])

        client    = openai.AsyncOpenAI()
        t0        = time.time()
        resp      = await client.embeddings.create(model=model, input=text)
        embedding = resp.data[0].embedding

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
# Pure-Python character-level sliding-window chunker — no LangChain dependency.
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

    @staticmethod
    def _split(text: str, chunk_size: int, overlap: int) -> list:
        """
        Character-level overlapping chunker.
        Steps forward by (chunk_size - overlap) characters each iteration,
        producing chunks of at most *chunk_size* characters.
        """
        if not text or chunk_size <= 0:
            return []
        step    = max(1, chunk_size - overlap)
        chunks  = []
        start   = 0
        n       = len(text)
        while start < n:
            end = min(start + chunk_size, n)
            chunks.append(text[start:end])
            if end >= n:
                break
            start += step
        return [c for c in chunks if c.strip()]

    async def compute(self, executionContext=None) -> ExecutionResult:
        ctx     = (executionContext or {}).get("data_inputs", {})
        text    = ctx.get("text",          self.inputs["text"].value)          or ""
        size    = int(ctx.get("chunk_size",    self.inputs["chunk_size"].value)    or 512)
        overlap = int(ctx.get("chunk_overlap", self.inputs["chunk_overlap"].value) or 64)

        chunks = self._split(text, size, overlap)

        self.outputs["chunks"].value      = chunks
        self.outputs["chunk_count"].value = len(chunks)

        _fire(self, "NODE_DETAIL", detail={
            "chunkCount": len(chunks),
            "chunkSize":  size,
            "overlap":    overlap,
            "totalChars": len(text),
        })

        result = ExecutionResult(ExecCommand.CONTINUE)
        result.data_outputs["chunks"]      = chunks
        result.data_outputs["chunk_count"] = len(chunks)
        return result
