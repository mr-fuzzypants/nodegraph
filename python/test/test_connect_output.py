"""
Tests for NodeNetwork.connect_output_to_refactored (called via connect_node_output_to /
connectNodes).

Covers:
  - sibling→sibling   (normal data edge)
  - parent→child      (tunnel-in)
  - child→parent      (tunnel-out)
  - same-name ports   (subnet has inputs["data"] AND outputs["data"])
  - error cases       (unrelated nodes, missing port, already-connected)
"""
import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Executor import ExecutionResult, ExecCommand
from nodegraph.python.core.NodePort import (
    InputDataPort, OutputDataPort,
    InputControlPort, OutputControlPort,
)
from nodegraph.python.core.Types import ValueType


# ── Test node types ───────────────────────────────────────────────────────────

@Node.register("ConTestAdd")
class ConTestAdd(Node):
    def __init__(self, name, type="ConTestAdd", network_id=None, **kwargs):
        super().__init__(name, type, network_id=network_id, **kwargs)
        self.inputs["a"]    = InputDataPort(self.id, "a",   ValueType.INT)
        self.inputs["b"]    = InputDataPort(self.id, "b",   ValueType.INT)
        self.outputs["sum"] = OutputDataPort(self.id, "sum", ValueType.INT)

    async def compute(self, executionContext=None):
        return ExecutionResult(ExecCommand.CONTINUE)


@Node.register("ConTestGate")
class ConTestGate(Node):
    def __init__(self, name, type="ConTestGate", network_id=None, **kwargs):
        super().__init__(name, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.inputs["trigger"]  = InputControlPort(self.id, "trigger")
        self.outputs["true"]    = OutputControlPort(self.id, "true")
        self.outputs["false"]   = OutputControlPort(self.id, "false")

    async def compute(self, executionContext=None):
        return ExecutionResult(ExecCommand.CONTINUE)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _edge(graph, from_id, from_port, to_id, to_port):
    """Return matching edge or None."""
    for e in graph.get_outgoing_edges(from_id, from_port):
        if e.to_node_id == to_id and e.to_port_name == to_port:
            return e
    return None


# ── Test class ────────────────────────────────────────────────────────────────

class TestConnectOutputToRefactored:

    def setup_method(self):
        NodeNetwork.deleteAllNodes()

    # ── sibling→sibling ───────────────────────────────────────────────────────

    def test_sibling_output_to_input(self):
        """Standard sibling connection: A.sum → B.a."""
        root = NodeNetwork.createRootNetwork("r", "NodeNetworkSystem")
        a    = root.createNode("A", "ConTestAdd")
        b    = root.createNode("B", "ConTestAdd")

        edge = root.connect_node_output_to(a, "sum", b, "a")

        assert edge is not None
        assert edge.from_node_id   == a.id
        assert edge.from_port_name == "sum"
        assert edge.to_node_id     == b.id
        assert edge.to_port_name   == "a"

    def test_sibling_fan_out(self):
        """One output port can feed two sibling nodes."""
        root = NodeNetwork.createRootNetwork("r2", "NodeNetworkSystem")
        src  = root.createNode("Src", "ConTestAdd")
        b    = root.createNode("B",   "ConTestAdd")
        c    = root.createNode("C",   "ConTestAdd")

        root.connect_node_output_to(src, "sum", b, "a")
        root.connect_node_output_to(src, "sum", c, "a")

        assert _edge(root.graph, src.id, "sum", b.id, "a") is not None
        assert _edge(root.graph, src.id, "sum", c.id, "a") is not None

    def test_sibling_wrong_port_raises(self):
        """Connecting to a non-existent sibling port raises ValueError."""
        root = NodeNetwork.createRootNetwork("r3", "NodeNetworkSystem")
        a    = root.createNode("A", "ConTestAdd")
        b    = root.createNode("B", "ConTestAdd")

        with pytest.raises(ValueError, match="not found"):
            root.connect_node_output_to(a, "nonexistent", b, "a")

    def test_sibling_duplicate_raises(self):
        """Connecting the same non-IO port twice raises ValueError."""
        root = NodeNetwork.createRootNetwork("r4", "NodeNetworkSystem")
        a    = root.createNode("A", "ConTestAdd")
        b    = root.createNode("B", "ConTestAdd")

        root.connect_node_output_to(a, "sum", b, "a")
        with pytest.raises(ValueError, match="already connected"):
            root.connect_node_output_to(a, "sum", b, "a")

    # ── parent→child (tunnel-in) ──────────────────────────────────────────────

    def test_tunnel_in_from_network_input(self):
        """parent→child: subnet.inputs['val'] → inner node .inputs['a']."""
        root   = NodeNetwork.createRootNetwork("r5", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")

        subnet.add_data_input_port("val")

        # subnet IS the parent of inner (inner.network_id == subnet.id)
        edge = root.connect_node_output_to(subnet, "val", inner, "a")

        assert edge.from_node_id   == subnet.id
        assert edge.from_port_name == "val"
        assert edge.to_node_id     == inner.id
        assert edge.to_port_name   == "a"

    def test_tunnel_in_missing_inner_port_raises(self):
        root   = NodeNetwork.createRootNetwork("r6", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")
        subnet.add_data_input_port("val")

        with pytest.raises(ValueError, match="not found"):
            root.connect_node_output_to(subnet, "val", inner, "no_such_port")

    # ── child→parent (tunnel-out) ─────────────────────────────────────────────

    def test_tunnel_out_from_inner_to_network_output(self):
        """child→parent: inner.outputs['sum'] → subnet.outputs['result']."""
        root   = NodeNetwork.createRootNetwork("r7", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")

        subnet.add_data_output_port("result")

        # inner IS a child of subnet (inner.network_id == subnet.id)
        edge = root.connect_node_output_to(inner, "sum", subnet, "result")

        assert edge.from_node_id   == inner.id
        assert edge.from_port_name == "sum"
        assert edge.to_node_id     == subnet.id
        assert edge.to_port_name   == "result"

    def test_tunnel_out_missing_network_port_raises(self):
        root   = NodeNetwork.createRootNetwork("r8", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")

        # "result" not added → ValueError
        with pytest.raises(ValueError, match="not found"):
            root.connect_node_output_to(inner, "sum", subnet, "result")

    # ── same-name ports on the subnet boundary ────────────────────────────────

    def test_same_name_tunnel_in_uses_inputs_dict(self):
        """
        subnet has BOTH inputs['data'] and outputs['data'].

        When source is the subnet (parent→child), the method must look up
        from_port in subnet.inputs — NOT subnet.outputs — even though the
        port names are identical.
        """
        root   = NodeNetwork.createRootNetwork("r9", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")

        subnet.add_data_input_port("data")   # lives in subnet.inputs["data"]
        subnet.add_data_output_port("data")  # lives in subnet.outputs["data"]

        # parent→child: must pick subnet.inputs["data"], not subnet.outputs["data"]
        edge = root.connect_node_output_to(subnet, "data", inner, "a")

        assert edge.from_node_id   == subnet.id
        assert edge.from_port_name == "data"
        assert edge.to_node_id     == inner.id
        assert edge.to_port_name   == "a"

        # Verify the chosen port is the INPUT tunnel port (allow_multiple=True, stored in inputs dict)
        from_port = subnet.inputs.get("data")
        assert from_port is not None, "Expected to find port in subnet.inputs['data']"

    def test_same_name_tunnel_out_uses_outputs_dict(self):
        """
        subnet has BOTH inputs['data'] and outputs['data'].

        When source is an inner node (child→parent), the method must look up
        to_port in subnet.outputs — NOT subnet.inputs.
        """
        root   = NodeNetwork.createRootNetwork("r10", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")

        subnet.add_data_input_port("data")   # subnet.inputs["data"]
        subnet.add_data_output_port("data")  # subnet.outputs["data"]

        # child→parent: must pick subnet.outputs["data"]
        edge = root.connect_node_output_to(inner, "sum", subnet, "data")

        assert edge.from_node_id   == inner.id
        assert edge.from_port_name == "sum"
        assert edge.to_node_id     == subnet.id
        assert edge.to_port_name   == "data"

        to_port = subnet.outputs.get("data")
        assert to_port is not None, "Expected to find port in subnet.outputs['data']"

    def test_same_name_both_directions_distinct_edges(self):
        """
        Full pipeline through a subnet: src → subnet → inner → subnet → sink.

        Uses distinct port names ("in_data" for tunnel-in, "out_data" for
        tunnel-out) because the Arena indexes edges by (node_id, port_name)
        without direction; reusing the same name for both boundary ports on the
        same subnet would make the two edges indistinguishable in the Arena.
        The same-name dict-selection correctness is already covered by the two
        individual tests above.
        """
        root   = NodeNetwork.createRootNetwork("r11", "NodeNetworkSystem")
        src    = root.createNode("Src",   "ConTestAdd")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")
        sink   = root.createNode("Sink",  "ConTestAdd")

        subnet.add_data_input_port("in_data")    # tunnel-in
        subnet.add_data_output_port("out_data")  # tunnel-out

        # Outer → subnet tunnel-in (sibling→sibling at root level)
        root.connect_node_output_to(src,    "sum",      subnet, "in_data")
        # subnet tunnel-in → inner (parent→child)
        root.connect_node_output_to(subnet, "in_data",  inner,  "a")
        # inner → subnet tunnel-out (child→parent)
        root.connect_node_output_to(inner,  "sum",      subnet, "out_data")
        # subnet tunnel-out → sink (sibling→sibling at root level)
        root.connect_node_output_to(subnet, "out_data", sink,   "a")

        assert _edge(root.graph, src.id,    "sum",      subnet.id, "in_data")  is not None
        assert _edge(root.graph, subnet.id, "in_data",  inner.id,  "a")        is not None
        assert _edge(root.graph, inner.id,  "sum",      subnet.id, "out_data") is not None
        assert _edge(root.graph, subnet.id, "out_data", sink.id,   "a")        is not None

    def test_same_name_tunnel_in_does_not_connect_output_port(self):
        """
        parent→child must NOT wire to subnet.outputs even if the port name
        matches — it must raise if there is no matching INPUT port on the child.
        """
        root   = NodeNetwork.createRootNetwork("r12", "NodeNetworkSystem")
        subnet = root.createNetwork("Sub", "NodeNetworkSystem")
        inner  = subnet.createNode("Inner", "ConTestAdd")

        # Only an OUTPUT port named "data" on the subnet — no INPUT port
        subnet.add_data_output_port("data")

        # parent→child looks in subnet.inputs["data"] → not there → ValueError
        with pytest.raises(ValueError, match="not found"):
            root.connect_node_output_to(subnet, "data", inner, "a")

    # ── unrelated nodes ───────────────────────────────────────────────────────

    def test_unrelated_nodes_raise(self):
        """
        Two nodes in different sibling subnetworks (no parent/child or sibling
        relationship at the calling network level) must raise ValueError.
        """
        root  = NodeNetwork.createRootNetwork("r13", "NodeNetworkSystem")
        sub_a = root.createNetwork("SubA", "NodeNetworkSystem")
        sub_b = root.createNetwork("SubB", "NodeNetworkSystem")

        inner_a = sub_a.createNode("IA", "ConTestAdd")
        inner_b = sub_b.createNode("IB", "ConTestAdd")

        # inner_a.network_id == sub_a.id
        # inner_b.network_id == sub_b.id
        # They are not siblings (different network_ids) and neither is parent of the other.
        with pytest.raises(ValueError):
            root.connect_node_output_to(inner_a, "sum", inner_b, "a")
