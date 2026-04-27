"""
AgentNodes — pydantic-ai powered nodes for the NodeGraph execution engine.

These nodes expose LLM / agent capabilities as first-class graph nodes so
they can be wired together like any other computation in a NodeNetwork.

Three nodes are provided:

  PydanticAgentNode  — full pydantic-ai agent loop with optional tool nodes.
  LLMCallNode        — single, stateless LLM call (prompt → response).
  AgentPlannerNode   — wraps AgentExecutor.plan() to build a graph from a
                       natural-language objective.
"""

from __future__ import annotations

from typing import Any

from ..core.Node import Node
from ..core.Executor import ExecCommand, ExecutionResult
from ..core.NodePort import ValueType


# ─────────────────────────────────────────────────────────────────────────────
# PydanticAgentNode
# ─────────────────────────────────────────────────────────────────────────────

@Node.register("PydanticAgentNode")
class PydanticAgentNode(Node):
    """
    Runs a pydantic-ai agent loop and exposes the result on data output ports.

    Inputs (data)
    -------------
    objective   : STRING  — the user-facing task for the agent.
    context_data: DICT    — optional structured context injected as deps.
    vault       : DICT    — optional secret/config dictionary passed as deps.
    model       : STRING  — model identifier, e.g. "openai:gpt-4o".
    tool_types  : STRING  — comma-separated node type names to expose as tools,
                            e.g. "AddNode,MessageNode".

    Outputs (data)
    --------------
    answer      : STRING  — final answer produced by the agent.
    tool_calls  : INT     — number of tool invocations performed.
    reasoning   : STRING  — chain-of-thought reasoning (if present).
    confidence  : STRING  — self-reported confidence level (if present).
    raw_output  : DICT    — full structured result dict.
    error       : STRING  — error message on failure (empty string on success).

    Control outputs
    ---------------
    done   — fires when the agent completed successfully.
    failed — fires when an exception was raised.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True  # LLM agent loop — exactly-once via DBOS step
        # ── control ──────────────────────────────────────────────────────────
        self.cin_exec       = self.add_control_input('exec')
        self.cout_done      = self.add_control_output('done')
        self.cout_failed    = self.add_control_output('failed')

        # ── data inputs ──────────────────────────────────────────────────────
        self.din_objective   = self.add_data_input('objective',    data_type=ValueType.STRING)
        self.din_context     = self.add_data_input('context_data', data_type=ValueType.DICT)
        self.din_vault       = self.add_data_input('vault',        data_type=ValueType.DICT)
        self.din_model       = self.add_data_input('model',        data_type=ValueType.STRING)
        self.din_tool_types  = self.add_data_input('tool_types',   data_type=ValueType.STRING)

        # ── data outputs ─────────────────────────────────────────────────────
        self.dout_answer     = self.add_data_output('answer',      data_type=ValueType.STRING)
        self.dout_tool_calls = self.add_data_output('tool_calls',  data_type=ValueType.INT)
        self.dout_reasoning  = self.add_data_output('reasoning',   data_type=ValueType.STRING)
        self.dout_confidence = self.add_data_output('confidence',  data_type=ValueType.STRING)
        self.dout_raw_output = self.add_data_output('raw_output',  data_type=ValueType.DICT)
        self.dout_error      = self.add_data_output('error',       data_type=ValueType.STRING)

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _import_pydantic_ai():
        try:
            from pydantic_ai import Agent  # type: ignore
            return Agent
        except ImportError as exc:
            raise ImportError(
                "pydantic-ai is required for PydanticAgentNode. "
                "Install it with: pip install pydantic-ai"
            ) from exc

    def _build_tools(self, tool_types_str: str) -> list:
        """Instantiate tool nodes by type name and wrap them as callables."""
        import uuid
        tools = []
        if not tool_types_str:
            return tools
        for type_name in (t.strip() for t in tool_types_str.split(',') if t.strip()):
            try:
                node = Node.create_node(str(uuid.uuid4()), type_name)
                tools.append(node)
            except Exception:
                pass  # unknown type — skip silently
        return tools

    # ── compute ──────────────────────────────────────────────────────────────

    async def compute(self, executionContext=None) -> ExecutionResult:
        # Read inputs
        objective   = self.din_objective.value or ''
        context_data: dict = self.din_context.value or {}
        vault: dict         = self.din_vault.value or {}
        model: str          = self.din_model.value or 'openai:gpt-4o'
        tool_types: str     = self.din_tool_types.value or ''

        try:
            Agent = self._import_pydantic_ai()
            from pydantic import BaseModel  # type: ignore

            class AgentOutput(BaseModel):
                answer: str = ''
                reasoning: str = ''
                confidence: str = ''
                tool_calls_made: int = 0

            deps = {**context_data, **vault}
            agent: Any = Agent(
                model=model,
                output_type=AgentOutput,
                system_prompt=(
                    "You are a graph-execution agent. "
                    "Complete the given objective using the available tools. "
                    "Return a structured result with answer, reasoning, and confidence."
                ),
                retries=3,
            )

            tool_nodes = self._build_tools(tool_types)
            for tool_node in tool_nodes:
                async def _tool_fn(ctx: Any, **kwargs: Any) -> Any:  # noqa: ANN401
                    # Inject kwargs as input port values then compute
                    for key, val in kwargs.items():
                        if key in tool_node.inputs:
                            tool_node.inputs[key].value = val
                    result = await tool_node.compute(executionContext)
                    # Return the first data output value
                    for port in tool_node.get_output_data_ports():
                        return port.value
                    return None
                agent.tool(_tool_fn)

            result = await agent.run(objective, deps=deps)
            output: AgentOutput = result.output

            self.dout_answer.value     = output.answer
            self.dout_tool_calls.value = output.tool_calls_made
            self.dout_reasoning.value  = output.reasoning
            self.dout_confidence.value = output.confidence
            self.dout_raw_output.value = output.model_dump()
            self.dout_error.value      = ''

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'done': True, 'failed': False})

        except Exception as exc:  # noqa: BLE001
            self.dout_error.value      = str(exc)
            self.dout_answer.value     = ''
            self.dout_tool_calls.value = 0
            self.dout_reasoning.value  = ''
            self.dout_confidence.value = ''
            self.dout_raw_output.value = {}

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'done': False, 'failed': True})


# ─────────────────────────────────────────────────────────────────────────────
# LLMCallNode
# ─────────────────────────────────────────────────────────────────────────────

@Node.register("LLMCallNode")
class LLMCallNode(Node):
    """
    A single, stateless LLM call — no tool loop, no memory.

    Useful for classification, summarisation, or any one-shot inference step
    within a larger graph flow.

    Inputs (data)
    -------------
    prompt        : STRING — the user message.
    system_prompt : STRING — optional system/persona prompt.
    model         : STRING — model identifier, e.g. "openai:gpt-4o-mini".

    Outputs (data)
    --------------
    response    : STRING — the model's reply.
    tokens_used : INT    — token count (if reported by the provider).
    error       : STRING — error message on failure (empty string on success).

    Control outputs
    ---------------
    next   — fires on success.
    failed — fires on error.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True  # LLM call — exactly-once via DBOS step
        # ── control ──────────────────────────────────────────────────────────
        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        # ── data inputs ──────────────────────────────────────────────────────
        self.din_prompt        = self.add_data_input('prompt',        data_type=ValueType.STRING)
        self.din_system_prompt = self.add_data_input('system_prompt', data_type=ValueType.STRING)
        self.din_model         = self.add_data_input('model',         data_type=ValueType.STRING)

        # ── data outputs ─────────────────────────────────────────────────────
        self.dout_response    = self.add_data_output('response',    data_type=ValueType.STRING)
        self.dout_tokens_used = self.add_data_output('tokens_used', data_type=ValueType.INT)
        self.dout_error       = self.add_data_output('error',       data_type=ValueType.STRING)

    async def compute(self, executionContext=None) -> ExecutionResult:
        prompt:        str = self.din_prompt.value or ''
        system_prompt: str = self.din_system_prompt.value or ''
        model:         str = self.din_model.value or 'openai:gpt-4o-mini'

        try:
            try:
                from pydantic_ai import Agent  # type: ignore
            except ImportError as exc:
                raise ImportError(
                    "pydantic-ai is required for LLMCallNode. "
                    "Install it with: pip install pydantic-ai"
                ) from exc

            agent: Any = Agent(
                model=model,
                output_type=str,
                system_prompt=system_prompt or "You are a helpful assistant.",
            )

            result = await agent.run(prompt)
            response: str = result.output

            # pydantic-ai exposes usage via result.usage() on some providers
            tokens: int = 0
            try:
                usage = result.usage()
                tokens = (usage.total_tokens or 0) if usage else 0
            except Exception:
                pass

            self.dout_response.value    = response
            self.dout_tokens_used.value = tokens
            self.dout_error.value       = ''

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})

        except Exception as exc:  # noqa: BLE001
            self.dout_response.value    = ''
            self.dout_tokens_used.value = 0
            self.dout_error.value       = str(exc)

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})


# ─────────────────────────────────────────────────────────────────────────────
# AgentPlannerNode
# ─────────────────────────────────────────────────────────────────────────────

@Node.register("AgentPlannerNode")
class AgentPlannerNode(Node):
    """
    Calls AgentExecutor.plan() to synthesise a NodeNetwork graph from a
    natural-language objective and write the result to output ports.

    Inputs (data)
    -------------
    objective : STRING — what the resulting graph should achieve.
    model     : STRING — LLM used for planning, e.g. "openai:gpt-4o".
    max_steps : INT    — upper bound on generated nodes (default 10).

    Outputs (data)
    --------------
    node_count     : INT    — number of nodes in the produced plan.
    edge_count     : INT    — number of edges in the produced plan.
    plan_reasoning : STRING — the planner's explanation of its choices.
    error          : STRING — error message on failure (empty on success).

    Control outputs
    ---------------
    done   — fires when a plan was produced successfully.
    failed — fires on error.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.is_durable_step = True  # Planning LLM call — exactly-once via DBOS step
        # ── control ──────────────────────────────────────────────────────────
        self.cin_exec    = self.add_control_input('exec')
        self.cout_done   = self.add_control_output('done')
        self.cout_failed = self.add_control_output('failed')

        # ── data inputs ──────────────────────────────────────────────────────
        self.din_objective = self.add_data_input('objective', data_type=ValueType.STRING)
        self.din_model     = self.add_data_input('model',     data_type=ValueType.STRING)
        self.din_max_steps = self.add_data_input('max_steps', data_type=ValueType.INT)

        # ── data outputs ─────────────────────────────────────────────────────
        self.dout_node_count     = self.add_data_output('node_count',     data_type=ValueType.INT)
        self.dout_edge_count     = self.add_data_output('edge_count',     data_type=ValueType.INT)
        self.dout_plan_reasoning = self.add_data_output('plan_reasoning', data_type=ValueType.STRING)
        self.dout_error          = self.add_data_output('error',          data_type=ValueType.STRING)

    async def compute(self, executionContext=None) -> ExecutionResult:
        objective: str = self.din_objective.value or ''
        model:     str = self.din_model.value or 'openai:gpt-4o'
        max_steps: int = int(self.din_max_steps.value or 10)

        try:
            # Deferred import to avoid circular references at module load time
            from ..core.AgentExecutor import AgentExecutor  # type: ignore

            network, reasoning = await AgentExecutor.plan(
                objective=objective,
                model=model,
                max_steps=max_steps,
            )

            node_count = len(list(network.graph.nodes.values())) if hasattr(network, 'graph') else 0
            edge_count = len(list(network.graph.edges))           if hasattr(network, 'graph') else 0

            self.dout_node_count.value     = node_count
            self.dout_edge_count.value     = edge_count
            self.dout_plan_reasoning.value = reasoning or ''
            self.dout_error.value          = ''

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'done': True, 'failed': False})

        except Exception as exc:  # noqa: BLE001
            self.dout_node_count.value     = 0
            self.dout_edge_count.value     = 0
            self.dout_plan_reasoning.value = ''
            self.dout_error.value          = str(exc)

            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'done': False, 'failed': True})
