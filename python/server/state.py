"""
GraphState — Python port of server/src/state.ts.

Builds the same demo graph on startup so the UI has something to display on
first load.  All networks share a single flat Graph object (Arena pattern).

Import this module as a side-effect to also register demo node types via
node_definitions.py.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Side-effect: registers all demo node types in Node._node_registry
import nodegraph.python.server.node_definitions  # noqa: F401

import random
from typing import Any, Dict, Optional

from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Node import Node
from nodegraph.python.core.Types import PortFunction, ValueType


class GraphState:
    """Holds the root network, all sub-networks, and UI layout positions."""

    def __init__(self) -> None:
        self.root_network: NodeNetwork = NodeNetwork.createRootNetwork(
            "root", "NodeNetworkSystem"
        )
        # Flat index of every NodeNetwork instance keyed by UUID
        self.all_networks: Dict[str, NodeNetwork] = {
            self.root_network.id: self.root_network
        }
        # UI layout positions: node_id → {x, y}
        self.positions: Dict[str, Dict[str, float]] = {}

        # Live executor instances keyed by run_id.
        # Populated by the /execute endpoint; cleaned up in its finally block.
        # Allows the /executions/{run_id}/waiting endpoint to introspect state.
        self.active_executors: Dict[str, Any] = {}

        self._seed_demo()

    # ── Demo graph ──────────────────────────────────────────────────────────

    def _seed_demo(self) -> None:
        net = self.root_network
        graph = net.graph  # shared across all networks

        # ── Root-level nodes ─────────────────────────────────────────────────
        a = net.createNode("ConstA", "ConstantNode")
        b = net.createNode("ConstB", "ConstantNode")
        add = net.createNode("Add", "AddNode")
        print_node = net.createNode("Print", "PrintNode")

        a.outputs["out"].value = 8
        b.outputs["out"].value = 4
        add.inputs["a"].value = 8
        add.inputs["b"].value = 4
        add.outputs["sum"].value = 12
        print_node.inputs["value"].value = 12

        # Use graph.add_edge directly — connectNodesByPath hits a pre-existing bug in
        # can_connnect_output that uses `from_port` before it is defined.
        graph.add_edge(a.id, "out", add.id, "a")
        graph.add_edge(b.id, "out", add.id, "b")
        graph.add_edge(add.id, "sum", print_node.id, "value")

        self.positions[a.id] = {"x": 80, "y": 100}
        self.positions[b.id] = {"x": 80, "y": 260}
        self.positions[add.id] = {"x": 340, "y": 180}
        self.positions[print_node.id] = {"x": 580, "y": 180}

        # ── ScaleNet ─────────────────────────────────────────────────────────
        scale_net = net.createNetwork("ScaleNet", "NodeNetworkSystem")
        self.all_networks[scale_net.id] = scale_net

        scale_net.add_data_input_port("value")
        scale_net.inputs["value"].value = 12

        two = scale_net.createNode("Two", "ConstantNode")
        mul = scale_net.createNode("Double", "MultiplyNode")
        result = scale_net.createNode("Result", "PrintNode")

        two.outputs["out"].value = 2
        mul.inputs["a"].value = 12
        mul.inputs["b"].value = 2
        mul.outputs["product"].value = 24
        result.inputs["value"].value = 24

        # Internal wiring — use graph.add_edge with node ids (same shared graph)
        graph.add_edge(scale_net.id, "value", mul.id, "a")
        graph.add_edge(two.id, "out", mul.id, "b")
        graph.add_edge(mul.id, "product", result.id, "value")

        # Wire root Add → ScaleNet tunnel
        graph.add_edge(add.id, "sum", scale_net.id, "value")

        self.positions[scale_net.id] = {"x": 820, "y": 180}
        self.positions[two.id] = {"x": 80, "y": 80}
        self.positions[mul.id] = {"x": 340, "y": 180}
        self.positions[result.id] = {"x": 600, "y": 180}

        # ── LoopDemo ──────────────────────────────────────────────────────────
        loop_net = net.createNetwork("LoopDemo", "NodeNetworkSystem")
        self.all_networks[loop_net.id] = loop_net

        loop_node = loop_net.createNode("Loop", "ForLoopNode")
        accum_node = loop_net.createNode("Accumulator", "AccumulatorNode")

        loop_node.inputs["start"].value = 0
        loop_node.inputs["end"].value = 5
        loop_node.outputs["index"].value = 0

        graph.add_edge(loop_node.id, "loop_body", accum_node.id, "exec")
        graph.add_edge(loop_node.id, "index", accum_node.id, "val")

        self.positions[loop_net.id] = {"x": 1080, "y": 180}
        self.positions[loop_node.id] = {"x": 80, "y": 180}
        self.positions[accum_node.id] = {"x": 420, "y": 180}

        # ── pydantic-ai demos ──────────────────────────────────────────────────
        self._seed_pydantic_ai_demo(net, graph)

        # ── DotDemo ───────────────────────────────────────────────────────────
        dot_net = net.createNetwork("DotDemo", "NodeNetworkSystem")
        self.all_networks[dot_net.id] = dot_net

        vec_a = dot_net.createNode("VecA", "VectorNode")
        vec_b = dot_net.createNode("VecB", "VectorNode")
        dot = dot_net.createNode("Dot", "DotProductNode")

        vec_a.inputs["x"].value = 1
        vec_a.inputs["y"].value = 2
        vec_a.inputs["z"].value = 3
        vec_a.outputs["vec"].value = [1, 2, 3]

        vec_b.inputs["x"].value = 4
        vec_b.inputs["y"].value = 5
        vec_b.inputs["z"].value = 6
        vec_b.outputs["vec"].value = [4, 5, 6]

        dot.inputs["vec_a"].value = [1, 2, 3]
        dot.inputs["vec_b"].value = [4, 5, 6]
        dot.outputs["result"].value = 32.0

        graph.add_edge(vec_a.id, "vec", dot.id, "vec_a")
        graph.add_edge(vec_b.id, "vec", dot.id, "vec_b")

        self.positions[dot_net.id] = {"x": 1380, "y": 180}
        self.positions[vec_a.id] = {"x": 80, "y": 100}
        self.positions[vec_b.id] = {"x": 80, "y": 300}
        self.positions[dot.id] = {"x": 400, "y": 200}

        # ── ParallelLoopDemo ──────────────────────────────────────────────────
        parallel_net = net.createNetwork("ParallelLoopDemo", "NodeNetworkSystem")
        self.all_networks[parallel_net.id] = parallel_net

        p_loop = parallel_net.createNode("Loop", "ForLoopNode")
        counter_a = parallel_net.createNode("CounterA", "AccumulatorNode")
        counter_b = parallel_net.createNode("CounterB", "AccumulatorNode")

        p_loop.inputs["start"].value = 0
        p_loop.inputs["end"].value = 3
        p_loop.outputs["index"].value = 0

        graph.add_edge(p_loop.id, "loop_body", counter_a.id, "exec")
        graph.add_edge(p_loop.id, "loop_body", counter_b.id, "exec")
        graph.add_edge(p_loop.id, "index", counter_a.id, "val")
        graph.add_edge(p_loop.id, "index", counter_b.id, "val")

        self.positions[parallel_net.id] = {"x": 1680, "y": 180}
        self.positions[p_loop.id] = {"x": 80, "y": 180}
        self.positions[counter_a.id] = {"x": 420, "y": 80}
        self.positions[counter_b.id] = {"x": 420, "y": 300}

        # ── NestedLoopDemo ────────────────────────────────────────────────────
        nested_net = net.createNetwork("NestedLoopDemo", "NodeNetworkSystem")
        self.all_networks[nested_net.id] = nested_net

        outer_loop = nested_net.createNode("OuterLoop", "ForLoopNode")
        inner_loop = nested_net.createNode("InnerLoop", "ForLoopNode")
        n_counter = nested_net.createNode("Counter", "AccumulatorNode")

        outer_loop.inputs["start"].value = 0
        outer_loop.inputs["end"].value = 3
        outer_loop.outputs["index"].value = 0

        inner_loop.inputs["start"].value = 0
        inner_loop.inputs["end"].value = 2
        inner_loop.outputs["index"].value = 0

        graph.add_edge(outer_loop.id, "loop_body", inner_loop.id, "exec")
        graph.add_edge(inner_loop.id, "loop_body", n_counter.id, "exec")
        graph.add_edge(inner_loop.id, "index", n_counter.id, "val")

        self.positions[nested_net.id] = {"x": 1980, "y": 180}
        self.positions[outer_loop.id] = {"x": 80, "y": 180}
        self.positions[inner_loop.id] = {"x": 420, "y": 180}
        self.positions[n_counter.id] = {"x": 760, "y": 180}

        # ── ParallelNestedLoopDemo ────────────────────────────────────────────
        pn_net = net.createNetwork("ParallelNestedLoopDemo", "NodeNetworkSystem")
        self.all_networks[pn_net.id] = pn_net

        pn_print = pn_net.createNode("Print", "PrintNode")
        pn_outer_a = pn_net.createNode("OuterA", "ForLoopNode")
        pn_inner_a = pn_net.createNode("InnerA", "ForLoopNode")
        pn_accum_a = pn_net.createNode("AccumA", "AccumulatorNode")
        pn_outer_b = pn_net.createNode("OuterB", "ForLoopNode")
        pn_inner_b = pn_net.createNode("InnerB", "ForLoopNode")
        pn_accum_b = pn_net.createNode("AccumB", "AccumulatorNode")

        pn_print.inputs["value"].value = "start"
        pn_outer_a.inputs["start"].value = 0
        pn_outer_a.inputs["end"].value = 2
        pn_inner_a.inputs["start"].value = 0
        pn_inner_a.inputs["end"].value = 3
        pn_outer_b.inputs["start"].value = 0
        pn_outer_b.inputs["end"].value = 3
        pn_inner_b.inputs["start"].value = 0
        pn_inner_b.inputs["end"].value = 2

        graph.add_edge(pn_print.id, "next", pn_outer_a.id, "exec")
        graph.add_edge(pn_print.id, "next", pn_outer_b.id, "exec")
        graph.add_edge(pn_outer_a.id, "loop_body", pn_inner_a.id, "exec")
        graph.add_edge(pn_inner_a.id, "loop_body", pn_accum_a.id, "exec")
        graph.add_edge(pn_inner_a.id, "index", pn_accum_a.id, "val")
        graph.add_edge(pn_outer_b.id, "loop_body", pn_inner_b.id, "exec")
        graph.add_edge(pn_inner_b.id, "loop_body", pn_accum_b.id, "exec")
        graph.add_edge(pn_inner_b.id, "index", pn_accum_b.id, "val")

        self.positions[pn_net.id] = {"x": 2280, "y": 180}
        self.positions[pn_print.id] = {"x": 80, "y": 280}
        self.positions[pn_outer_a.id] = {"x": 360, "y": 100}
        self.positions[pn_inner_a.id] = {"x": 680, "y": 100}
        self.positions[pn_accum_a.id] = {"x": 1000, "y": 100}
        self.positions[pn_outer_b.id] = {"x": 360, "y": 460}
        self.positions[pn_inner_b.id] = {"x": 680, "y": 460}
        self.positions[pn_accum_b.id] = {"x": 1000, "y": 460}

        # ── ForEachDemo ───────────────────────────────────────────────────────
        # Iterates a list of fruit names; prints each item inside the loop,
        # then prints a summary when the list is exhausted.
        #
        #  Items (ConstantNode, ["apple","banana","cherry"])
        #    |
        #    | items
        #    ▼
        #  ForEach (ForEachNode)
        #    |  loop_body ──► ItemPrinter (PrintNode)  ← item
        #    |  completed ──► Done (PrintNode)          ← total
        #
        fe_net = net.createNetwork("ForEachDemo", "NodeNetworkSystem")
        self.all_networks[fe_net.id] = fe_net

        fe_items   = fe_net.createNode("Items",       "ConstantNode")
        fe_node    = fe_net.createNode("ForEach",     "ForEachNode")
        fe_printer = fe_net.createNode("ItemPrinter", "PrintNode")
        fe_done    = fe_net.createNode("Done",        "PrintNode")

        fe_items.outputs["out"].value  = ["apple", "banana", "cherry"]
        fe_node.inputs["items"].value  = ["apple", "banana", "cherry"]
        fe_node.outputs["item"].value  = "apple"
        fe_node.outputs["index"].value = 0
        fe_node.outputs["total"].value = 3
        fe_printer.inputs["value"].value = "apple"
        fe_done.inputs["value"].value    = 3

        graph.add_edge(fe_items.id, "out",       fe_node.id,    "items")
        graph.add_edge(fe_node.id,  "loop_body", fe_printer.id, "exec")
        graph.add_edge(fe_node.id,  "item",      fe_printer.id, "value")
        graph.add_edge(fe_node.id,  "completed", fe_done.id,    "exec")
        graph.add_edge(fe_node.id,  "total",     fe_done.id,    "value")

        self.positions[fe_net.id]      = {"x": 2580, "y": 180}
        self.positions[fe_items.id]    = {"x": 80,  "y": 180}
        self.positions[fe_node.id]     = {"x": 360, "y": 180}
        self.positions[fe_printer.id]  = {"x": 660, "y": 80}
        self.positions[fe_done.id]     = {"x": 660, "y": 300}

        # ── Agent node demos ──────────────────────────────────────────────────
        self._seed_agent_demos(net, graph)
        self._seed_sampler_demos(net, graph)

    # ── pydantic-ai demo seed ──────────────────────────────────────────────────

    def _seed_pydantic_ai_demo(self, net, graph) -> None:
        """Demonstration subnetworks for pydantic-ai powered nodes."""
        # ── LLMPipeline: PromptTemplateNode → LLMNode → PrintNode ─────────────
        llm_net = net.createNetwork("LLMPipeline", "NodeNetworkSystem")
        self.all_networks[llm_net.id] = llm_net

        tmpl_node = llm_net.createNode("Template", "PromptTemplateNode")
        llm_node  = llm_net.createNode("LLM",      "LLMNode")
        print_llm = llm_net.createNode("Output",   "PrintNode")

        tmpl_node.inputs["template"].value  = (
            "You are a concise assistant. Answer in one sentence: {question}"
        )
        tmpl_node.inputs["variables"].value = {"question": "What is a node graph?"}
        llm_node.inputs["model"].value       = "openai:gpt-4o-mini"
        llm_node.inputs["temperature"].value = 0.3

        graph.add_edge(tmpl_node.id, "prompt",   llm_node.id,  "prompt")
        graph.add_edge(llm_node.id,  "response", print_llm.id, "value")

        self.positions[llm_net.id]    = {"x": 2880, "y": 180}
        self.positions[tmpl_node.id]  = {"x": 80,  "y": 180}
        self.positions[llm_node.id]   = {"x": 420, "y": 180}
        self.positions[print_llm.id]  = {"x": 760, "y": 180}

        # ── AgentDemo: ConstantNode (task) → ToolAgentNode → PrintNode ─────────
        agent_net  = net.createNetwork("AgentDemo", "NodeNetworkSystem")
        self.all_networks[agent_net.id] = agent_net

        task_node  = agent_net.createNode("Task",   "ConstantNode")
        agent_node = agent_net.createNode("Agent",  "ToolAgentNode")
        print_agent= agent_net.createNode("Output", "PrintNode")

        task_node.outputs["out"].value      = "What is 123 * 456? Then count the words in the answer."
        agent_node.inputs["tools"].value    = ["calculator", "word_count"]
        agent_node.inputs["model"].value    = "openai:gpt-4o-mini"

        graph.add_edge(task_node.id,  "out",    agent_node.id, "task")
        graph.add_edge(agent_node.id, "result", print_agent.id,"value")

        self.positions[agent_net.id]    = {"x": 3180, "y": 180}
        self.positions[task_node.id]    = {"x": 80,  "y": 180}
        self.positions[agent_node.id]   = {"x": 420, "y": 180}
        self.positions[print_agent.id]  = {"x": 760, "y": 180}

        # ── EmbedSimilarity: two EmbeddingNodes → DotProductNode ──────────────
        embed_net = net.createNetwork("EmbedSimilarity", "NodeNetworkSystem")
        self.all_networks[embed_net.id] = embed_net

        text_a  = embed_net.createNode("TextA",      "ConstantNode")
        text_b  = embed_net.createNode("TextB",      "ConstantNode")
        embed_a = embed_net.createNode("EmbedA",     "EmbeddingNode")
        embed_b = embed_net.createNode("EmbedB",     "EmbeddingNode")
        dot     = embed_net.createNode("Dot",        "DotProductNode")
        sim_out = embed_net.createNode("Similarity", "PrintNode")

        text_a.outputs["out"].value = "The cat sat on the mat."
        text_b.outputs["out"].value = "A feline rested on a rug."

        graph.add_edge(text_a.id,  "out",       embed_a.id, "text")
        graph.add_edge(text_b.id,  "out",       embed_b.id, "text")
        graph.add_edge(embed_a.id, "embedding", dot.id,     "vec_a")
        graph.add_edge(embed_b.id, "embedding", dot.id,     "vec_b")
        graph.add_edge(dot.id,     "result",    sim_out.id, "value")

        self.positions[embed_net.id] = {"x": 3480, "y": 180}
        self.positions[text_a.id]    = {"x": 80,  "y": 80}
        self.positions[text_b.id]    = {"x": 80,  "y": 280}
        self.positions[embed_a.id]   = {"x": 360, "y": 80}
        self.positions[embed_b.id]   = {"x": 360, "y": 280}
        self.positions[dot.id]       = {"x": 680, "y": 180}
        self.positions[sim_out.id]   = {"x": 960, "y": 180}

        # ── StreamingDemo: PromptTemplateNode → LLMStreamNode → PrintNode ─────
        # Like LLMPipeline but uses LLMStreamNode so every token fires a
        # STREAM_CHUNK trace event — visible as a live-updating buffer in the
        # Trace / ParameterPane overlay.
        stream_net = net.createNetwork("StreamingDemo", "NodeNetworkSystem")
        self.all_networks[stream_net.id] = stream_net

        s_tmpl   = stream_net.createNode("Template",  "PromptTemplateNode")
        s_stream = stream_net.createNode("Stream",     "LLMStreamNode")
        s_print  = stream_net.createNode("Output",     "PrintNode")

        s_tmpl.inputs["template"].value  = (
            "You are a concise technical writer. "
            "Answer in 2-3 sentences: {question}"
        )
        s_tmpl.inputs["variables"].value = {
            "question": "How does streaming differ from blocking LLM calls?"
        }
        s_stream.inputs["model"].value         = "openai:gpt-4o-mini"
        s_stream.inputs["system_prompt"].value = "You are a helpful assistant."

        graph.add_edge(s_tmpl.id,   "prompt",   s_stream.id, "prompt")
        graph.add_edge(s_stream.id, "response", s_print.id,  "value")

        self.positions[stream_net.id] = {"x": 3780, "y": 180}
        self.positions[s_tmpl.id]     = {"x": 80,  "y": 180}
        self.positions[s_stream.id]   = {"x": 420, "y": 180}
        self.positions[s_print.id]    = {"x": 760, "y": 180}

        # ── MultiStepAgent: multi-step calculator chain ────────────────────────
        # Multi-step calculator chain:
        #   ConstantNode (task) → ToolAgentNode (calculator only) → PrintNode
        # The agent decomposes the expression into sequential tool calls,
        # firing an AGENT_STEP trace event for each calculator invocation.
        ms_net = net.createNetwork("MultiStepAgent", "NodeNetworkSystem")
        self.all_networks[ms_net.id] = ms_net

        ms_task  = ms_net.createNode("Task",   "ConstantNode")
        ms_agent = ms_net.createNode("Agent",  "ToolAgentNode")
        ms_print = ms_net.createNode("Output", "PrintNode")

        ms_task.outputs["out"].value     = (
            "Calculate (17 * 23) + (88 / 4). "
            "Then take that result and multiply it by 3."
        )
        ms_agent.inputs["tools"].value   = ["calculator"]
        ms_agent.inputs["model"].value   = "openai:gpt-4o-mini"

        graph.add_edge(ms_task.id,  "out",    ms_agent.id, "task")
        graph.add_edge(ms_agent.id, "result", ms_print.id, "value")

        self.positions[ms_net.id]   = {"x": 4080, "y": 180}
        self.positions[ms_task.id]  = {"x": 80,  "y": 180}
        self.positions[ms_agent.id] = {"x": 420, "y": 180}
        self.positions[ms_print.id] = {"x": 760, "y": 180}

        # ── AgentStreamDemo ────────────────────────────────────────────────────
        # Streaming version of AgentDemo (maths + word count).
        # ToolAgentStreamNode fires loop_body → StepPrinterNode for every
        # tool_call / tool_result step, then completed → PrintNode (final answer).
        asd_net   = net.createNetwork("AgentStreamDemo", "NodeNetworkSystem")
        self.all_networks[asd_net.id] = asd_net

        asd_task   = asd_net.createNode("Task",        "ConstantNode")
        asd_agent  = asd_net.createNode("Agent",       "ToolAgentStreamNode")
        asd_step   = asd_net.createNode("StepPrinter", "StepPrinterNode")
        asd_print  = asd_net.createNode("Output",      "PrintNode")

        asd_task.outputs["out"].value    = "What is 123 * 456? Then count the words in the answer."
        asd_agent.inputs["tools"].value  = ["calculator", "word_count"]
        asd_agent.inputs["model"].value  = "openai:gpt-4o-mini"

        graph.add_edge(asd_task.id,  "out",          asd_agent.id, "task")
        graph.add_edge(asd_agent.id, "loop_body",    asd_step.id,  "exec")
        graph.add_edge(asd_agent.id, "step_type",    asd_step.id,  "step_type")
        graph.add_edge(asd_agent.id, "step_content", asd_step.id,  "step_content")
        graph.add_edge(asd_agent.id, "tool_name",    asd_step.id,  "tool_name")
        graph.add_edge(asd_agent.id, "completed",    asd_print.id, "exec")
        graph.add_edge(asd_agent.id, "result",       asd_print.id, "value")

        self.positions[asd_net.id]   = {"x": 4380, "y": 180}
        self.positions[asd_task.id]  = {"x": 80,  "y": 180}
        self.positions[asd_agent.id] = {"x": 420, "y": 180}
        self.positions[asd_step.id]  = {"x": 760, "y": 80}
        self.positions[asd_print.id] = {"x": 760, "y": 280}

        # ── MultiStepAgentStream ───────────────────────────────────────────────
        # Streaming version of MultiStepAgent (4-step calculator chain).
        mss_net   = net.createNetwork("MultiStepAgentStream", "NodeNetworkSystem")
        self.all_networks[mss_net.id] = mss_net

        mss_task   = mss_net.createNode("Task",        "ConstantNode")
        mss_agent  = mss_net.createNode("Agent",       "ToolAgentStreamNode")
        mss_step   = mss_net.createNode("StepPrinter", "StepPrinterNode")
        mss_print  = mss_net.createNode("Output",      "PrintNode")

        mss_task.outputs["out"].value   = (
            "Calculate (17 * 23) + (88 / 4). "
            "Then take that result and multiply it by 3."
        )
        mss_agent.inputs["tools"].value = ["calculator"]
        mss_agent.inputs["model"].value = "openai:gpt-4o-mini"

        graph.add_edge(mss_task.id,  "out",          mss_agent.id, "task")
        graph.add_edge(mss_agent.id, "loop_body",    mss_step.id,  "exec")
        graph.add_edge(mss_agent.id, "step_type",    mss_step.id,  "step_type")
        graph.add_edge(mss_agent.id, "step_content", mss_step.id,  "step_content")
        graph.add_edge(mss_agent.id, "tool_name",    mss_step.id,  "tool_name")
        graph.add_edge(mss_agent.id, "completed",    mss_print.id, "exec")
        graph.add_edge(mss_agent.id, "result",       mss_print.id, "value")

        self.positions[mss_net.id]   = {"x": 4680, "y": 180}
        self.positions[mss_task.id]  = {"x": 80,  "y": 180}
        self.positions[mss_agent.id] = {"x": 420, "y": 180}
        self.positions[mss_step.id]  = {"x": 760, "y": 80}
        self.positions[mss_print.id] = {"x": 760, "y": 280}

        # ── ImageGenDemo: ConstantNode (prompt) → ImageGenNode → PrintNode ───
        img_net  = net.createNetwork("ImageGenDemo", "NodeNetworkSystem")
        self.all_networks[img_net.id] = img_net

        img_prompt  = img_net.createNode("Prompt",   "ConstantNode")
        img_gen     = img_net.createNode("ImageGen",  "ImageGenNode")
        img_url     = img_net.createNode("URL",       "PrintNode")
        img_revised = img_net.createNode("Revised",   "PrintNode")

        img_prompt.outputs["out"].value = "A red fox in a snow-covered forest, digital art"
        img_gen.inputs["model"].value   = "dall-e-3"
        img_gen.inputs["size"].value    = "1024x1024"

        graph.add_edge(img_prompt.id, "out",            img_gen.id,     "prompt")
        graph.add_edge(img_gen.id,    "url",            img_url.id,     "value")
        graph.add_edge(img_gen.id,    "revised_prompt", img_revised.id, "value")

        self.positions[img_net.id]      = {"x": 4980, "y": 180}
        self.positions[img_prompt.id]   = {"x": 80,   "y": 180}
        self.positions[img_gen.id]      = {"x": 420,  "y": 180}
        self.positions[img_url.id]      = {"x": 760,  "y": 100}
        self.positions[img_revised.id]  = {"x": 760,  "y": 280}

        # ── PromptRefinementLoop ───────────────────────────────────────────────
        # Feeds revised_prompt from Gen1 back into Gen2 as its prompt, so
        # DALL-E's own richer rewrite becomes the seed for the second image.
        # The second generation is typically more detailed and consistent.
        #
        #  Prompt (ConstantNode)
        #    |
        #    ▼
        #  Gen1 (ImageGenNode)
        #    |  url         ──► Image1 (PrintNode)
        #    |  revised_prompt ──► Gen2 (ImageGenNode)
        #                              |  url         ──► Image2 (PrintNode)
        #                              |  revised_prompt ──► Refined (PrintNode)
        #
        prl_net = net.createNetwork("PromptRefinementLoop", "NodeNetworkSystem")
        self.all_networks[prl_net.id] = prl_net

        prl_prompt  = prl_net.createNode("Prompt",  "ConstantNode")
        prl_gen1    = prl_net.createNode("Gen1",    "ImageGenNode")
        prl_img1    = prl_net.createNode("Image1",  "PrintNode")
        prl_gen2    = prl_net.createNode("Gen2",    "ImageGenNode")
        prl_img2    = prl_net.createNode("Image2",  "PrintNode")
        prl_refined = prl_net.createNode("Refined", "PrintNode")

        prl_prompt.outputs["out"].value = "A serene mountain lake at dawn, impressionist oil painting"
        prl_gen1.inputs["model"].value  = "dall-e-3"
        prl_gen1.inputs["size"].value   = "1024x1024"
        prl_gen2.inputs["model"].value  = "dall-e-3"
        prl_gen2.inputs["size"].value   = "1024x1024"

        graph.add_edge(prl_prompt.id, "out",            prl_gen1.id,    "prompt")
        graph.add_edge(prl_gen1.id,   "url",            prl_img1.id,    "value")
        graph.add_edge(prl_gen1.id,   "revised_prompt", prl_gen2.id,    "prompt")
        graph.add_edge(prl_gen2.id,   "url",            prl_img2.id,    "value")
        graph.add_edge(prl_gen2.id,   "revised_prompt", prl_refined.id, "value")

        self.positions[prl_net.id]     = {"x": 5280, "y": 180}
        self.positions[prl_prompt.id]  = {"x": 80,   "y": 180}
        self.positions[prl_gen1.id]    = {"x": 380,  "y": 180}
        self.positions[prl_img1.id]    = {"x": 720,  "y": 80}
        self.positions[prl_gen2.id]    = {"x": 720,  "y": 300}
        self.positions[prl_img2.id]    = {"x": 1060, "y": 180}
        self.positions[prl_refined.id] = {"x": 1060, "y": 400}

        # ── PromptCritiqueLoop ────────────────────────────────────────────────────
        # Full critique-and-refine cycle:
        #
        #  Prompt (ConstantNode)
        #    ↓
        #  Gen1 (ImageGenNode)
        #    ├── url            ──► FirstImage (PrintNode)
        #    ├── url            ──► Vision (GPT4VisionNode)
        #    └── revised_prompt ──► Refiner.original_prompt
        #
        #  Vision
        #    ├── critique ──► CritiqueOut (PrintNode)
        #    └── critique ──► Refiner.critique
        #
        #  Refiner (PromptRefinerNode)
        #    └── refined_prompt ──► Gen2 (ImageGenNode)
        #
        #  Gen2
        #    ├── url            ──► FinalImage (PrintNode)
        #    └── revised_prompt ──► FinalRevised (PrintNode)
        #
        pcl_net = net.createNetwork("PromptCritiqueLoop", "NodeNetworkSystem")
        self.all_networks[pcl_net.id] = pcl_net

        pcl_prompt      = pcl_net.createNode("Prompt",      "ConstantNode")
        pcl_gen1        = pcl_net.createNode("Gen1",         "ImageGenNode")
        pcl_first_img   = pcl_net.createNode("FirstImage",   "PrintNode")
        pcl_vision      = pcl_net.createNode("Vision",       "GPT4VisionNode")
        pcl_critique    = pcl_net.createNode("CritiqueOut",  "PrintNode")
        pcl_refiner     = pcl_net.createNode("Refiner",      "PromptRefinerNode")
        pcl_gen2        = pcl_net.createNode("Gen2",         "ImageGenNode")
        pcl_final_img   = pcl_net.createNode("FinalImage",   "PrintNode")
        pcl_final_rev   = pcl_net.createNode("FinalRevised", "PrintNode")

        pcl_prompt.outputs["out"].value      = "A serene mountain lake at dawn, impressionist oil painting"
        pcl_gen1.inputs["model"].value       = "dall-e-3"
        pcl_gen1.inputs["size"].value        = "1024x1024"
        pcl_vision.inputs["question"].value  = (
            "Critique this image in detail. What elements are missing, "
            "incorrect, or could be improved? Be specific and constructive."
        )
        pcl_gen2.inputs["model"].value       = "dall-e-3"
        pcl_gen2.inputs["size"].value        = "1024x1024"

        graph.add_edge(pcl_prompt.id,   "out",            pcl_gen1.id,      "prompt")
        graph.add_edge(pcl_gen1.id,     "url",            pcl_first_img.id, "value")
        graph.add_edge(pcl_gen1.id,     "url",            pcl_vision.id,    "url")
        graph.add_edge(pcl_gen1.id,     "revised_prompt", pcl_refiner.id,   "original_prompt")
        graph.add_edge(pcl_vision.id,   "critique",       pcl_critique.id,  "value")
        graph.add_edge(pcl_vision.id,   "critique",       pcl_refiner.id,   "critique")
        graph.add_edge(pcl_refiner.id,  "refined_prompt", pcl_gen2.id,      "prompt")
        graph.add_edge(pcl_gen2.id,     "url",            pcl_final_img.id, "value")
        graph.add_edge(pcl_gen2.id,     "revised_prompt", pcl_final_rev.id, "value")

        self.positions[pcl_net.id]        = {"x": 5580, "y": 180}
        self.positions[pcl_prompt.id]     = {"x": 80,   "y": 280}
        self.positions[pcl_gen1.id]       = {"x": 420,  "y": 280}
        self.positions[pcl_first_img.id]  = {"x": 780,  "y": 80}
        self.positions[pcl_vision.id]     = {"x": 780,  "y": 300}
        self.positions[pcl_critique.id]   = {"x": 780,  "y": 520}
        self.positions[pcl_refiner.id]    = {"x": 1140, "y": 300}
        self.positions[pcl_gen2.id]       = {"x": 1500, "y": 300}
        self.positions[pcl_final_img.id]  = {"x": 1860, "y": 180}
        self.positions[pcl_final_rev.id]  = {"x": 1860, "y": 420}

        # ── PrivacyPipelineDemo ────────────────────────────────────────────────
        # Demonstrates AnonymizerNode (Presidio) chained into SummarizerNode.
        #
        # Raw text with real PII
        #   ↓ out → text
        # AnonymizerNode  (operator="replace")
        #   ├── anonymized   ──► SummarizerNode ──► SummaryOut (PrintNode)
        #   ├── entities     ──► EntitiesOut    (PrintNode)
        #   └── entity_count ──► CountOut       (PrintNode)
        #
        # The LLM in SummarizerNode only ever sees anonymized text —
        # PII is stripped by Presidio before any data leaves the machine.
        priv_net = net.createNetwork("PrivacyPipelineDemo", "NodeNetworkSystem")
        self.all_networks[priv_net.id] = priv_net

        priv_raw     = priv_net.createNode("RawText",    "ConstantNode")
        priv_anon    = priv_net.createNode("Anonymizer", "AnonymizerNode")
        priv_summ    = priv_net.createNode("Summarizer", "SummarizerNode")
        priv_summary = priv_net.createNode("SummaryOut", "PrintNode")
        priv_ents    = priv_net.createNode("EntitiesOut","PrintNode")
        priv_count   = priv_net.createNode("CountOut",   "PrintNode")

        priv_raw.outputs["out"].value = (
            "Meeting notes — 2024-03-15\n"
            "Attendees: Dr. Sarah Mitchell (sarah.mitchell@acme.com, +1-555-0192) "
            "and John Brennan (john.brennan@acme.com).\n"
            "John's employee ID is EMP-4829 and his SSN is 123-45-6789.\n"
            "The team discussed the Q1 roadmap for the Phoenix project. "
            "Budget approved: $2.4M. Launch target: June 30, 2024.\n"
            "Action items: Sarah to review the security audit by March 22. "
            "John to contact vendor at vendor-support@supplierco.io.\n"
            "Next meeting: April 5 at 14:00 UTC, Room B4, 221 West 57th St, New York."
        )
        priv_anon.inputs["operator"].value  = "replace"
        priv_anon.inputs["language"].value  = "en"
        priv_summ.inputs["style"].value     = "bullet"
        priv_summ.inputs["max_length"].value = 80
        priv_summ.inputs["model"].value     = "openai:gpt-4o-mini"

        graph.add_edge(priv_raw.id,  "out",          priv_anon.id,    "text")
        graph.add_edge(priv_anon.id, "anonymized",   priv_summ.id,    "text")
        graph.add_edge(priv_summ.id, "summary",      priv_summary.id, "value")
        graph.add_edge(priv_anon.id, "entities",     priv_ents.id,    "value")
        graph.add_edge(priv_anon.id, "entity_count", priv_count.id,   "value")

        self.positions[priv_net.id]     = {"x": 5880, "y": 180}
        self.positions[priv_raw.id]     = {"x": 80,   "y": 280}
        self.positions[priv_anon.id]    = {"x": 440,  "y": 280}
        self.positions[priv_summ.id]    = {"x": 820,  "y": 180}
        self.positions[priv_summary.id] = {"x": 1180, "y": 180}
        self.positions[priv_ents.id]    = {"x": 820,  "y": 400}
        self.positions[priv_count.id]   = {"x": 820,  "y": 560}

    # ── Agent demo seed ───────────────────────────────────────────────────────

    def _seed_agent_demos(self, net, graph) -> None:
        """Three demonstration subnetworks for the pydantic-ai powered agent nodes."""

        # ── LLMCallDemo ───────────────────────────────────────────────────────
        # Single stateless LLM call: prompt in → response out.
        #
        #  Prompt (ConstantNode)
        #    ↓ out → prompt
        #  LLMCall (LLMCallNode)
        #    ├── next   ──► Response (PrintNode) ← response
        #    └── failed ──► Error    (PrintNode) ← error
        #
        llmc_net = net.createNetwork("LLMCallDemo", "NodeNetworkSystem")
        self.all_networks[llmc_net.id] = llmc_net

        llmc_prompt  = llmc_net.createNode("Prompt",   "ConstantNode")
        llmc_system  = llmc_net.createNode("System",   "ConstantNode")
        llmc_node    = llmc_net.createNode("LLMCall",  "LLMCallNode")
        llmc_resp    = llmc_net.createNode("Response", "PrintNode")
        llmc_err     = llmc_net.createNode("Error",    "PrintNode")

        llmc_prompt.outputs["out"].value  = "What is a node graph? Answer in one sentence."
        llmc_system.outputs["out"].value  = "You are a concise technical writer."
        llmc_node.inputs["model"].value   = "openai:gpt-4o-mini"

        graph.add_edge(llmc_prompt.id, "out",      llmc_node.id, "prompt")
        graph.add_edge(llmc_system.id, "out",      llmc_node.id, "system_prompt")
        graph.add_edge(llmc_node.id,   "next",     llmc_resp.id, "exec")
        graph.add_edge(llmc_node.id,   "response", llmc_resp.id, "value")
        graph.add_edge(llmc_node.id,   "failed",   llmc_err.id,  "exec")
        graph.add_edge(llmc_node.id,   "error",    llmc_err.id,  "value")

        self.positions[llmc_net.id]    = {"x": 6180, "y": 180}
        self.positions[llmc_prompt.id] = {"x": 80,  "y": 100}
        self.positions[llmc_system.id] = {"x": 80,  "y": 300}
        self.positions[llmc_node.id]   = {"x": 400, "y": 180}
        self.positions[llmc_resp.id]   = {"x": 760, "y": 80}
        self.positions[llmc_err.id]    = {"x": 760, "y": 300}

        # ── PydanticAgentDemo ─────────────────────────────────────────────────
        # Full pydantic-ai agent loop with structured output.
        # The agent may call tool nodes wired into tool_types before returning
        # a typed answer with reasoning and confidence.
        #
        #  Objective (ConstantNode)
        #    ↓ out → objective
        #  PydanticAgent (PydanticAgentNode)
        #    ├── done   ──► Answer    (PrintNode) ← answer
        #    ├── done   ──► Reasoning (PrintNode) ← reasoning
        #    └── failed ──► Error     (PrintNode) ← error
        #
        pa_net = net.createNetwork("PydanticAgentDemo", "NodeNetworkSystem")
        self.all_networks[pa_net.id] = pa_net

        pa_obj    = pa_net.createNode("Objective", "ConstantNode")
        pa_model  = pa_net.createNode("Model",     "ConstantNode")
        pa_agent  = pa_net.createNode("Agent",     "PydanticAgentNode")
        pa_ans    = pa_net.createNode("Answer",    "PrintNode")
        pa_reason = pa_net.createNode("Reasoning", "PrintNode")
        pa_err    = pa_net.createNode("Error",     "PrintNode")

        pa_obj.outputs["out"].value   = (
            "Summarise the key benefits of node-based programming in 3 bullet points."
        )
        pa_model.outputs["out"].value = "openai:gpt-4o-mini"
        pa_agent.inputs["model"].value = "openai:gpt-4o-mini"

        graph.add_edge(pa_obj.id,   "out",       pa_agent.id,  "objective")
        graph.add_edge(pa_model.id, "out",       pa_agent.id,  "model")
        graph.add_edge(pa_agent.id, "done",      pa_ans.id,    "exec")
        graph.add_edge(pa_agent.id, "answer",    pa_ans.id,    "value")
        graph.add_edge(pa_agent.id, "done",      pa_reason.id, "exec")
        graph.add_edge(pa_agent.id, "reasoning", pa_reason.id, "value")
        graph.add_edge(pa_agent.id, "failed",    pa_err.id,    "exec")
        graph.add_edge(pa_agent.id, "error",     pa_err.id,    "value")

        self.positions[pa_net.id]    = {"x": 6480, "y": 180}
        self.positions[pa_obj.id]    = {"x": 80,   "y": 100}
        self.positions[pa_model.id]  = {"x": 80,   "y": 300}
        self.positions[pa_agent.id]  = {"x": 440,  "y": 180}
        self.positions[pa_ans.id]    = {"x": 840,  "y": 80}
        self.positions[pa_reason.id] = {"x": 840,  "y": 240}
        self.positions[pa_err.id]    = {"x": 840,  "y": 400}

        # ── AgentPlannerDemo ──────────────────────────────────────────────────
        # Calls AgentExecutor.plan() to synthesise a subgraph from a goal.
        # Outputs the planner's reasoning, node count, and edge count.
        #
        #  Goal (ConstantNode)
        #    ↓ out → objective
        #  Planner (AgentPlannerNode)
        #    ├── done   ──► Reasoning (PrintNode) ← plan_reasoning
        #    ├── done   ──► NodeCount (PrintNode) ← node_count
        #    ├── done   ──► EdgeCount (PrintNode) ← edge_count
        #    └── failed ──► Error     (PrintNode) ← error
        #
        apl_net = net.createNetwork("AgentPlannerDemo", "NodeNetworkSystem")
        self.all_networks[apl_net.id] = apl_net

        apl_goal    = apl_net.createNode("Goal",       "ConstantNode")
        apl_planner = apl_net.createNode("Planner",    "AgentPlannerNode")
        apl_reason  = apl_net.createNode("Reasoning",  "PrintNode")
        apl_ncnt    = apl_net.createNode("NodeCount",  "PrintNode")
        apl_ecnt    = apl_net.createNode("EdgeCount",  "PrintNode")
        apl_err     = apl_net.createNode("Error",      "PrintNode")

        apl_goal.outputs["out"].value      = (
            "Build a graph that reads two numbers, adds them, multiplies by a constant, "
            "and prints the result."
        )
        apl_planner.inputs["model"].value     = "openai:gpt-4o-mini"
        apl_planner.inputs["max_steps"].value = 8

        graph.add_edge(apl_goal.id,    "out",           apl_planner.id, "objective")
        graph.add_edge(apl_planner.id, "done",          apl_reason.id,  "exec")
        graph.add_edge(apl_planner.id, "plan_reasoning",apl_reason.id,  "value")
        graph.add_edge(apl_planner.id, "done",          apl_ncnt.id,    "exec")
        graph.add_edge(apl_planner.id, "node_count",    apl_ncnt.id,    "value")
        graph.add_edge(apl_planner.id, "done",          apl_ecnt.id,    "exec")
        graph.add_edge(apl_planner.id, "edge_count",    apl_ecnt.id,    "value")
        graph.add_edge(apl_planner.id, "failed",        apl_err.id,     "exec")
        graph.add_edge(apl_planner.id, "error",         apl_err.id,     "value")

        self.positions[apl_net.id]     = {"x": 6780, "y": 180}
        self.positions[apl_goal.id]    = {"x": 80,   "y": 280}
        self.positions[apl_planner.id] = {"x": 440,  "y": 280}
        self.positions[apl_reason.id]  = {"x": 840,  "y": 80}
        self.positions[apl_ncnt.id]    = {"x": 840,  "y": 240}
        self.positions[apl_ecnt.id]    = {"x": 840,  "y": 400}
        self.positions[apl_err.id]     = {"x": 840,  "y": 560}

        # ── LLMStreamDemo ─────────────────────────────────────────────────────
        # Demonstrates LLMStreamNode: streams the model response one chunk at a
        # time using the LOOP_AGAIN execution pattern.
        #
        #  Prompt (ConstantNode)
        #    ↓ out → prompt
        #  LLMStream (LLMStreamNode) [is_flow_control_node]
        #    ├── loop_body ──► ChunkPrint (PrintNode) ← chunk
        #    └── completed ──► FullResponse (PrintNode) ← response
        #
        lsd_net = net.createNetwork("LLMStreamDemo", "NodeNetworkSystem")
        self.all_networks[lsd_net.id] = lsd_net

        lsd_prompt = lsd_net.createNode("Prompt",       "ConstantNode")
        lsd_stream = lsd_net.createNode("LLMStream",    "LLMStreamNode")
        lsd_chunk  = lsd_net.createNode("ChunkPrint",   "PrintNode")
        lsd_full   = lsd_net.createNode("FullResponse", "PrintNode")

        lsd_prompt.outputs["out"].value         = (
            "Explain the benefits of streaming in AI applications in 3 sentences."
        )
        lsd_stream.inputs["model"].value        = "openai:gpt-4o-mini"
        lsd_stream.inputs["system_prompt"].value = "You are a concise technical writer."

        graph.add_edge(lsd_prompt.id, "out",       lsd_stream.id, "prompt")
        graph.add_edge(lsd_stream.id, "loop_body", lsd_chunk.id,  "exec")
        graph.add_edge(lsd_stream.id, "chunk",     lsd_chunk.id,  "value")
        graph.add_edge(lsd_stream.id, "completed", lsd_full.id,   "exec")
        graph.add_edge(lsd_stream.id, "response",  lsd_full.id,   "value")

        self.positions[lsd_net.id]    = {"x": 7080, "y": 180}
        self.positions[lsd_prompt.id] = {"x": 80,  "y": 180}
        self.positions[lsd_stream.id] = {"x": 380, "y": 180}
        self.positions[lsd_chunk.id]  = {"x": 740, "y": 80}
        self.positions[lsd_full.id]   = {"x": 740, "y": 300}

        # ── ToolAgentDemo ─────────────────────────────────────────────────────
        # Single-shot ReAct agent with built-in calculator and word_count tools.
        # Runs to completion and outputs the final answer + full tool-call log.
        #
        #  Task (ConstantNode)
        #    ↓ out → task
        #  Agent (ToolAgentNode)
        #    ├── result     ──► ResultOut   (PrintNode)
        #    ├── tool_calls ──► ToolCallOut (PrintNode)
        #    └── steps      ──► StepsOut    (PrintNode)
        #
        tad_net = net.createNetwork("ToolAgentDemo", "NodeNetworkSystem")
        self.all_networks[tad_net.id] = tad_net

        tad_task   = tad_net.createNode("Task",        "ConstantNode")
        tad_agent  = tad_net.createNode("Agent",       "ToolAgentNode")
        tad_result = tad_net.createNode("ResultOut",   "PrintNode")
        tad_calls  = tad_net.createNode("ToolCallOut", "PrintNode")
        tad_steps  = tad_net.createNode("StepsOut",    "PrintNode")

        tad_task.outputs["out"].value    = (
            "What is 42 * 17? Then count the words in: 'The quick brown fox'"
        )
        tad_agent.inputs["model"].value  = "openai:gpt-4o-mini"
        tad_agent.inputs["tools"].value  = ["calculator", "word_count"]

        graph.add_edge(tad_task.id,  "out",        tad_agent.id,  "task")
        graph.add_edge(tad_agent.id, "result",     tad_result.id, "value")
        graph.add_edge(tad_agent.id, "tool_calls", tad_calls.id,  "value")
        graph.add_edge(tad_agent.id, "steps",      tad_steps.id,  "value")

        self.positions[tad_net.id]    = {"x": 7380, "y": 180}
        self.positions[tad_task.id]   = {"x": 80,  "y": 180}
        self.positions[tad_agent.id]  = {"x": 380, "y": 180}
        self.positions[tad_result.id] = {"x": 740, "y": 80}
        self.positions[tad_calls.id]  = {"x": 740, "y": 240}
        self.positions[tad_steps.id]  = {"x": 740, "y": 400}

        # ── ToolAgentStreamDemo ───────────────────────────────────────────────
        # Streaming ReAct agent: emits one step per compute() loop iteration.
        # Each loop_body fires with the next tool_call, tool_result, or final
        # answer — making the agent's reasoning visible in real time.
        #
        #  Task (ConstantNode)
        #    ↓ out → task
        #  AgentStream (ToolAgentStreamNode) [is_flow_control_node]
        #    ├── loop_body ──► StepOut  (PrintNode) ← step_content
        #    └── completed ──► FinalOut (PrintNode) ← result
        #
        tasd_net   = net.createNetwork("ToolAgentStreamDemo", "NodeNetworkSystem")
        self.all_networks[tasd_net.id] = tasd_net

        tasd_task   = tasd_net.createNode("Task",        "ConstantNode")
        tasd_stream = tasd_net.createNode("AgentStream", "ToolAgentStreamNode")
        tasd_step   = tasd_net.createNode("StepOut",     "PrintNode")
        tasd_final  = tasd_net.createNode("FinalOut",    "PrintNode")

        tasd_task.outputs["out"].value    = (
            "Calculate (123 + 456) * 2, then count the words in 'Hello world from the node graph'."
        )
        tasd_stream.inputs["model"].value  = "openai:gpt-4o-mini"
        tasd_stream.inputs["tools"].value  = ["calculator", "word_count"]

        graph.add_edge(tasd_task.id,   "out",          tasd_stream.id, "task")
        graph.add_edge(tasd_stream.id, "loop_body",    tasd_step.id,   "exec")
        graph.add_edge(tasd_stream.id, "step_content", tasd_step.id,   "value")
        graph.add_edge(tasd_stream.id, "completed",    tasd_final.id,  "exec")
        graph.add_edge(tasd_stream.id, "result",       tasd_final.id,  "value")

        self.positions[tasd_net.id]    = {"x": 7680, "y": 180}
        self.positions[tasd_task.id]   = {"x": 80,  "y": 180}
        self.positions[tasd_stream.id] = {"x": 380, "y": 180}
        self.positions[tasd_step.id]   = {"x": 740, "y": 80}
        self.positions[tasd_final.id]  = {"x": 740, "y": 280}

        # ── HumanInTheLoopDemo ────────────────────────────────────────────────
        # Pauses execution at HumanInputNode and waits for:
        #   POST /api/nodes/{hitl_node.id}/human-input  {"response": "Alice"}
        #
        # Intentional gap exposed: ExecCommand.WAIT is returned but the
        # executor has no special handling for it — it behaves identically
        # to CONTINUE because only LOOP_AGAIN is name-checked in the
        # scheduler loop.  This demo is a probe to determine whether
        # suspension / serialisation semantics need to be added.
        #
        #  Question (ConstantNode, "What is your name?")
        #    ↓ out → prompt
        #  HumanIn (HumanInputNode)
        #    ├── responded  ──► Output  (PrintNode) ← response
        #    └── timed_out ──► Timeout (PrintNode)
        #
        hitl_net  = net.createNetwork("HumanInTheLoopDemo", "NodeNetworkSystem")
        self.all_networks[hitl_net.id] = hitl_net

        hitl_q    = hitl_net.createNode("Question", "ConstantNode")
        hitl_node = hitl_net.createNode("HumanIn",  "HumanInputNode")
        hitl_out  = hitl_net.createNode("Output",   "PrintNode")
        hitl_tout = hitl_net.createNode("Timeout",  "PrintNode")

        hitl_q.outputs["out"].value            = "What is your name?"
        hitl_node.inputs["timeout_secs"].value = 60.0

        graph.add_edge(hitl_q.id,    "out",       hitl_node.id, "prompt")
        graph.add_edge(hitl_node.id, "responded",  hitl_out.id,  "exec")
        graph.add_edge(hitl_node.id, "response",   hitl_out.id,  "value")
        graph.add_edge(hitl_node.id, "timed_out",  hitl_tout.id, "exec")

        self.positions[hitl_net.id]   = {"x": 7980, "y": 180}
        self.positions[hitl_q.id]     = {"x": 80,  "y": 180}
        self.positions[hitl_node.id]  = {"x": 360, "y": 180}
        self.positions[hitl_out.id]   = {"x": 680, "y": 80}
        self.positions[hitl_tout.id]  = {"x": 680, "y": 280}

        # ── HumanInputLoopDemo ────────────────────────────────────────────────
        # Loops 3 times, pausing at HumanInputNode each iteration to collect a
        # human response.  Execute by selecting the ForLoop node and pressing Run.
        #
        #  ForLoop (start=0, end=3)
        #    ├── loop_body ──► HumanIn (HumanInputNode)
        #    │                  ├── responded ──► ResponsePrint ← response
        #    │                  └── timed_out ──► TimedOut
        #    └── completed ──► Done
        #
        hitl_loop_net   = net.createNetwork("HumanInputLoopDemo", "NodeNetworkSystem")
        self.all_networks[hitl_loop_net.id] = hitl_loop_net

        hitl_loop_node  = hitl_loop_net.createNode("ForLoop",       "ForLoopNode")
        hitl_loop_human = hitl_loop_net.createNode("HumanIn",       "HumanInputNode")
        hitl_loop_print = hitl_loop_net.createNode("ResponsePrint", "PrintNode")
        hitl_loop_tout  = hitl_loop_net.createNode("TimedOut",      "PrintNode")
        hitl_loop_done  = hitl_loop_net.createNode("Done",          "PrintNode")

        hitl_loop_node.inputs["start"].value         = 0
        hitl_loop_node.inputs["end"].value           = 3
        hitl_loop_node.outputs["index"].value        = 0
        hitl_loop_human.inputs["prompt"].value       = "Enter your response:"
        hitl_loop_human.inputs["timeout_secs"].value = 120.0
        hitl_loop_tout.inputs["value"].value         = "Timed out waiting for response"
        hitl_loop_done.inputs["value"].value         = "All 3 responses collected!"

        graph.add_edge(hitl_loop_node.id,  "loop_body", hitl_loop_human.id, "exec")
        graph.add_edge(hitl_loop_human.id, "responded", hitl_loop_print.id, "exec")
        graph.add_edge(hitl_loop_human.id, "response",  hitl_loop_print.id, "value")
        graph.add_edge(hitl_loop_human.id, "timed_out", hitl_loop_tout.id,  "exec")
        graph.add_edge(hitl_loop_node.id,  "completed", hitl_loop_done.id,  "exec")

        self.positions[hitl_loop_net.id]   = {"x": 8280, "y": 180}
        self.positions[hitl_loop_node.id]  = {"x": 80,  "y": 180}
        self.positions[hitl_loop_human.id] = {"x": 400, "y": 180}
        self.positions[hitl_loop_print.id] = {"x": 740, "y": 80}
        self.positions[hitl_loop_tout.id]  = {"x": 740, "y": 300}
        self.positions[hitl_loop_done.id]  = {"x": 740, "y": 480}

        # ── ImageRefinementDemo ───────────────────────────────────────────────
        # Interactive image generation with iterative human-guided refinement.
        # Press Run on WhileLoopNode to start.
        #
        # Per iteration:
        #   1. Human types a refinement directive (e.g. "make it snow")
        #      or "done" / empty to exit.
        #   2. PromptRefineExecNode combines the PREVIOUS image's revised_prompt
        #      with the directive via LLM.  On the FIRST iteration, the
        #      feedback is used directly as the initial prompt (no prior image).
        #   3. ImageGenExecNode calls DALL-E 3 with the refined prompt.
        #   4. ShowURL prints the generated image URL.
        #   5. The loop repeats.
        #
        # Topology:
        #   WhileLoop (stop_signal ← HumanIn.response)
        #     ├── loop_body  ──► HumanIn (HumanInputNode)
        #     │                   ├── responded  ──► RefinePrompt.exec
        #     │                   │                   next ──► ImageGen.exec
        #     │                   │                              next ──► ShowURL
        #     │                   │              (ImageGen.revised_prompt ──► RefinePrompt.original_prompt)
        #     │                   ├── response   ──► WhileLoop.stop_signal
        #     │                   ├── response   ──► RefinePrompt.feedback
        #     │                   └── timed_out  ──► Done
        #     └── completed  ──► Done
        #
        imgref_net    = net.createNetwork("ImageRefinementDemo", "NodeNetworkSystem")
        self.all_networks[imgref_net.id] = imgref_net

        imgref_loop   = imgref_net.createNode("WhileLoop",    "WhileLoopNode")
        imgref_human  = imgref_net.createNode("HumanIn",      "HumanInputNode")
        imgref_refine = imgref_net.createNode("RefinePrompt", "PromptRefineExecNode")
        imgref_gen    = imgref_net.createNode("ImageGen",     "ImageGenExecNode")
        imgref_show   = imgref_net.createNode("ShowURL",      "PrintNode")
        imgref_done   = imgref_net.createNode("Done",         "PrintNode")

        imgref_human.inputs["prompt"].value       = "Enter image prompt (or refinement for next round). Type 'done' to exit."
        imgref_human.inputs["timeout_secs"].value = 300.0
        imgref_done.inputs["value"].value         = "Image refinement session complete."

        graph.add_edge(imgref_loop.id,   "loop_body",      imgref_human.id,  "exec")
        graph.add_edge(imgref_human.id,  "response",       imgref_loop.id,   "stop_signal")
        graph.add_edge(imgref_human.id,  "response",       imgref_refine.id, "feedback")
        graph.add_edge(imgref_human.id,  "responded",      imgref_refine.id, "exec")
        graph.add_edge(imgref_refine.id, "refined_prompt", imgref_gen.id,    "prompt")  # ← was missing
        graph.add_edge(imgref_refine.id, "next",           imgref_gen.id,    "exec")
        graph.add_edge(imgref_gen.id,    "revised_prompt", imgref_refine.id, "original_prompt")
        graph.add_edge(imgref_gen.id,    "next",           imgref_show.id,   "exec")
        graph.add_edge(imgref_gen.id,    "url",            imgref_show.id,   "value")
        graph.add_edge(imgref_human.id,  "timed_out",      imgref_done.id,   "exec")
        graph.add_edge(imgref_loop.id,   "completed",      imgref_done.id,   "exec")

        self.positions[imgref_net.id]    = {"x": 8580, "y": 180}
        self.positions[imgref_loop.id]   = {"x": 80,   "y": 280}
        self.positions[imgref_human.id]  = {"x": 380,  "y": 280}
        self.positions[imgref_refine.id] = {"x": 700,  "y": 180}
        self.positions[imgref_gen.id]    = {"x": 1040, "y": 180}
        self.positions[imgref_show.id]   = {"x": 1380, "y": 80}
        self.positions[imgref_done.id]   = {"x": 380,  "y": 480}

        # ── DeadlockCycleDemo ───────────────────────────────────────────────────
        # Demonstrates a CIRCULAR DATA DEPENDENCY that the executor cannot
        # resolve.  Run this graph to see the deadlock RuntimeError.
        #
        # AddA depends on AddB's output, and AddB depends on AddA's output.
        # Neither can execute first — a classic mutual dependency deadlock.
        # The executor detects this after const5 and const3 are consumed and
        # no further progress is possible.
        #
        #   const5 (5) ──┈ a
        #               AddA.sum ──┈ b         ←── CYCLE
        #   const3 (3) ──┈ a    AddB.sum ──┈ b  ←── CYCLE
        #               Trigger (PrintNode) ←─ AddA.sum
        #
        # SAFE equivalent: break the cycle by routing one value through a
        # WhileLoopNode so the back-edge becomes a deferred LOOP_AGAIN command
        # rather than a live data dependency.
        #
        dl_net     = net.createNetwork("DeadlockCycleDemo", "NodeNetworkSystem")
        self.all_networks[dl_net.id] = dl_net

        dl_const5  = dl_net.createNode("Const5",   "ConstantNode")
        dl_const3  = dl_net.createNode("Const3",   "ConstantNode")
        dl_addA    = dl_net.createNode("AddA",     "AddNode")
        dl_addB    = dl_net.createNode("AddB",     "AddNode")
        dl_trigger = dl_net.createNode("Trigger",  "PrintNode")

        dl_const5.outputs["out"].value = 5
        dl_const3.outputs["out"].value = 3

        graph.add_edge(dl_const5.id,  "out", dl_addA.id,    "a")
        graph.add_edge(dl_addB.id,    "sum", dl_addA.id,    "b")  # ← CYCLE: A waits for B
        graph.add_edge(dl_const3.id,  "out", dl_addB.id,    "a")
        graph.add_edge(dl_addA.id,    "sum", dl_addB.id,    "b")  # ← CYCLE: B waits for A
        graph.add_edge(dl_addA.id,    "sum", dl_trigger.id, "value")

        self.positions[dl_net.id]     = {"x": 8880, "y": 180}
        self.positions[dl_const5.id]  = {"x": 80,   "y": 80}
        self.positions[dl_const3.id]  = {"x": 80,   "y": 280}
        self.positions[dl_addA.id]    = {"x": 380,  "y": 80}
        self.positions[dl_addB.id]    = {"x": 380,  "y": 280}
        self.positions[dl_trigger.id] = {"x": 700,  "y": 180}

    # ── Diffusion sampler demos ───────────────────────────────────────────────

    def _seed_sampler_demos(self, net, graph) -> None:
        """Demonstration subnetworks for whole-run and step-wise diffusion sampling."""
        required_types = {
            "CheckpointLoader",
            "CLIPTextEncode",
            "EmptyLatentImage",
            "KSampler",
            "KSamplerStep",
            "VAEDecode",
            "SaveImage",
        }
        if not required_types.issubset(Node._node_registry):
            missing = ", ".join(sorted(required_types.difference(Node._node_registry)))
            print(f"[demo] sampler demos skipped; missing node types: {missing}")
            return

        # ── KSamplerDemo: full denoising pass → decode → save ────────────────
        ks_net = net.createNetwork("KSamplerDemo", "NodeNetworkSystem")
        self.all_networks[ks_net.id] = ks_net

        ks_loader = ks_net.createNode("Checkpoint", "CheckpointLoader")
        ks_pos    = ks_net.createNode("PositivePrompt", "CLIPTextEncode")
        ks_neg    = ks_net.createNode("NegativePrompt", "CLIPTextEncode")
        ks_latent = ks_net.createNode("EmptyLatent", "EmptyLatentImage")
        ks_sample = ks_net.createNode("KSampler", "KSampler")
        ks_decode = ks_net.createNode("Decode", "VAEDecode")
        ks_save   = ks_net.createNode("SaveImage", "SaveImage")

        ks_loader.inputs["ckpt_path"].value = "/Users/robertpringle/development/ai_models/sd-1.5/"
        ks_pos.inputs["text"].value = "a small robot sketching a node graph, soft studio light"
        ks_neg.inputs["text"].value = "blurry, low quality, distorted"
        ks_latent.inputs["width"].value = 512
        ks_latent.inputs["height"].value = 512
        ks_latent.inputs["batch_size"].value = 1
        ks_sample.inputs["seed"].value = 12345
        ks_sample.inputs["steps"].value = 12
        ks_sample.inputs["cfg"].value = 7.0
        ks_sample.inputs["sampler_name"].value = "euler"
        ks_sample.inputs["scheduler"].value = "normal"
        ks_sample.inputs["denoise"].value = 1.0
        ks_save.inputs["filename_prefix"].value = "ksampler_demo"
        ks_save.inputs["output_dir"].value = "./output"

        graph.add_edge(ks_loader.id, "next", ks_pos.id, "exec")
        graph.add_edge(ks_loader.id, "next", ks_neg.id, "exec")
        graph.add_edge(ks_loader.id, "next", ks_latent.id, "exec")
        graph.add_edge(ks_pos.id, "next", ks_sample.id, "exec")
        graph.add_edge(ks_sample.id, "next", ks_decode.id, "exec")
        graph.add_edge(ks_decode.id, "next", ks_save.id, "exec")
        graph.add_edge(ks_loader.id, "MODEL", ks_sample.id, "MODEL")
        graph.add_edge(ks_loader.id, "CLIP", ks_pos.id, "CLIP")
        graph.add_edge(ks_loader.id, "CLIP", ks_neg.id, "CLIP")
        graph.add_edge(ks_loader.id, "VAE", ks_decode.id, "VAE")
        graph.add_edge(ks_pos.id, "CONDITIONING", ks_sample.id, "positive")
        graph.add_edge(ks_neg.id, "CONDITIONING", ks_sample.id, "negative")
        graph.add_edge(ks_latent.id, "LATENT", ks_sample.id, "latent_image")
        graph.add_edge(ks_sample.id, "LATENT", ks_decode.id, "samples")
        graph.add_edge(ks_decode.id, "IMAGE", ks_save.id, "images")

        self.positions[ks_net.id]    = {"x": 9180, "y": 180}
        self.positions[ks_loader.id] = {"x": 80,   "y": 220}
        self.positions[ks_pos.id]    = {"x": 380,  "y": 80}
        self.positions[ks_neg.id]    = {"x": 380,  "y": 260}
        self.positions[ks_latent.id] = {"x": 380,  "y": 440}
        self.positions[ks_sample.id] = {"x": 720,  "y": 240}
        self.positions[ks_decode.id] = {"x": 1060, "y": 240}
        self.positions[ks_save.id]   = {"x": 1400, "y": 240}

        # ── KSamplerStepDemo: one denoising step per loop iteration ──────────
        step_net = net.createNetwork("KSamplerStepDemo", "NodeNetworkSystem")
        self.all_networks[step_net.id] = step_net

        st_loader = step_net.createNode("Checkpoint", "CheckpointLoader")
        st_pos    = step_net.createNode("PositivePrompt", "CLIPTextEncode")
        st_neg    = step_net.createNode("NegativePrompt", "CLIPTextEncode")
        st_latent = step_net.createNode("EmptyLatent", "EmptyLatentImage")
        st_sample = step_net.createNode("KSamplerStep", "KSamplerStep")
        st_preview_decode = step_net.createNode("PreviewDecode", "VAEDecode")
        st_preview_save   = step_net.createNode("SavePreview", "SaveImage")
        st_final_decode   = step_net.createNode("FinalDecode", "VAEDecode")
        st_final_save     = step_net.createNode("SaveFinal", "SaveImage")

        st_loader.inputs["ckpt_path"].value = "/Users/robertpringle/development/ai_models/sd-1.5/"
        st_pos.inputs["text"].value = "a watercolor city skyline generated step by step"
        st_neg.inputs["text"].value = "noise, artifacts, overexposed"
        st_latent.inputs["width"].value = 512
        st_latent.inputs["height"].value = 512
        st_latent.inputs["batch_size"].value = 1
        st_sample.inputs["seed"].value = 67890
        st_sample.inputs["steps"].value = 8
        st_sample.inputs["cfg"].value = 7.0
        st_sample.inputs["sampler_name"].value = "euler"
        st_sample.inputs["scheduler"].value = "normal"
        st_sample.inputs["denoise"].value = 1.0
        st_preview_save.inputs["filename_prefix"].value = "ksampler_step_preview"
        st_preview_save.inputs["output_dir"].value = "./output"
        st_final_save.inputs["filename_prefix"].value = "ksampler_step_final"
        st_final_save.inputs["output_dir"].value = "./output"

        graph.add_edge(st_loader.id, "next", st_pos.id, "exec")
        graph.add_edge(st_loader.id, "next", st_neg.id, "exec")
        graph.add_edge(st_loader.id, "next", st_latent.id, "exec")
        graph.add_edge(st_pos.id, "next", st_sample.id, "exec")
        graph.add_edge(st_sample.id, "loop_body", st_preview_decode.id, "exec")
        graph.add_edge(st_preview_decode.id, "next", st_preview_save.id, "exec")
        graph.add_edge(st_sample.id, "done", st_final_decode.id, "exec")
        graph.add_edge(st_final_decode.id, "next", st_final_save.id, "exec")
        graph.add_edge(st_loader.id, "MODEL", st_sample.id, "MODEL")
        graph.add_edge(st_loader.id, "CLIP", st_pos.id, "CLIP")
        graph.add_edge(st_loader.id, "CLIP", st_neg.id, "CLIP")
        graph.add_edge(st_loader.id, "VAE", st_preview_decode.id, "VAE")
        graph.add_edge(st_loader.id, "VAE", st_final_decode.id, "VAE")
        graph.add_edge(st_pos.id, "CONDITIONING", st_sample.id, "positive")
        graph.add_edge(st_neg.id, "CONDITIONING", st_sample.id, "negative")
        graph.add_edge(st_latent.id, "LATENT", st_sample.id, "latent_image")
        graph.add_edge(st_sample.id, "LATENT", st_preview_decode.id, "samples")
        graph.add_edge(st_sample.id, "LATENT", st_final_decode.id, "samples")
        graph.add_edge(st_preview_decode.id, "IMAGE", st_preview_save.id, "images")
        graph.add_edge(st_final_decode.id, "IMAGE", st_final_save.id, "images")

        self.positions[step_net.id]          = {"x": 9480, "y": 180}
        self.positions[st_loader.id]         = {"x": 80,   "y": 240}
        self.positions[st_pos.id]            = {"x": 380,  "y": 80}
        self.positions[st_neg.id]            = {"x": 380,  "y": 260}
        self.positions[st_latent.id]         = {"x": 380,  "y": 440}
        self.positions[st_sample.id]         = {"x": 720,  "y": 240}
        self.positions[st_preview_decode.id] = {"x": 1060, "y": 120}
        self.positions[st_preview_save.id]   = {"x": 1400, "y": 120}
        self.positions[st_final_decode.id]   = {"x": 1060, "y": 360}
        self.positions[st_final_save.id]     = {"x": 1400, "y": 360}

    # ── Network helpers ──────────────────────────────────────────────────────

    def get_network(self, network_id: str) -> Optional[NodeNetwork]:
        return self.all_networks.get(network_id)

    def create_subnetwork(self, parent_id: str, name: str) -> NodeNetwork:
        parent = self.get_network(parent_id)
        if parent is None:
            raise ValueError(f"Network '{parent_id}' not found")
        subnet = parent.createNetwork(name, "NodeNetworkSystem")
        self.all_networks[subnet.id] = subnet
        return subnet

    # ── Node helpers ─────────────────────────────────────────────────────────

    def create_node(self, network_id: str, node_type: str, name: str) -> Node:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        return network.createNode(name, node_type)

    def delete_node(self, network_id: str, node_id: str) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        # Call graph.deleteNode directly — NodeNetwork.deleteNode takes a name,
        # but here we have an id from the REST request.
        network.graph.deleteNode(node_id)
        self.positions.pop(node_id, None)
        # If the deleted node was itself a network, remove from allNetworks.
        self.all_networks.pop(node_id, None)

    def rename_node(self, network_id: str, node_id: str, name: str) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        next_name = name.strip()
        if not next_name:
            raise ValueError("Node name cannot be empty")
        node = network.graph.get_node_by_id(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found")
        if getattr(node, "network_id", None) != network.id:
            raise ValueError(f"Node '{node_id}' is not in network '{network_id}'")
        node.name = next_name

    def group_nodes(self, network_id: str, node_ids: list[str], name: str = "") -> str:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")

        selected_ids = set(node_ids)
        if not selected_ids:
            raise ValueError("Select at least one node to group")

        selected_nodes = []
        for node_id in node_ids:
            node = network.graph.get_node_by_id(node_id)
            if node is None:
                raise ValueError(f"Node '{node_id}' not found")
            if getattr(node, "network_id", None) != network.id:
                raise ValueError(f"Node '{node_id}' is not in network '{network_id}'")
            if getattr(node, "kind", None) and getattr(node, "id", None) == network.id:
                raise ValueError("Cannot group the network tunnel node")
            selected_nodes.append(node)

        subnet_name = name.strip() if name.strip() else f"subnet_{random.randint(1000, 999999):06d}"
        subnet = network.createNetwork(subnet_name, "NodeNetworkSystem")
        self.all_networks[subnet.id] = subnet

        selected_positions = [
            self.positions.get(node.id, {"x": 0, "y": 0})
            for node in selected_nodes
        ]
        min_x = min((pos.get("x", 0) for pos in selected_positions), default=0)
        min_y = min((pos.get("y", 0) for pos in selected_positions), default=0)
        self.positions[subnet.id] = {"x": min_x, "y": min_y}
        for node in selected_nodes:
            pos = self.positions.get(node.id)
            if pos is not None:
                self.positions[node.id] = {
                    "x": pos.get("x", 0) - min_x + 120,
                    "y": pos.get("y", 0) - min_y + 120,
                }
            node.network_id = subnet.id

        existing_inputs = set(subnet.inputs.keys())
        existing_outputs = set(subnet.outputs.keys())
        crossing_edges = [
            edge
            for edge in list(network.graph.edges)
            if (edge.from_node_id in selected_ids) != (edge.to_node_id in selected_ids)
        ]

        for index, edge in enumerate(crossing_edges, start=1):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )

            if edge.to_node_id in selected_ids:
                target_node = network.graph.get_node_by_id(edge.to_node_id)
                if target_node is None:
                    continue
                template_port = getattr(target_node, "inputs", {}).get(edge.to_port_name)
                if template_port is None:
                    raise ValueError(
                        f"Input port '{edge.to_port_name}' not found on node '{edge.to_node_id}'"
                    )
                port_name = self._make_unique_tunnel_port_name(
                    existing_inputs,
                    f"{edge.to_port_name}_in_{index}",
                    f"{edge.to_port_name}_in",
                )
                existing_inputs.add(port_name)
                self._create_typed_tunnel_input_port(subnet, port_name, template_port)
                network.graph.add_edge(edge.from_node_id, edge.from_port_name, subnet.id, port_name)
                network.graph.add_edge(subnet.id, port_name, edge.to_node_id, edge.to_port_name)
            else:
                source_node = network.graph.get_node_by_id(edge.from_node_id)
                if source_node is None:
                    continue
                template_port = getattr(source_node, "outputs", {}).get(edge.from_port_name)
                if template_port is None:
                    raise ValueError(
                        f"Output port '{edge.from_port_name}' not found on node '{edge.from_node_id}'"
                    )
                port_name = self._make_unique_tunnel_port_name(
                    existing_outputs,
                    f"{edge.from_port_name}_out_{index}",
                    f"{edge.from_port_name}_out",
                )
                existing_outputs.add(port_name)
                self._create_typed_tunnel_output_port(subnet, port_name, template_port)
                network.graph.add_edge(edge.from_node_id, edge.from_port_name, subnet.id, port_name)
                network.graph.add_edge(subnet.id, port_name, edge.to_node_id, edge.to_port_name)

        return subnet.id

    # ── Edge helpers ─────────────────────────────────────────────────────────

    def add_edge(
        self,
        network_id: str,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        network.graph.add_edge(source_node_id, source_port, target_node_id, target_port)

    def remove_edge(
        self,
        network_id: str,
        source_node_id: str,
        source_port: str,
        target_node_id: str,
        target_port: str,
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        network.graph.delete_edge(source_node_id, source_port, target_node_id, target_port)

    # ── Position helpers ─────────────────────────────────────────────────────

    def set_position(self, node_id: str, x: float, y: float) -> None:
        self.positions[node_id] = {"x": x, "y": y}

    # ── Data helpers ─────────────────────────────────────────────────────────

    def set_port_value(
        self, network_id: str, node_id: str, port_name: str, value: Any
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        node = network.graph.get_node_by_id(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found")
        port = node.inputs.get(port_name) or node.outputs.get(port_name)
        if port is None:
            raise ValueError(f"Port '{port_name}' not found on node '{node_id}'")
        port.value = value
        node.markDirty()

    # ── Dynamic node port helpers ──────────────────────────────────────────────

    def _resolve_node_for_port_mutation(self, network_id: str, node_id: str) -> Node:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        node = network.graph.get_node_by_id(node_id)
        if node is None:
            raise ValueError(f"Node '{node_id}' not found")
        if getattr(node, "network_id", None) != network.id:
            raise ValueError(f"Node '{node_id}' is not in network '{network_id}'")
        return node

    @staticmethod
    def _resolve_value_type(value_type: str) -> ValueType:
        try:
            return ValueType(value_type.lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported value type '{value_type}'") from exc

    def _delete_edges_for_node_port(
        self,
        network: NodeNetwork,
        node_id: str,
        port_name: str,
    ) -> None:
        for edge in list(network.graph.get_incoming_edges(node_id, port_name)):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )
        for edge in list(network.graph.get_outgoing_edges(node_id, port_name)):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )

    def add_dynamic_input_port(
        self,
        network_id: str,
        node_id: str,
        port_name: str,
        value_type: str,
    ) -> None:
        node = self._resolve_node_for_port_mutation(network_id, node_id)
        add_port = getattr(node, "add_dynamic_input_port", None)
        if not callable(add_port):
            raise ValueError(f"Node type '{node.type}' does not support dynamic input ports")
        add_port(port_name, self._resolve_value_type(value_type))
        node.markDirty()

    def remove_dynamic_input_port(
        self,
        network_id: str,
        node_id: str,
        port_name: str,
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        node = self._resolve_node_for_port_mutation(network_id, node_id)
        remove_port = getattr(node, "remove_dynamic_input_port", None)
        if not callable(remove_port):
            raise ValueError(f"Node type '{node.type}' does not support dynamic input ports")
        remove_port(port_name)
        self._delete_edges_for_node_port(network, node_id, port_name)
        node.markDirty()

    def add_dynamic_output_port(
        self,
        network_id: str,
        node_id: str,
        port_name: str,
        value_type: str,
        port_function: str = "DATA",
    ) -> None:
        node = self._resolve_node_for_port_mutation(network_id, node_id)
        add_port = getattr(node, "add_dynamic_output_port", None)
        if not callable(add_port):
            raise ValueError(f"Node type '{node.type}' does not support dynamic output ports")
        add_port(port_name, self._resolve_value_type(value_type), port_function.upper())
        node.markDirty()

    def remove_dynamic_output_port(
        self,
        network_id: str,
        node_id: str,
        port_name: str,
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        node = self._resolve_node_for_port_mutation(network_id, node_id)
        remove_port = getattr(node, "remove_dynamic_output_port", None)
        if not callable(remove_port):
            raise ValueError(f"Node type '{node.type}' does not support dynamic output ports")
        remove_port(port_name)
        self._delete_edges_for_node_port(network, node_id, port_name)
        node.markDirty()

    # ── Tunnel port helpers ───────────────────────────────────────────────────

    def add_tunnel_port(
        self,
        network_id: str,
        port_name: str,
        direction: str,
        port_function: str = "DATA",
        value_type: str = "ANY",
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        try:
            resolved_function = PortFunction[port_function.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported port function '{port_function}'") from exc
        try:
            resolved_value_type = ValueType(value_type.lower())
        except ValueError as exc:
            raise ValueError(f"Unsupported value type '{value_type}'") from exc

        if direction == "input":
            if resolved_function == PortFunction.CONTROL:
                network.add_control_input_port(port_name)
            else:
                network.add_data_input_port(port_name, resolved_value_type)
        else:
            if resolved_function == PortFunction.CONTROL:
                network.add_control_output_port(port_name)
            else:
                network.add_data_output_port(port_name, resolved_value_type)

    def _make_unique_tunnel_port_name(
        self,
        existing_names: set[str],
        base_name: str,
        suffix_label: str,
    ) -> str:
        unique_name = base_name
        suffix = 2
        while unique_name in existing_names:
            unique_name = f"{suffix_label}_{suffix}_{base_name.split('_')[-1]}"
            suffix += 1
        return unique_name

    def _create_typed_tunnel_input_port(
        self, network: NodeNetwork, port_name: str, template_port: Any
    ) -> None:
        if getattr(template_port, "function", None) == PortFunction.CONTROL:
            network.add_control_input_port(port_name)
            return
        network.add_data_input_port(
            port_name,
            getattr(template_port, "data_type", ValueType.ANY),
        )

    def _create_typed_tunnel_output_port(
        self, network: NodeNetwork, port_name: str, template_port: Any
    ) -> None:
        if getattr(template_port, "function", None) == PortFunction.CONTROL:
            network.add_control_output_port(port_name)
            return
        network.add_data_output_port(
            port_name,
            getattr(template_port, "data_type", ValueType.ANY),
        )

    def connect_to_new_tunnel_input(
        self,
        network_id: str,
        source_node_id: str,
        source_port: str,
    ) -> str:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        trimmed_source_port = source_port.strip()
        if not trimmed_source_port:
            raise ValueError("Source port is required")
        source_node = network.graph.get_node_by_id(source_node_id)
        if source_node is None:
            raise ValueError(f"Source node '{source_node_id}' not found")
        template_port = getattr(source_node, "outputs", {}).get(trimmed_source_port)
        if template_port is None:
            template_port = getattr(source_node, "inputs", {}).get(trimmed_source_port)
        if template_port is None:
            raise ValueError(f"Port '{trimmed_source_port}' not found on node '{source_node_id}'")
        unique_name = self._make_unique_tunnel_port_name(
            set(network.inputs.keys()),
            f"{trimmed_source_port}_in",
            trimmed_source_port,
        )
        self._create_typed_tunnel_input_port(network, unique_name, template_port)
        network.graph.add_edge(source_node_id, trimmed_source_port, network.id, unique_name)
        return unique_name

    def connect_new_tunnel_input_to_target(
        self,
        network_id: str,
        target_node_id: str,
        target_port: str,
    ) -> str:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        trimmed_target_port = target_port.strip()
        if not trimmed_target_port:
            raise ValueError("Target port is required")
        target_node = network.graph.get_node_by_id(target_node_id)
        if target_node is None:
            raise ValueError(f"Target node '{target_node_id}' not found")
        template_port = getattr(target_node, "inputs", {}).get(trimmed_target_port)
        if template_port is None:
            raise ValueError(f"Input port '{trimmed_target_port}' not found on node '{target_node_id}'")
        unique_name = self._make_unique_tunnel_port_name(
            set(network.inputs.keys()),
            f"{trimmed_target_port}_in",
            trimmed_target_port,
        )
        self._create_typed_tunnel_input_port(network, unique_name, template_port)
        network.graph.add_edge(network.id, unique_name, target_node_id, trimmed_target_port)
        return unique_name

    def connect_source_to_new_tunnel_output(
        self,
        network_id: str,
        source_node_id: str,
        source_port: str,
    ) -> str:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        trimmed_source_port = source_port.strip()
        if not trimmed_source_port:
            raise ValueError("Source port is required")
        source_node = network.graph.get_node_by_id(source_node_id)
        if source_node is None:
            raise ValueError(f"Source node '{source_node_id}' not found")
        template_port = getattr(source_node, "outputs", {}).get(trimmed_source_port)
        if template_port is None:
            raise ValueError(f"Output port '{trimmed_source_port}' not found on node '{source_node_id}'")
        unique_name = self._make_unique_tunnel_port_name(
            set(network.outputs.keys()),
            f"{trimmed_source_port}_out",
            trimmed_source_port,
        )
        self._create_typed_tunnel_output_port(network, unique_name, template_port)
        network.graph.add_edge(source_node_id, trimmed_source_port, network.id, unique_name)
        return unique_name

    def _delete_edges_for_tunnel_port(
        self, network: NodeNetwork, port_name: str
    ) -> None:
        for edge in list(network.graph.get_incoming_edges(network.id, port_name)):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )
        for edge in list(network.graph.get_outgoing_edges(network.id, port_name)):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )

    def remove_tunnel_port(
        self, network_id: str, port_name: str, direction: str
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        ports = network.inputs if direction == "input" else network.outputs
        if port_name not in ports:
            raise ValueError(f"Tunnel {direction} port '{port_name}' does not exist")
        self._delete_edges_for_tunnel_port(network, port_name)
        del ports[port_name]

    def rename_tunnel_port(
        self, network_id: str, old_name: str, new_name: str, direction: str
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        ports = network.inputs if direction == "input" else network.outputs
        if old_name not in ports:
            raise ValueError(f"Tunnel {direction} port '{old_name}' does not exist")
        if new_name in ports:
            raise ValueError(f"Tunnel {direction} port '{new_name}' already exists")

        port = ports.pop(old_name)
        port.port_name = new_name
        ports[new_name] = port

        for edge in list(network.graph.get_incoming_edges(network.id, old_name)):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )
            network.graph.add_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                new_name,
            )
        for edge in list(network.graph.get_outgoing_edges(network.id, old_name)):
            network.graph.delete_edge(
                edge.from_node_id,
                edge.from_port_name,
                edge.to_node_id,
                edge.to_port_name,
            )
            network.graph.add_edge(
                edge.from_node_id,
                new_name,
                edge.to_node_id,
                edge.to_port_name,
            )


# ---------------------------------------------------------------------------
# Module-level singleton — created once when this module is first imported.
# ---------------------------------------------------------------------------

graph_state = GraphState()
