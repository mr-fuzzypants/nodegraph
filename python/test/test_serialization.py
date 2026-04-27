"""
Serialisation / deserialisation unit tests for:
  - NodePort  (to_dict / from_dict / _serialise_value)
  - Node      (to_dict / from_dict)
  - NodeNetwork (to_dict / from_dict including inner Graph)
"""
import os
import sys
import json
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.Node import Node, PluginRegistry
from nodegraph.python.core.NodeNetwork import NodeNetwork
from nodegraph.python.core.Executor import ExecutionResult, ExecCommand
from nodegraph.python.core.NodePort import (
    NodePort,
    InputDataPort, OutputDataPort,
    InputControlPort, OutputControlPort,
    PORT_TYPE_INPUT, PORT_TYPE_OUTPUT, PORT_TYPE_CONTROL,
)
from nodegraph.python.core.Types import ValueType, PortFunction, PortDirection


# ── Shared test nodes ─────────────────────────────────────────────────────────

@Node.register("SerTestAdd")
class SerTestAdd(Node):
    """Simple add node with one int input and one int output."""
    def __init__(self, name, type="SerTestAdd", network_id=None, **kwargs):
        super().__init__(name, type, network_id=network_id, **kwargs)
        self.inputs["a"]   = InputDataPort(self.id, "a",   ValueType.INT)
        self.inputs["b"]   = InputDataPort(self.id, "b",   ValueType.INT)
        self.outputs["sum"] = OutputDataPort(self.id, "sum", ValueType.INT)

    async def compute(self, executionContext=None):
        return ExecutionResult(ExecCommand.CONTINUE)


@Node.register("SerTestGate")
class SerTestGate(Node):
    """Flow-control node: one control in, two control outs."""
    def __init__(self, name, type="SerTestGate", network_id=None, **kwargs):
        super().__init__(name, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True
        self.inputs["trigger"]  = InputControlPort(self.id, "trigger")
        self.outputs["true"]    = OutputControlPort(self.id, "true")
        self.outputs["false"]   = OutputControlPort(self.id, "false")

    async def compute(self, executionContext=None):
        return ExecutionResult(ExecCommand.CONTINUE)


# ── NodePort tests ────────────────────────────────────────────────────────────

class TestNodePortSerialisation:

    def test_to_dict_shape(self):
        """to_dict produces all required keys."""
        port = InputDataPort("node-1", "value", ValueType.INT)
        d = port.to_dict()

        assert set(d.keys()) == {
            "node_id", "port_id", "port_name", "port_type", "data_type",
            "direction", "function", "value", "is_dirty", "allow_multiple",
            "incoming_connections", "outgoing_connections",
        }

    def test_to_dict_values(self):
        """to_dict captures the correct field values."""
        port = InputDataPort("node-abc", "score", ValueType.FLOAT)
        port.setValue(3.14)
        d = port.to_dict()

        assert d["node_id"]   == "node-abc"
        assert d["port_name"] == "score"
        assert d["value"]     == pytest.approx(3.14)
        assert d["is_dirty"]  is False                      # setValue clears dirty
        assert d["data_type"] == ValueType.FLOAT.value
        assert d["direction"] == PortDirection.INPUT.value
        assert d["function"]  == PortFunction.DATA.value

    def test_to_dict_is_json_serialisable(self):
        """The dict produced by to_dict must survive json.dumps."""
        port = OutputDataPort("n1", "result", ValueType.STRING)
        port.setValue("hello")
        json_str = json.dumps(port.to_dict())
        assert "hello" in json_str

    def test_round_trip_int_port(self):
        """INT port survives to_dict → from_dict with correct value and type."""
        p = InputDataPort("n1", "count", ValueType.INT)
        p.setValue(99)
        d = p.to_dict()

        p2 = NodePort.from_dict(d)
        assert p2.value     == 99
        assert p2.port_name == "count"
        assert p2.data_type == ValueType.INT
        assert p2.direction == PortDirection.INPUT
        assert p2.function  == PortFunction.DATA
        assert p2._isDirty  is False

    def test_round_trip_float_port(self):
        p = OutputDataPort("n2", "weight", ValueType.FLOAT)
        p.setValue(1.5)
        p2 = NodePort.from_dict(p.to_dict())
        assert p2.value == pytest.approx(1.5)

    def test_round_trip_string_port(self):
        p = InputDataPort("n3", "label", ValueType.STRING)
        p.setValue("alpha")
        p2 = NodePort.from_dict(p.to_dict())
        assert p2.value == "alpha"

    def test_round_trip_bool_port(self):
        p = InputDataPort("n4", "flag", ValueType.BOOL)
        p.setValue(True)
        p2 = NodePort.from_dict(p.to_dict())
        assert p2.value is True

    def test_round_trip_control_port(self):
        """Control port preserves function=CONTROL through round-trip."""
        p = InputControlPort("n5", "trigger")
        d = p.to_dict()
        p2 = NodePort.from_dict(d)
        assert p2.function == PortFunction.CONTROL
        assert p2.isControlPort() is True

    def test_round_trip_output_port_direction(self):
        p = OutputDataPort("n6", "out", ValueType.INT)
        p.setValue(7)
        p2 = NodePort.from_dict(p.to_dict())
        assert p2.direction == PortDirection.OUTPUT
        assert p2.isOutputPort() is True

    def test_round_trip_tunnel_port(self):
        """Tunnel (allow_multiple) port preserves allow_multiple=True after round-trip."""
        p = InputDataPort("n7", "tunnel", ValueType.ANY)
        p.allow_multiple = True
        d = p.to_dict()
        p2 = NodePort.from_dict(d)
        assert p2.direction == PortDirection.INPUT
        assert p2.allow_multiple is True

    def test_dirty_flag_preserved(self):
        """is_dirty=True is round-tripped correctly."""
        p = InputDataPort("n8", "x", ValueType.INT)
        # Default — dirty, value not set
        assert p._isDirty is True
        p2 = NodePort.from_dict(p.to_dict())
        assert p2._isDirty is True

    def test_connections_round_trip(self):
        """incoming_connections list is preserved."""
        p = InputDataPort("n9", "v", ValueType.INT)
        p.incoming_connections = ["edge-1", "edge-2"]
        p2 = NodePort.from_dict(p.to_dict())
        assert p2.incoming_connections == ["edge-1", "edge-2"]

    def test_null_value_round_trip(self):
        """None value (ANY port, no value set) round-trips to None."""
        p = InputDataPort("n10", "opt", ValueType.ANY)
        d = p.to_dict()
        p2 = NodePort.from_dict(d)
        # ANY default is None
        assert p2.value is None

    def test_serialise_value_passthrough_primitives(self):
        p = InputDataPort("x", "v", ValueType.ANY)
        for v in (1, 3.14, "txt", True, None, [1, 2], {"k": "v"}):
            assert p._serialise_value(v) == v

    def test_serialise_value_non_json_becomes_string(self):
        """Non-JSON-safe objects are converted to str."""
        p = InputDataPort("x", "v", ValueType.ANY)
        assert p._serialise_value(ValueType.INT) == str(ValueType.INT)


# ── Node tests ────────────────────────────────────────────────────────────────

class TestNodeSerialisation:

    def setup_method(self):
        NodeNetwork.deleteAllNodes()

    def test_to_dict_shape(self):
        """to_dict contains all required top-level keys."""
        net = NodeNetwork.createRootNetwork("net_ser", "NodeNetworkSystem")
        node = net.createNode("Add1", "SerTestAdd")
        d = node.to_dict()

        assert "id"                   in d
        assert "name"                 in d
        assert "type"                 in d
        assert "kind"                 in d
        assert "network_id"           in d
        assert "is_flow_control_node" in d
        assert "inputs"               in d
        assert "outputs"              in d

    def test_to_dict_identity(self):
        net = NodeNetwork.createRootNetwork("net_id", "NodeNetworkSystem")
        node = net.createNode("Adder", "SerTestAdd")
        d = node.to_dict()

        assert d["id"]   == node.id
        assert d["name"] == "Adder"
        assert d["type"] == "SerTestAdd"

    def test_to_dict_ports_serialised(self):
        """All ports appear in the dict with correct metadata."""
        net = NodeNetwork.createRootNetwork("net_ports", "NodeNetworkSystem")
        node = net.createNode("A", "SerTestAdd")
        node.inputs["a"].setValue(3)
        node.inputs["b"].setValue(5)
        d = node.to_dict()

        assert "a"   in d["inputs"]
        assert "b"   in d["inputs"]
        assert "sum" in d["outputs"]
        assert d["inputs"]["a"]["value"]  == 3
        assert d["inputs"]["b"]["value"]  == 5

    def test_to_dict_is_json_serialisable(self):
        net = NodeNetwork.createRootNetwork("net_json", "NodeNetworkSystem")
        node = net.createNode("A", "SerTestAdd")
        node.inputs["a"].setValue(10)
        json.dumps(node.to_dict())                  # must not raise

    def test_from_dict_restores_id(self):
        """from_dict patches the id to the saved value."""
        net = NodeNetwork.createRootNetwork("net_fdict", "NodeNetworkSystem")
        orig = net.createNode("X", "SerTestAdd")
        orig.inputs["a"].setValue(7)
        d = orig.to_dict()

        NodeNetwork.deleteAllNodes()
        net2 = NodeNetwork.createRootNetwork("net_fdict2", "NodeNetworkSystem")
        restored = Node.from_dict(d)
        assert restored.id   == orig.id
        assert restored.name == "X"
        assert restored.type == "SerTestAdd"

    def test_from_dict_restores_port_values(self):
        """from_dict patches saved values back into ports."""
        net = NodeNetwork.createRootNetwork("net_pv", "NodeNetworkSystem")
        orig = net.createNode("Y", "SerTestAdd")
        orig.inputs["a"].setValue(11)
        orig.inputs["b"].setValue(22)
        d = orig.to_dict()

        NodeNetwork.deleteAllNodes()
        NodeNetwork.createRootNetwork("net_pv2", "NodeNetworkSystem")
        restored = Node.from_dict(d)
        assert restored.inputs["a"].value == 11
        assert restored.inputs["b"].value == 22

    def test_from_dict_control_node_flag(self):
        """is_flow_control_node is preserved through to_dict."""
        net = NodeNetwork.createRootNetwork("net_ctrl", "NodeNetworkSystem")
        gate = net.createNode("G", "SerTestGate")
        d = gate.to_dict()
        assert d["is_flow_control_node"] is True

    def test_round_trip_multiple_ports(self):
        net = NodeNetwork.createRootNetwork("net_mp", "NodeNetworkSystem")
        orig = net.createNode("Z", "SerTestAdd")
        orig.inputs["a"].setValue(3)
        orig.inputs["b"].setValue(4)
        d = orig.to_dict()

        NodeNetwork.deleteAllNodes()
        NodeNetwork.createRootNetwork("net_mp2", "NodeNetworkSystem")
        restored = Node.from_dict(d)

        assert restored.inputs["a"].value == 3
        assert restored.inputs["b"].value == 4
        assert "sum" in restored.outputs


# ── NodeNetwork tests ─────────────────────────────────────────────────────────

class TestNodeNetworkSerialisation:

    def setup_method(self):
        NodeNetwork.deleteAllNodes()

    def test_to_dict_has_graph_key(self):
        """to_dict includes a 'graph' section with nodes and edges lists."""
        net = NodeNetwork.createRootNetwork("net_g", "NodeNetworkSystem")
        net.createNode("A", "SerTestAdd")
        d = net.to_dict()

        assert "graph" in d
        assert "nodes" in d["graph"]
        assert "edges" in d["graph"]

    def test_to_dict_inner_nodes_included(self):
        net = NodeNetwork.createRootNetwork("net_in", "NodeNetworkSystem")
        a = net.createNode("A", "SerTestAdd")
        b = net.createNode("B", "SerTestAdd")
        d = net.to_dict()

        assert a.id in d["graph"]["nodes"]
        assert b.id in d["graph"]["nodes"]

    def test_to_dict_edges_included(self):
        net = NodeNetwork.createRootNetwork("net_edges", "NodeNetworkSystem")
        net.createNode("A", "SerTestAdd")
        net.createNode("B", "SerTestAdd")
        net.connectNodes("A", "sum", "B", "a")
        d = net.to_dict()

        assert len(d["graph"]["edges"]) == 1
        edge = d["graph"]["edges"][0]
        assert edge["from_port_name"] == "sum"
        assert edge["to_port_name"]   == "a"

    def test_to_dict_multiple_edges(self):
        net = NodeNetwork.createRootNetwork("net_me", "NodeNetworkSystem")
        net.createNode("A", "SerTestAdd")
        net.createNode("B", "SerTestAdd")
        net.createNode("C", "SerTestAdd")
        net.connectNodes("A", "sum", "B", "a")
        net.connectNodes("B", "sum", "C", "a")
        d = net.to_dict()
        assert len(d["graph"]["edges"]) == 2

    def test_to_dict_is_json_serialisable(self):
        net = NodeNetwork.createRootNetwork("net_jser", "NodeNetworkSystem")
        a = net.createNode("A", "SerTestAdd")
        b = net.createNode("B", "SerTestAdd")
        net.connectNodes("A", "sum", "B", "a")
        a.inputs["a"].setValue(1)
        json.dumps(net.to_dict())                   # must not raise

    def test_from_dict_restores_nodes(self):
        net = NodeNetwork.createRootNetwork("net_rn", "NodeNetworkSystem")
        a = net.createNode("Alpha", "SerTestAdd")
        b = net.createNode("Beta",  "SerTestAdd")
        a.inputs["a"].setValue(5)
        d = net.to_dict()

        NodeNetwork.deleteAllNodes()
        restored_net = NodeNetwork.from_dict(d)

        assert a.id in restored_net.graph.nodes
        assert b.id in restored_net.graph.nodes

    def test_from_dict_restores_port_values(self):
        net = NodeNetwork.createRootNetwork("net_rpv", "NodeNetworkSystem")
        a = net.createNode("A", "SerTestAdd")
        a.inputs["a"].setValue(42)
        a.inputs["b"].setValue(58)
        d = net.to_dict()

        NodeNetwork.deleteAllNodes()
        restored = NodeNetwork.from_dict(d)
        ra = restored.graph.nodes[a.id]
        assert ra.inputs["a"].value == 42
        assert ra.inputs["b"].value == 58

    def test_from_dict_restores_edges(self):
        net = NodeNetwork.createRootNetwork("net_re", "NodeNetworkSystem")
        a = net.createNode("A", "SerTestAdd")
        b = net.createNode("B", "SerTestAdd")
        net.connectNodes("A", "sum", "B", "a")
        d = net.to_dict()

        NodeNetwork.deleteAllNodes()
        restored = NodeNetwork.from_dict(d)

        incoming = restored.graph.get_incoming_edges(b.id, "a")
        assert len(incoming) == 1
        assert incoming[0].from_node_id   == a.id
        assert incoming[0].from_port_name == "sum"

    def test_from_dict_restores_network_id(self):
        net = NodeNetwork.createRootNetwork("net_nid", "NodeNetworkSystem")
        d = net.to_dict()
        NodeNetwork.deleteAllNodes()
        restored = NodeNetwork.from_dict(d)
        assert restored.id == net.id

    def test_round_trip_empty_network(self):
        """An empty network round-trips without error."""
        net = NodeNetwork.createRootNetwork("net_empty", "NodeNetworkSystem")
        d = net.to_dict()
        NodeNetwork.deleteAllNodes()
        restored = NodeNetwork.from_dict(d)
        assert len(restored.graph.nodes) == 0
        assert len(restored.graph.edges) == 0

    def test_round_trip_full_pipeline(self):
        """Three-node pipeline: port values and two edges survive round-trip."""
        net = NodeNetwork.createRootNetwork("net_pipe", "NodeNetworkSystem")
        a = net.createNode("In",  "SerTestAdd")
        b = net.createNode("Mid", "SerTestAdd")
        c = net.createNode("Out", "SerTestAdd")
        a.inputs["a"].setValue(10)
        a.inputs["b"].setValue(20)
        net.connectNodes("In",  "sum", "Mid", "a")
        net.connectNodes("Mid", "sum", "Out", "a")
        d = net.to_dict()

        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        ra = r.graph.nodes[a.id]
        assert ra.inputs["a"].value == 10
        assert ra.inputs["b"].value == 20

        # Both edges restored
        assert len(r.graph.edges) == 2
        from_ids = {e.from_node_id for e in r.graph.edges}
        assert a.id in from_ids
        assert b.id in from_ids


# ── Nested Subnetwork tests ───────────────────────────────────────────────────

class TestNestedSubnetworkSerialisation:
    """
    Exercises deeply nested and parallel subnetwork topologies.

    Default topology used by _build_topology():

        root
        ├── preamble  (SerTestAdd)  a=10, b=5
        ├── ScaleSub  (NodeNetworkSystem)  [tunnel-in: "val", tunnel-out: "result"]
        │   ├── doubler  (SerTestAdd)   a ← val, b ← val
        │   └── adder    (SerTestAdd)   a ← doubler.sum
        │                               sum → ScaleSub."result"
        └── collector (SerTestAdd)  a ← ScaleSub."result"

    Outer edges  (stored in shared root.graph arena):
        preamble.sum   → ScaleSub.val
        ScaleSub.result → collector.a

    Inner edges  (also in the shared arena but filtered to ScaleSub's scope):
        ScaleSub.val   → doubler.a
        ScaleSub.val   → doubler.b
        doubler.sum    → adder.a
        adder.sum      → ScaleSub.result
    """

    def setup_method(self):
        NodeNetwork.deleteAllNodes()

    # ── topology builder ──────────────────────────────────────────────────────

    def _build_topology(self):
        root      = NodeNetwork.createRootNetwork("root", "NodeNetworkSystem")
        preamble  = root.createNode("preamble",  "SerTestAdd")
        subnet    = root.createNetwork("ScaleSub", "NodeNetworkSystem")
        collector = root.createNode("collector", "SerTestAdd")

        subnet.add_data_input_port("val")
        subnet.add_data_output_port("result")

        doubler = subnet.createNode("doubler", "SerTestAdd")
        adder   = subnet.createNode("adder",   "SerTestAdd")

        preamble.inputs["a"].setValue(10)
        preamble.inputs["b"].setValue(5)

        # All edges go into the single shared arena (root.graph).
        # Outer connections
        root.graph.add_edge(preamble.id,  "sum",    subnet.id,    "val")
        root.graph.add_edge(subnet.id,    "result", collector.id, "a")
        # Tunnel input → inner nodes
        root.graph.add_edge(subnet.id, "val", doubler.id, "a")
        root.graph.add_edge(subnet.id, "val", doubler.id, "b")
        # Inner pipeline
        root.graph.add_edge(doubler.id, "sum", adder.id,  "a")
        # Inner node → tunnel output
        root.graph.add_edge(adder.id,   "sum", subnet.id, "result")

        return root, preamble, subnet, doubler, adder, collector

    # ── to_dict structure tests ───────────────────────────────────────────────

    def test_subnet_appears_in_root_dict(self):
        """Subnet and outer sibling nodes appear at the top level of root's graph."""
        root, preamble, subnet, _, _, collector = self._build_topology()
        d = root.to_dict()
        assert subnet.id    in d["graph"]["nodes"]
        assert preamble.id  in d["graph"]["nodes"]
        assert collector.id in d["graph"]["nodes"]

    def test_inner_nodes_not_in_root_dict(self):
        """Inner nodes (network_id == subnet) must NOT appear flat inside root's node dict."""
        root, _, subnet, doubler, adder, _ = self._build_topology()
        d = root.to_dict()
        assert doubler.id not in d["graph"]["nodes"]
        assert adder.id   not in d["graph"]["nodes"]

    def test_inner_nodes_appear_in_subnet_dict(self):
        """Both inner nodes appear under the subnet's own graph.nodes."""
        root, _, subnet, doubler, adder, _ = self._build_topology()
        d = root.to_dict()
        subnet_d = d["graph"]["nodes"][subnet.id]
        assert doubler.id in subnet_d["graph"]["nodes"]
        assert adder.id   in subnet_d["graph"]["nodes"]

    def test_tunnel_ports_in_subnet_dict(self):
        """Tunnel input/output ports survive into the serialised subnet."""
        root, _, subnet, _, _, _ = self._build_topology()
        d          = root.to_dict()
        subnet_d   = d["graph"]["nodes"][subnet.id]
        assert "val"    in subnet_d["inputs"]
        assert "result" in subnet_d["outputs"]

    def test_outer_edges_in_root_dict(self):
        """Edges between outer nodes and the subnet boundary appear in root-level edges."""
        root, preamble, subnet, _, _, collector = self._build_topology()
        d     = root.to_dict()
        pairs = {
            (e["from_node_id"], e["from_port_name"],
             e["to_node_id"],   e["to_port_name"])
            for e in d["graph"]["edges"]
        }
        assert (preamble.id, "sum",    subnet.id,    "val")    in pairs
        assert (subnet.id,   "result", collector.id, "a")      in pairs

    def test_inner_edges_in_subnet_dict(self):
        """All inner edges—including tunnel→inner and inner→tunnel—appear in subnet's graph."""
        root, _, subnet, doubler, adder, _ = self._build_topology()
        d        = root.to_dict()
        subnet_d = d["graph"]["nodes"][subnet.id]
        pairs = {
            (e["from_node_id"], e["from_port_name"],
             e["to_node_id"],   e["to_port_name"])
            for e in subnet_d["graph"]["edges"]
        }
        # tunnel input → inner nodes
        assert (subnet.id, "val", doubler.id, "a") in pairs
        assert (subnet.id, "val", doubler.id, "b") in pairs
        # inner pipeline
        assert (doubler.id, "sum", adder.id,   "a")      in pairs
        # inner → tunnel output
        assert (adder.id,   "sum", subnet.id, "result")  in pairs

    def test_outer_edges_not_in_subnet_dict(self):
        """Outer nodes (preamble, collector) must not leak into subnet's edge list."""
        root, preamble, subnet, _, _, collector = self._build_topology()
        d        = root.to_dict()
        subnet_d = d["graph"]["nodes"][subnet.id]
        outer_ids = {preamble.id, collector.id}
        for e in subnet_d["graph"]["edges"]:
            assert e["from_node_id"] not in outer_ids, \
                f"Outer source {e['from_node_id']} leaked into subnet edge dict"
            assert e["to_node_id"] not in outer_ids, \
                f"Outer target {e['to_node_id']} leaked into subnet edge dict"

    def test_inner_edges_not_in_root_dict(self):
        """Inner edges (both endpoints inside subnet) must not appear in root's edge list."""
        root, _, subnet, doubler, adder, _ = self._build_topology()
        d = root.to_dict()
        inner_ids = {doubler.id, adder.id}
        for e in d["graph"]["edges"]:
            assert not (e["from_node_id"] in inner_ids or e["to_node_id"] in inner_ids), \
                f"Inner edge leaked into root edge list: {e}"

    def test_full_nested_dict_is_json_serialisable(self):
        root, *_ = self._build_topology()
        json.dumps(root.to_dict())   # must not raise

    # ── round-trip tests ──────────────────────────────────────────────────────

    def test_round_trip_root_nodes_present(self):
        """After from_dict, root graph contains preamble, subnet, and collector."""
        root, preamble, subnet, _, _, collector = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        assert preamble.id  in r.graph.nodes
        assert subnet.id    in r.graph.nodes
        assert collector.id in r.graph.nodes

    def test_round_trip_subnet_is_nodenetwork(self):
        """The restored subnet node is a NodeNetwork instance (not a plain Node)."""
        root, _, subnet, _, _, _ = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        assert isinstance(r.graph.nodes[subnet.id], NodeNetwork)

    def test_round_trip_inner_nodes_in_subnet(self):
        """Both inner nodes exist inside the restored subnet's graph."""
        root, _, subnet, doubler, adder, _ = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r        = NodeNetwork.from_dict(d)
        r_subnet = r.graph.nodes[subnet.id]

        assert doubler.id in r_subnet.graph.nodes
        assert adder.id   in r_subnet.graph.nodes

    def test_round_trip_outer_port_values(self):
        """Port values on outer nodes survive round-trip."""
        root, preamble, _, _, _, _ = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r          = NodeNetwork.from_dict(d)
        r_preamble = r.graph.nodes[preamble.id]

        assert r_preamble.inputs["a"].value == 10
        assert r_preamble.inputs["b"].value == 5

    def test_round_trip_outer_edges(self):
        """preamble→subnet and subnet→collector edges survive round-trip."""
        root, preamble, subnet, _, _, collector = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        out_edges = r.graph.get_outgoing_edges(preamble.id, "sum")
        assert len(out_edges) == 1
        assert out_edges[0].to_node_id   == subnet.id
        assert out_edges[0].to_port_name == "val"

        in_edges = r.graph.get_incoming_edges(collector.id, "a")
        assert len(in_edges) == 1
        assert in_edges[0].from_node_id   == subnet.id
        assert in_edges[0].from_port_name == "result"

    def test_round_trip_inner_pipeline_edge(self):
        """doubler.sum → adder.a edge survives round-trip inside the subnet."""
        root, _, subnet, doubler, adder, _ = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r        = NodeNetwork.from_dict(d)
        r_subnet = r.graph.nodes[subnet.id]

        mid_edges = r_subnet.graph.get_outgoing_edges(doubler.id, "sum")
        assert len(mid_edges) == 1
        assert mid_edges[0].to_node_id   == adder.id
        assert mid_edges[0].to_port_name == "a"

    def test_round_trip_tunnel_in_edges(self):
        """subnet.val → doubler.a and subnet.val → doubler.b edges survive."""
        root, _, subnet, doubler, _, _ = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r        = NodeNetwork.from_dict(d)
        r_subnet = r.graph.nodes[subnet.id]

        tun_edges = r_subnet.graph.get_outgoing_edges(subnet.id, "val")
        to_ports  = {(e.to_node_id, e.to_port_name) for e in tun_edges}
        assert (doubler.id, "a") in to_ports
        assert (doubler.id, "b") in to_ports

    def test_round_trip_tunnel_out_edge(self):
        """adder.sum → subnet.result edge survives round-trip."""
        root, _, subnet, _, adder, _ = self._build_topology()
        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r        = NodeNetwork.from_dict(d)
        r_subnet = r.graph.nodes[subnet.id]

        out_edges = r_subnet.graph.get_outgoing_edges(adder.id, "sum")
        assert len(out_edges) == 1
        assert out_edges[0].to_node_id   == subnet.id
        assert out_edges[0].to_port_name == "result"

    # ── deep nesting (3 levels) ───────────────────────────────────────────────

    def test_three_level_nesting_to_dict(self):
        """root → Sub1 → Sub2 → leaf: each level serialised at the correct depth."""
        root = NodeNetwork.createRootNetwork("root3", "NodeNetworkSystem")
        sub1 = root.createNetwork("Sub1", "NodeNetworkSystem")
        sub2 = sub1.createNetwork("Sub2", "NodeNetworkSystem")
        leaf = sub2.createNode("Leaf", "SerTestAdd")
        leaf.inputs["a"].setValue(7)

        d = root.to_dict()

        # Level 1: only sub1 at root depth
        assert sub1.id in  d["graph"]["nodes"]
        assert sub2.id not in d["graph"]["nodes"]
        assert leaf.id not in d["graph"]["nodes"]

        # Level 2: sub2 inside sub1, leaf NOT at sub1 depth
        sub1_d = d["graph"]["nodes"][sub1.id]
        assert sub2.id in  sub1_d["graph"]["nodes"]
        assert leaf.id not in sub1_d["graph"]["nodes"]

        # Level 3: leaf inside sub2 with correct value
        sub2_d = sub1_d["graph"]["nodes"][sub2.id]
        assert leaf.id in sub2_d["graph"]["nodes"]
        assert sub2_d["graph"]["nodes"][leaf.id]["inputs"]["a"]["value"] == 7

    def test_three_level_nesting_round_trip(self):
        """Full 3-level round-trip: root → Sub1 → Sub2 → leaf."""
        root = NodeNetwork.createRootNetwork("root3rt", "NodeNetworkSystem")
        sub1 = root.createNetwork("Sub1", "NodeNetworkSystem")
        sub2 = sub1.createNetwork("Sub2", "NodeNetworkSystem")
        leaf = sub2.createNode("Leaf", "SerTestAdd")
        leaf.inputs["a"].setValue(42)

        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        r_sub1 = r.graph.nodes[sub1.id]
        assert isinstance(r_sub1, NodeNetwork)

        r_sub2 = r_sub1.graph.nodes[sub2.id]
        assert isinstance(r_sub2, NodeNetwork)

        r_leaf = r_sub2.graph.nodes[leaf.id]
        assert r_leaf.inputs["a"].value == 42

    def test_three_level_with_cross_level_edges(self):
        """Edges from root nodes through sub1 tunnel into sub2's inner nodes."""
        root    = NodeNetwork.createRootNetwork("root3e", "NodeNetworkSystem")
        src     = root.createNode("Src", "SerTestAdd")
        sub1    = root.createNetwork("Sub1", "NodeNetworkSystem")
        sub2    = sub1.createNetwork("Sub2", "NodeNetworkSystem")
        deep_n  = sub2.createNode("DeepNode", "SerTestAdd")

        sub1.add_data_input_port("pin")
        sub2.add_data_input_port("pin")

        src.inputs["a"].setValue(99)

        # Outer → sub1 tunnel
        root.graph.add_edge(src.id,   "sum", sub1.id,   "pin")
        # sub1 tunnel → sub2 tunnel (cross-subnet connection stored in arena)
        root.graph.add_edge(sub1.id,  "pin", sub2.id,   "pin")
        # sub2 tunnel → deep inner node
        root.graph.add_edge(sub2.id,  "pin", deep_n.id, "a")

        d = root.to_dict()

        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        r_sub1   = r.graph.nodes[sub1.id]
        r_sub2   = r_sub1.graph.nodes[sub2.id]
        r_deep   = r_sub2.graph.nodes[deep_n.id]

        assert r_deep.inputs["a"] is not None   # port exists

        # Edge: src → sub1 is in root
        root_out = r.graph.get_outgoing_edges(src.id, "sum")
        assert any(e.to_node_id == sub1.id for e in root_out)

        # Edge: sub1.pin → sub2.pin is in sub1's graph
        sub1_out = r_sub1.graph.get_outgoing_edges(sub1.id, "pin")
        assert any(e.to_node_id == sub2.id for e in sub1_out)

        # Edge: sub2.pin → deep_n.a is in sub2's graph
        sub2_out = r_sub2.graph.get_outgoing_edges(sub2.id, "pin")
        assert any(e.to_node_id == deep_n.id for e in sub2_out)

    # ── parallel subnets ──────────────────────────────────────────────────────

    def test_parallel_subnets_isolated_nodes(self):
        """Two sibling subnets each serialise only their own inner nodes."""
        root  = NodeNetwork.createRootNetwork("rootPar", "NodeNetworkSystem")
        sub_a = root.createNetwork("SubA", "NodeNetworkSystem")
        sub_b = root.createNetwork("SubB", "NodeNetworkSystem")

        inner_x = sub_a.createNode("X", "SerTestAdd")
        inner_y = sub_b.createNode("Y", "SerTestAdd")
        inner_x.inputs["a"].setValue(11)
        inner_y.inputs["a"].setValue(22)

        d     = root.to_dict()
        sub_a_d = d["graph"]["nodes"][sub_a.id]
        sub_b_d = d["graph"]["nodes"][sub_b.id]

        assert inner_x.id     in sub_a_d["graph"]["nodes"]
        assert inner_y.id not in sub_a_d["graph"]["nodes"]

        assert inner_y.id     in sub_b_d["graph"]["nodes"]
        assert inner_x.id not in sub_b_d["graph"]["nodes"]

    def test_parallel_subnets_isolated_edges(self):
        """Edges inside SubA do not appear in SubB's serialised edge list."""
        root  = NodeNetwork.createRootNetwork("rootParE", "NodeNetworkSystem")
        sub_a = root.createNetwork("SubA", "NodeNetworkSystem")
        sub_b = root.createNetwork("SubB", "NodeNetworkSystem")

        sub_a.add_data_input_port("in")
        sub_b.add_data_input_port("in")

        inner_x = sub_a.createNode("X", "SerTestAdd")
        inner_y = sub_b.createNode("Y", "SerTestAdd")

        root.graph.add_edge(sub_a.id, "in", inner_x.id, "a")
        root.graph.add_edge(sub_b.id, "in", inner_y.id, "a")

        d       = root.to_dict()
        sub_b_d = d["graph"]["nodes"][sub_b.id]

        # inner_x is in SubA, must never show up in SubB's edges
        for e in sub_b_d["graph"]["edges"]:
            assert e["from_node_id"] != inner_x.id
            assert e["to_node_id"]   != inner_x.id

    def test_parallel_subnets_round_trip(self):
        """Full round-trip: two sibling subnets with inner port values preserved."""
        root  = NodeNetwork.createRootNetwork("rootParRT", "NodeNetworkSystem")
        sub_a = root.createNetwork("SubA", "NodeNetworkSystem")
        sub_b = root.createNetwork("SubB", "NodeNetworkSystem")

        inner_x = sub_a.createNode("X", "SerTestAdd")
        inner_y = sub_b.createNode("Y", "SerTestAdd")
        inner_x.inputs["a"].setValue(33)
        inner_y.inputs["a"].setValue(44)

        d = root.to_dict()
        NodeNetwork.deleteAllNodes()
        r = NodeNetwork.from_dict(d)

        r_sub_a = r.graph.nodes[sub_a.id]
        r_sub_b = r.graph.nodes[sub_b.id]

        assert inner_x.id in r_sub_a.graph.nodes
        assert inner_y.id in r_sub_b.graph.nodes

        assert r_sub_a.graph.nodes[inner_x.id].inputs["a"].value == 33
        assert r_sub_b.graph.nodes[inner_y.id].inputs["a"].value == 44
