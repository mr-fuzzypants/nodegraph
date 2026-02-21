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

from typing import Any, Dict, Optional

from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Node import Node


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

        # ── LangChain demos ───────────────────────────────────────────────────
        self._seed_langchain_demo(net, graph)

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

    # ── LangChain demo seed ───────────────────────────────────────────────────

    def _seed_langchain_demo(self, net, graph) -> None:
        """Three demonstration subnetworks for LangChain nodes."""
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
        llm_node.inputs["model"].value       = "gpt-4o-mini"
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
        agent_node.inputs["model"].value    = "gpt-4o-mini"

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
        s_stream.inputs["model"].value         = "gpt-4o-mini"
        s_stream.inputs["system_prompt"].value = "You are a helpful assistant."

        graph.add_edge(s_tmpl.id,   "prompt",   s_stream.id, "prompt")
        graph.add_edge(s_stream.id, "response", s_print.id,  "value")

        self.positions[stream_net.id] = {"x": 3780, "y": 180}
        self.positions[s_tmpl.id]     = {"x": 80,  "y": 180}
        self.positions[s_stream.id]   = {"x": 420, "y": 180}
        self.positions[s_print.id]    = {"x": 760, "y": 180}

        # ── MultiStepAgent: multi-step calculator chain ────────────────────────
        # Mirrors langchain_agent_example.py scenario 2:
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
        ms_agent.inputs["model"].value   = "gpt-4o-mini"

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
        asd_agent.inputs["model"].value  = "gpt-4o-mini"

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
        mss_agent.inputs["model"].value = "gpt-4o-mini"

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

    # ── Tunnel port helpers ───────────────────────────────────────────────────

    def add_tunnel_port(
        self, network_id: str, port_name: str, direction: str
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        if direction == "input":
            network.add_data_input_port(port_name)
        else:
            network.add_data_output_port(port_name)

    def remove_tunnel_port(
        self, network_id: str, port_name: str, direction: str
    ) -> None:
        network = self.get_network(network_id)
        if network is None:
            raise ValueError(f"Network '{network_id}' not found")
        if direction == "input":
            network.remove_data_input_port(port_name)
        else:
            network.remove_data_output_port(port_name)


# ---------------------------------------------------------------------------
# Module-level singleton — created once when this module is first imported.
# ---------------------------------------------------------------------------

graph_state = GraphState()
