import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

import pytest
from nodegraph.python.core.Node import Node
from nodegraph.python.core.NodePort import DataPort, ControlPort
from nodegraph.python.core.Types import ValueType


from nodegraph.python.core.Node import Node, ExecCommand, ExecutionResult

    
@Node.register("MockNodeOne")
class MockNodeOne(Node):
    def __init__(self, name, type="MockNode", network=None, **kwargs):
        super().__init__(name, type, network=network, **kwargs)
        
    async def compute(self):
        return ExecutionResult(ExecCommand.CONTINUE, [])



class TestNode:

    def setup_method(self):
        # Stub: Setup logic here
        pass

    def teardown_method(self):
        # Stub: Cleanup logic here
        pass

    @pytest.fixture
    def node(self):
        """Fixture to create a basic Node instance for testing."""
        return MockNodeOne(name="test_node_1", type="TestType")

  

    def test_node_initialization(self, node):
        """Test that a node is initialized with correct attributes."""
        assert node.name == "test_node_1"
        assert node.type == "TestType"
        assert node.isDirty() is True
        assert len(node.inputs) == 0
        assert len(node.outputs) == 0
        assert node.isFlowControlNode() is False
        assert node.isDataNode() is True

    def test_dirty_flag_management(self, node):
        """Test marking node dirty and clean."""
        node.markClean()
        assert node.isDirty() is False
        
        node.markDirty()
        assert node.isDirty() is True

    def test_add_data_input(self, node):
        """Test adding a data input port."""
        port = node.add_data_input("in_a")
        
        assert "in_a" in node.inputs
        assert node.inputs["in_a"] == port
        assert isinstance(port, DataPort)
        assert port.port_name == "in_a"
        # Default type is ANY
        assert port.data_type == ValueType.ANY 

    def test_add_data_output(self, node):
        """Test adding a data output port."""
        port = node.add_data_output("out_result")
        
        assert "out_result" in node.outputs
        assert node.outputs["out_result"] == port
        assert isinstance(port, DataPort)
        assert port.port_name == "out_result"

    def test_add_control_input(self, node):
        """Test adding a control input port."""
        port = node.add_control_input("exec")
        
        assert "exec" in node.inputs
        assert node.inputs["exec"] == port
        assert isinstance(port, ControlPort)
        assert port.isControlPort() is True

    def test_add_control_output(self, node):
        """Test adding a control output port."""
        port = node.add_control_output("then")
        
        assert "then" in node.outputs
        assert node.outputs["then"] == port
        assert isinstance(port, ControlPort)
        assert port.isControlPort() is True

    def test_duplicate_port_name_error(self, node):
        """Test that adding a duplicate port name raises ValueError."""
        node.add_data_input("dup_port")
        with pytest.raises(ValueError, match="already exists"):
            node.add_data_input("dup_port")

        node.add_data_output("dup_port_out")
        with pytest.raises(ValueError, match="already exists"):
            node.add_data_output("dup_port_out")

    def test_typed_ports(self, node):
        """Test functionality of typed ports."""
        import asyncio
        
        async def run():
            # Add typed ports
            int_port = node.add_data_input("int_input_t", data_type=ValueType.INT)
            float_port = node.add_data_output("float_output_t", data_type=ValueType.FLOAT)
            
            assert int_port.data_type == ValueType.INT
            assert float_port.data_type == ValueType.FLOAT
            
            # Test validation via port directly
            # Valid assignment
            int_port.setValue(42)
            val = await int_port.getValue() 
            assert val == 42
            
            # Invalid assignment (should print warning based on current implementation, 
            # or we check if we change it to raise exception in future)
            # For now, just checking we can set it, as the current impl only prints warnings
            int_port.setValue("not an int") 
            val2 = await int_port.getValue()
            assert val2 == "not an int"

        asyncio.run(run())

    def test_helper_get_ports(self, node):
        """Test helper methods for retrieving specific types of ports."""
        node.add_data_input("d_in", ValueType.INT)
        node.add_control_input("c_in")
        node.add_data_output("d_out", ValueType.FLOAT)
        node.add_control_output("c_out")
        
        # Verify get_input_data_port returns correct port
        d_in = node.get_input_data_port("d_in")
        assert d_in is not None
        assert d_in.port_name == "d_in"
        assert d_in.data_type == ValueType.INT
        
        # Verify get_input_control_port
        c_in = node.get_input_control_port("c_in")
        assert c_in is not None
        assert c_in.port_name == "c_in"
        
        # Verify retrieval fail returns None (or raises based on impl, check source)
        # Source says: return self.inputs[port_name] ... lines 220-227 omitted
        # If key doesn't exist, it might raise KeyError. Let's check implicit behavior or dict access
        # Python dict raises KeyError. 
        with pytest.raises(KeyError):
            node.get_input_data_port("non_existent")

    def test_delete_input_port(self, node):
        """Test deleting an input port."""
        node.add_data_input("to_delete")
        assert "to_delete" in node.inputs
        
        node.delete_input("to_delete")
        assert "to_delete" not in node.inputs

    def test_delete_output_port(self, node):
        """Test deleting an output port."""
        node.add_data_output("to_delete")
        assert "to_delete" in node.outputs
        
        node.delete_output("to_delete")
        assert "to_delete" not in node.outputs


# Optional: Data Type Validation Tests
class TestDataTypeValidation:

    def setup_method(self):
        # Stub: Setup logic here
        pass

    def teardown_method(self):
        # Stub: Cleanup logic here
        pass
    
    def test_validate_methods(self):
        assert ValueType.validate(10, ValueType.INT) is True
        assert ValueType.validate(10.5, ValueType.INT) is False
        
        assert ValueType.validate(10.5, ValueType.FLOAT) is True
        assert ValueType.validate(10, ValueType.FLOAT) is True # Int allowed as float
        
        assert ValueType.validate("hello", ValueType.STRING) is True
        assert ValueType.validate(123, ValueType.STRING) is False
        
        assert ValueType.validate([1,2], ValueType.ARRAY) is True
        assert ValueType.validate({'a':1}, ValueType.DICT) is True
