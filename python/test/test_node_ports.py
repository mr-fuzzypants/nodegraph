import os
import sys
import logging
import pytest
from typing import List, Optional
import uuid

# Adjust path to find modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from nodegraph.python.core.NodePort import (
    NodePort, 
    DataPort, 
    ControlPort, 
    ValueType, 
    PortDirection, 
    PortFunction
)
from nodegraph.python.core.GraphPrimitives import Edge

# Mock Network to simulate NodeNetwork dependency
class MockNetwork:
    def __init__(self):
        self.nodes = {}  # element_id -> node
        self.edges: List[Edge] = []

    def add_node(self, node):
        self.nodes[node.id] = node
        node.network = self

    def get_node(self, node_id):
        return self.nodes.get(node_id)

    def add_edge(self, from_id, from_port, to_id, to_port):
        # Allow creating duplicate edges for this mock or check? 
        # The real network might check, but basic list append is fine for now
        edge = Edge(from_id, from_port, to_id, to_port)
        self.edges.append(edge)

    def get_outgoing_edges(self, node_id, port_name):
        return [e for e in self.edges if e.from_node_id == node_id and e.from_port_name == port_name]

    def get_incoming_edges(self, node_id, port_name):
        return [e for e in self.edges if e.to_node_id == node_id and e.to_port_name == port_name]

# Mock Node class for testing
class MockNode:
    def __init__(self, name, network=None):

        self.name = name
        self.id = uuid.uuid4().hex
        self.network = network
        self._isDirty = True
        self.inputs = {}
        self.outputs = {}
        
        if network:
            network.add_node(self)
    
    def markDirty(self):
        self._isDirty = True

    def isDirty(self):
        return self._isDirty
    
    def isDataNode(self):
        return True # Mock assumption
    
    # Helper to register ports so lookup logic works
    def register_port(self, port: NodePort):
        if port.direction == PortDirection.INPUT:
            self.inputs[port.port_name] = port
        elif port.direction == PortDirection.OUTPUT:
            self.outputs[port.port_name] = port
        elif port.direction == PortDirection.INPUT_OUTPUT:
             # Basic handling, maybe add to both?
             self.inputs[port.port_name] = port
             self.outputs[port.port_name] = port

class TestNodePort:

    def setup_method(self):
        # Stub: Setup logic here
        pass

    def teardown_method(self):
        # Stub: Cleanup logic here
        pass

    @pytest.fixture
    def mock_network(self):
        return MockNetwork()

    @pytest.fixture
    def mock_node(self, mock_network):
        node = MockNode("test_node", mock_network)
        return node

    def test_init_defaults(self, mock_node):
        """Test basic initialization of NodePort"""
        port = NodePort(mock_node, "test_port", 1)  # 1 = PORT_TYPE_INPUT
        
        assert port.node == mock_node
        assert port.port_name == "test_port"
        assert port.data_type == ValueType.ANY
        assert port.direction == PortDirection.INPUT
        assert port.function == PortFunction.DATA
        assert port.isDirty() is True

    def test_init_control_port(self, mock_node):
        """Test initialization of a Control Port"""
        # 0x80 | 1 = Control Input
        port = NodePort(mock_node, "exec", 0x81, is_control=True)
        
        assert port.function == PortFunction.CONTROL
        assert port.isControlPort() is True
        assert port.isDataPort() is False

    def test_dirty_flag(self, mock_node):
        """Test markDirty and markClean methods"""
        port = NodePort(mock_node, "dirty_port", 1)
        
        port.markClean()
        assert port.isDirty() is False
        
        port.markDirty()
        assert port.isDirty() is True

    def test_set_value_updates_dirty_flag(self, mock_node):
        """Test that setValue marks the port as clean"""
        port = NodePort(mock_node, "val_port", 1)
        # Assuming DataPort/NodePort behaves this way
        port.setValue(100)
        
        assert port.getValue() == 100
        assert port.isDirty() is False

    def test_set_value_propagates_dirty(self, mock_network):
        """Test that setting an output value marks connected inputs as dirty"""
        node_a = MockNode("A", mock_network)
        node_b = MockNode("B", mock_network)
        
        # 2 = Output, 1 = Input
        out_port = NodePort(node_a, "out", 2) 
        node_a.register_port(out_port)
        
        in_port = NodePort(node_b, "in", 1)
        node_b.register_port(in_port)
        
        # Connect via API
        out_port.connectTo(in_port)
        
        # Verify initial state
        in_port.markClean()
        node_b._isDirty = False
        assert in_port.isDirty() is False
        
        # Action: Set value on output
        out_port.setValue(50)
        
        # Expectation: Connected input should now be dirty
        assert in_port.isDirty() is True
        assert node_b.isDirty() is True 

    def test_value_type_validation_warning(self, caplog, mock_node):
        """Test that validation logic is triggered (logs error)"""
        # Ensure we capture logs at ERROR/WARNING level
        import logging
        caplog.set_level(logging.WARNING)

        port = NodePort(mock_node, "int_port", 1, data_type=ValueType.INT)
        
        # Pass a string to an INT port
        # This triggers logger.warning in setValue (updated from error in some versions?)
        port.setValue("not an int")
        
        # Check logs for the error message
        assert "expected ValueType.INT" in caplog.text

    def test_connect_to_basic(self, mock_network):
        """Test the connectTo method establishing bi-directional link via network edges"""
        node_a = MockNode("A", mock_network)
        node_b = MockNode("B", mock_network)
        
        port_a = NodePort(node_a, "out", 2, data_type=ValueType.INT)
        node_a.register_port(port_a)
        
        port_b = NodePort(node_b, "in", 1, data_type=ValueType.INT)
        node_b.register_port(port_b)
        
        port_a.connectTo(port_b)
        
        # Check network edges
        assert len(mock_network.edges) == 1
        edge = mock_network.edges[0]
        assert mock_network.nodes[edge.from_node_id].name == "A"
        assert edge.from_port_name == "out"
        assert mock_network.nodes[edge.to_node_id].name == "B"
        assert edge.to_port_name == "in"

    def test_connect_to_type_mismatch(self, mock_network):
        """Test that connecting incompatible types raises an error"""
        node_a = MockNode("A", mock_network)
        node_b = MockNode("B", mock_network)
        
        port_a = NodePort(node_a, "out", 2, data_type=ValueType.INT)
        port_b = NodePort(node_b, "in", 1, data_type=ValueType.STRING)
        
        with pytest.raises(ValueError, match="Type Mismatch"):
            port_a.connectTo(port_b)

    def test_control_port_activation(self, mock_network):
        """Test ControlPort specific activation logic"""
        node_a = MockNode("A", mock_network)
        node_b = MockNode("B", mock_network)

        # Create Control Output
        cp_out = ControlPort(node_a, "c_out", 2)
        node_a.register_port(cp_out)
        
        # Create Control Input on another node
        cp_in = ControlPort(node_b, "c_in", 1)
        node_b.register_port(cp_in)
        
        cp_out.connectTo(cp_in)
        
        # Activate
        cp_out.activate()
        
        assert cp_out.isActive() is True
        
        # Deactivate
        cp_out.deactivate()
        assert cp_out.isActive() is False

    def test_get_source(self, mock_network):
        """Test get_source retrieves the correct upstream port"""
        node_a = MockNode("A", mock_network)
        node_b = MockNode("B", mock_network)
        
        out_port = NodePort(node_a, "out", 2)
        node_a.register_port(out_port)
        
        in_port = NodePort(node_b, "in", 1)
        node_b.register_port(in_port)
        
        out_port.connectTo(in_port)
        
        source = in_port.get_source()
        assert source == out_port

class TestValueTypeable:

    def setup_method(self):
        # Stub: Setup logic here
        pass

    def teardown_method(self):
        # Stub: Cleanup logic here
        pass

    def test_int_validation(self):
        assert ValueType.validate(10, ValueType.INT) is True
        assert ValueType.validate("10", ValueType.INT) is False
        
    def test_any_validation(self):
        assert ValueType.validate("foo", ValueType.ANY) is True
        assert ValueType.validate(123, ValueType.ANY) is True
