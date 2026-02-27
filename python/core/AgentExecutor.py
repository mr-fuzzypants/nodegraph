"""
AgentExecutor — LLM-driven graph traversal built on top of Executor.

See AGENT_EXECUTOR.md for the full design document.

Architecture
------------
AgentExecutor extends Executor and overrides exactly one method:
    _process_control_outputs

Three phases run in sequence for every node that finishes executing:

    Phase 1 — Fork Check
        If more than one fired control port has wired outgoing edges, the LLM
        picks exactly one branch (ForkDecision).  On well-wired graphs the LLM
        is never called here.

    Phase 2 — Static Routing
        Delegates to the base Executor.  Follows existing edges as normal.

    Phase 3 — Dead-End Fallback
        If Phase 2 scheduled nothing (no wired successors), the LLM either
        calls another node already in the graph or terminates (TraversalDecision).

LLM Durability
--------------
The module-level functions _fork_llm_call and _traversal_llm_call are
decorated as @DBOS.step when DBOS is available, giving exactly-once semantics
for every LLM round-trip.  On a process restart inside a DBOS workflow, a
completed LLM call is not re-issued — its result is replayed from Postgres.

Observability
-------------
    agent.working_memory  — last known output value per port ({name.port: value})
    agent.trace           — append-only list of every LLM decision made

Plan Factory
------------
    AgentExecutor.plan(objective) — ask an LLM to design a full graph topology,
    returns (NodeNetwork, reasoning_text).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Literal, Optional, Tuple, TYPE_CHECKING

from pydantic import BaseModel

from .Executor import Executor, ExecutionResult
from .GraphPrimitives import Graph
from .Node import Node

if TYPE_CHECKING:
    from .NodeNetwork import NodeNetwork


# ── LLM output schemas ────────────────────────────────────────────────────────

class ForkDecision(BaseModel):
    """LLM picks one wired control port when multiple fired simultaneously."""
    chosen_port: str
    reasoning:   str


class TraversalDecision(BaseModel):
    """LLM chooses the next action when a node has no wired successors."""
    action:          Literal["call_node", "terminate"]
    node_id:         Optional[str] = None
    input_overrides: Optional[Dict[str, Any]] = None
    reasoning:       str
    is_complete:     bool


# ── Module-level step functions ───────────────────────────────────────────────
# Must be at module scope so DBOS can locate them by import path after a crash.
# Only serialisable types (str, dict) are passed as arguments.

async def _fork_llm_call(prompt: str, model: str) -> Dict[str, Any]:
    """Calls an LLM to resolve a fork decision.  Exactly-once via DBOS step."""
    from pydantic_ai import Agent  # type: ignore
    agent = Agent(model, result_type=ForkDecision)
    result = await agent.run(prompt)
    return result.data.model_dump()


async def _traversal_llm_call(prompt: str, model: str) -> Dict[str, Any]:
    """Calls an LLM to route a dead-end node.  Exactly-once via DBOS step."""
    from pydantic_ai import Agent  # type: ignore
    agent = Agent(model, result_type=TraversalDecision)
    result = await agent.run(prompt)
    return result.data.model_dump()


# Decorate as DBOS steps for exactly-once LLM execution when DBOS is available.
# Post-definition decoration (func = DBOS.step(...)(func)) is equivalent to
# @DBOS.step and works at module import time.
try:
    from dbos import DBOS as _DBOS
    _fork_llm_call       = _DBOS.step(name="agent.fork_decision")(_fork_llm_call)
    _traversal_llm_call  = _DBOS.step(name="agent.traversal_decision")(_traversal_llm_call)
except Exception:
    pass  # DBOS unavailable — calls remain plain async functions


# ── AgentExecutor ─────────────────────────────────────────────────────────────

class AgentExecutor(Executor):
    """
    Extends Executor with LLM-driven routing via _process_control_outputs.

    Parameters
    ----------
    graph      : the Graph arena to execute against
    model      : pydantic-ai model identifier, e.g. "openai:gpt-4o-mini"
    max_steps  : hard cap on total node executions before the agent terminates;
                 prevents runaway loops (default 50)
    """

    def __init__(
        self,
        graph: Graph,
        model:     str = "openai:gpt-4o-mini",
        max_steps: int = 50,
    ) -> None:
        super().__init__(graph)
        self.model     = model
        self.max_steps = max_steps
        self._step     = 0   # counts node executions via on_after_node hook

        # working_memory: last known output value per output port.
        # Key format: "{node_name}.{port_name}".
        # Passed to the LLM as recent context (last 5 entries are used in prompts).
        self.working_memory: Dict[str, Any] = {}

        # trace: append-only record of every LLM decision taken during this run.
        self.trace: List[Dict[str, Any]] = []

        # Chain pattern: AgentExecutor wires on_after_node to _capture_node_outputs.
        # If you need an additional on_after_node hook (e.g. for UI trace events),
        # set _caller_on_after_node instead of overwriting on_after_node directly.
        self._caller_on_after_node = None
        self.on_after_node = self._capture_node_outputs

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _capture_node_outputs(
        self,
        node_id:     str,
        name:        str,
        duration_ms: float,
        error:       Optional[str] = None,
    ) -> None:
        """Fires on every completed node; populates working_memory and increments step."""
        if self._caller_on_after_node:
            self._caller_on_after_node(node_id, name, duration_ms, error)
        if error:
            return
        node = self.graph.get_node_by_id(node_id)
        if node is None:
            return
        self._step += 1
        for port_name, port in node.outputs.items():
            if port.isDataPort() and port.value is not None:
                self.working_memory[f"{name}.{port_name}"] = port.value

    def _build_fork_prompt(self, node: Node, candidates: List[str]) -> str:
        memory_snippet = dict(list(self.working_memory.items())[-5:])
        return (
            f"You are routing a node graph execution.\n"
            f"Node '{node.name}' (type: {node.type}) just completed and fired "
            f"multiple wired control outputs: {candidates}.\n"
            f"Recent working memory: {memory_snippet}\n"
            f"Choose exactly one output port to follow. "
            f"chosen_port must be one of: {candidates}."
        )

    def _build_traversal_prompt(self, node: Node) -> str:
        memory_snippet = dict(list(self.working_memory.items())[-5:])
        node_summaries: List[str] = []
        for nid, n in list(self.graph.nodes.items())[:20]:
            if n is not None:
                node_summaries.append(f"  {nid}: {n.name} ({n.type})")
        nodes_str = "\n".join(node_summaries) or "  (none)"
        return (
            f"You are routing a node graph execution.\n"
            f"Node '{node.name}' (type: {node.type}) reached a dead-end "
            f"(no wired successors).\n"
            f"Recent working memory: {memory_snippet}\n"
            f"Available nodes in the graph:\n{nodes_str}\n"
            f"Decide: action='call_node' (provide node_id and optional "
            f"input_overrides) or action='terminate' (set is_complete)."
        )

    # ── Core override ─────────────────────────────────────────────────────────

    async def _process_control_outputs(
        self,
        cur_node:       Node,
        result:         ExecutionResult,
        execution_stack: List[str],
        pending_stack:   Dict[str, List[str]],
    ) -> None:
        """Three-phase LLM-augmented routing (see module docstring)."""
        if self._step >= self.max_steps:
            return

        # ── Phase 1: Fork Check ───────────────────────────────────────────────
        # Identify control ports that both fired (True) AND have wired successors.
        fired_with_edges: List[str] = [
            ctrl for ctrl, val in result.control_outputs.items()
            if val and self.graph.get_outgoing_edges(cur_node.id, ctrl)
        ]

        if len(fired_with_edges) > 1:
            prompt = self._build_fork_prompt(cur_node, fired_with_edges)
            try:
                decision  = await _fork_llm_call(prompt, self.model)
                chosen    = decision.get("chosen_port", "")
                reasoning = decision.get("reasoning", "")
                if chosen in fired_with_edges:
                    # Mutate control_outputs in-place: suppress all competing wired ports
                    # except the chosen one.  Ports with no wired successors are unaffected.
                    for port in fired_with_edges:
                        if port != chosen:
                            result.control_outputs[port] = False
                    self.trace.append({
                        "step":       self._step,
                        "type":       "fork",
                        "node":       cur_node.name,
                        "candidates": fired_with_edges,
                        "chosen":     chosen,
                        "reasoning":  reasoning,
                    })
            except Exception:
                # Fallback: follow all wired paths (silently doubles work on failure)
                pass

        # ── Phase 2: Static Routing ───────────────────────────────────────────
        stack_before = len(execution_stack)
        await super()._process_control_outputs(cur_node, result, execution_stack, pending_stack)
        scheduled_by_static = len(execution_stack) - stack_before

        # ── Phase 3: Dead-End Fallback ────────────────────────────────────────
        if scheduled_by_static == 0 and self._step < self.max_steps:
            prompt = self._build_traversal_prompt(cur_node)
            try:
                decision    = await _traversal_llm_call(prompt, self.model)
                action      = decision.get("action", "terminate")
                is_complete = bool(decision.get("is_complete", True))
                node_id     = decision.get("node_id")
                overrides   = decision.get("input_overrides") or {}
                reasoning   = decision.get("reasoning", "")

                self.trace.append({
                    "step":      self._step,
                    "type":      "traversal",
                    "node":      cur_node.name,
                    "action":    action,
                    "target":    node_id,
                    "reasoning": reasoning,
                })

                if action == "terminate" or is_complete:
                    return

                if action == "call_node" and node_id:
                    target = self.graph.get_node_by_id(node_id)
                    if target:
                        for port_name, value in overrides.items():
                            if port_name in target.inputs:
                                target.inputs[port_name].setValue(value)
                        self.build_flow_node_execution_stack(target, execution_stack, pending_stack)
            except Exception:
                pass  # Terminate silently on LLM error

    # ── Plan factory ──────────────────────────────────────────────────────────

    @classmethod
    async def plan(
        cls,
        objective: str,
        model:     str = "openai:gpt-4o",
        max_steps: int = 10,
    ) -> Tuple["NodeNetwork", str]:
        """
        Ask an LLM to design a NodeNetwork graph from scratch.

        Returns
        -------
        (network, reasoning_text)
        The returned network is fully materialised — saveable as JSON,
        loadable in the UI, and compilable by python/compiler/.
        """
        from pydantic_ai import Agent as _Agent  # type: ignore
        from .NodeNetwork import NodeNetwork

        catalogue = cls._describe_node_types()

        class _PlannedNode(BaseModel):
            type: str
            name: str

        class _PlannedEdge(BaseModel):
            from_node: str
            from_port: str
            to_node:   str
            to_port:   str

        class _GraphPlan(BaseModel):
            nodes:      List[_PlannedNode]
            edges:      List[_PlannedEdge]
            reasoning:  str
            start_node: str  # name of the node to begin execution from

        system_prompt = (
            "You design node-based computation graphs.  "
            "Given an objective, produce a GraphPlan using only the provided "
            "node types.  Use exact port names from the catalogue.  "
            "start_node must be the name of one of the nodes you define."
        )
        user_prompt = (
            f"Objective: {objective}\n\n"
            f"Available node types:\n{catalogue}\n\n"
            f"Produce a GraphPlan with at most {max_steps} nodes."
        )

        agent = _Agent(model, result_type=_GraphPlan, system_prompt=system_prompt)
        plan_result = await agent.run(user_prompt)
        plan = plan_result.data

        # Materialise the graph
        network: "NodeNetwork" = NodeNetwork.createRootNetwork("plan", "NodeNetworkSystem")
        name_to_id: Dict[str, str] = {}

        for pn in plan.nodes:
            try:
                node = network.createNode(pn.name, pn.type)
                name_to_id[pn.name] = node.id
            except Exception:
                pass  # Unknown type — skip

        for pe in plan.edges:
            from_id = name_to_id.get(pe.from_node)
            to_id   = name_to_id.get(pe.to_node)
            if from_id and to_id:
                try:
                    network.graph.add_edge(from_id, pe.from_port, to_id, pe.to_port)
                except Exception:
                    pass  # Bad port names — skip (logged as "# Skipping.")

        return network, plan.reasoning

    @classmethod
    def _describe_node_types(cls) -> str:
        """Return a human-readable catalogue of registered node types and their ports."""
        lines: List[str] = []
        for type_name, node_class in Node._node_registry.items():
            try:
                dummy = node_class(type_name, type_name, network_id="__describe__")
                in_ports  = list(dummy.inputs.keys())
                out_ports = list(dummy.outputs.keys())
                lines.append(f"  {type_name}: inputs={in_ports} outputs={out_ports}")
            except Exception:
                lines.append(f"  {type_name}: (unavailable)")
        return "\n".join(lines)
