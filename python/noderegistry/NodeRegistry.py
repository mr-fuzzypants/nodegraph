


from typing import Any, List, Optional, TYPE_CHECKING
from ..core.Node import Node, ExecCommand, ExecutionResult
from ..core.NodePort import (
    NodePort, 
    ValueType, # Replaces DataType
    PortFunction
)

if TYPE_CHECKING:
    pass

# Alias for backward compatibility if needed, but prefer ValueType
DataType = ValueType 

# =========================================================================================
# DUAL-MODE NODE ARCHITECTURE
# 
# 1. Runtime Mode (compute): 
#    - Python interprets the graph directly. 
#    - Uses `ExecutionResult` to act as a "Command Generator" for the NodeNetwork Runner.
#    - Compatible with async/event-driven systems (TS/JS) and ownership systems (Rust).
#
# 2. Compile Mode (compile):
#    - Python acts as a compiler frontend.
#    - Traverses the graph to emit Linear IR (Intermediate Representation).
#    - This IR is then used to generate efficient AssemblyScript/WASM code.
# =========================================================================================

@Node.register("Parameter")
class ParamNode(Node):
    def __init__(self, id: str, type: str, value: Any, **kwargs):
        super().__init__(id, type, **kwargs)

        self.dout_value = self.add_data_output('value', data_type=ValueType.ANY) # Ideally specific type
        self.param_value = value
        
    async def compute(self, executionContext=None) -> ExecutionResult:
        super().precompute()

        # For a parameter node, we might just set a default value
        self.dout_value.setValue(self.param_value)
        self.markClean()
        self._isDirty = False

        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

    def compile(self, builder: Any):
        # Compile Time: Emit a constant definition
        val = self.param_value
        target_var = builder.new_temp()
        builder.emit("CONST", val, "->", target_var)
        # Store mapping for downstream nodes to find this variable
        builder.set_var(self.dout_value, target_var)

    def generate_IRC(self, irc_builder: Any) -> Any:
        # Generic legacy hook, redirect to compile if needed or keep for backward compat
        return self.compile(irc_builder)
        

@Node.register("Add")
class AddNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)

        # Enforce types if possible, or leave ANY for polymorphism
        self.din_a = self.add_data_input('a', data_type=ValueType.ANY)
        self.din_b = self.add_data_input('b', data_type=ValueType.ANY)
        self.dout_result = self.add_data_output('result', data_type=ValueType.ANY)


    async def compute(self, executionContext=None) -> ExecutionResult:
        super().precompute()

        a = await self.din_a.getValue()
        b = await self.din_b.getValue()

        # Rust/TS: strictly check types here or rely on port connection rules
        if self.all_data_inputs_clean():
            # Runtime validation
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                 self.dout_result.setValue(a + b)
            else:
                 # In TS this would be a runtime error or string concatenation
                 self.dout_result.setValue(str(a) + str(b))
        else:
            raise ValueError(f"Cannot compute '{self.type}' '{self.id}' because inputs are dirty")
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

    def compile(self, builder: Any):
        # Compile Time
        var_a = builder.get_var(self.din_a.get_source())
        var_b = builder.get_var(self.din_b.get_source())
        result_var = builder.new_temp()
        
        builder.emit("ADD", var_a, var_b, "->", result_var)
        builder.set_var(self.dout_result, result_var)

    
@Node.register("LessThan")
class LessThanNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)

        self.din_a = self.add_data_input('a')
        self.din_b = self.add_data_input('b')
        self.dout_result = self.add_data_output('result', data_type=ValueType.BOOL)


    async def compute(self, executionContext=None) -> ExecutionResult:
        self.precompute()
       
        a = await self.din_a.getValue()
        b = await self.din_b.getValue()

        if self.all_data_inputs_clean():
            self.dout_result.setValue(a < b)
        else:
            raise ValueError(f"Cannot compute LessThanNode '{self.id}' because inputs are dirty")
            
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

    def compile(self, builder: Any):
        var_a = builder.get_var(self.din_a.get_source())
        var_b = builder.get_var(self.din_b.get_source())
        result_var = builder.new_temp()
        builder.emit("CMP_LT", var_a, var_b, "->", result_var)
        builder.set_var(self.dout_result, result_var)

@Node.register("If")
class IfNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)

        self.cin_exec = self.add_control_input('exec')
        self.din_condition = self.add_data_input('condition', data_type=ValueType.BOOL)
        self.cout_true = self.add_control_output('true')
        self.cout_false = self.add_control_output('false')

        self.is_flow_control_node = True

    async def compute(self, executionContext=None) -> ExecutionResult:
        super().precompute()
        
        next_nodes = []
        if self.cin_exec.isActive():
            self.cin_exec.deactivate()
        
            condition = await self.din_condition.getValue()
            
            if self.all_data_inputs_clean():
                if condition:
                    self.cout_true.activate()
                    self.cout_false.deactivate()
                    next_nodes = self._get_nodes_from_port(self.cout_true)
                else:
                    self.cout_false.activate()
                    self.cout_true.deactivate()
                    next_nodes = self._get_nodes_from_port(self.cout_false)
            else:
                raise ValueError(f"Cannot compute IfNode '{self.id}' because inputs are dirty")
        
        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)

    def compile(self, builder: Any):
        lbl_true = builder.new_label("IF_TRUE")
        lbl_false = builder.new_label("IF_FALSE")
        lbl_end = builder.new_label("IF_END")
        
        cond_var = builder.get_var(self.din_condition.get_source())
        builder.emit("TEST", cond_var)
        builder.emit("JMP_IF_FALSE", lbl_false)
        
        builder.emit_label(lbl_true)
        nodes_true = self._get_nodes_from_port(self.cout_true)
        if nodes_true: builder.compile_chain(nodes_true[0])
        builder.emit("JMP", lbl_end)

        builder.emit_label(lbl_false)
        nodes_false = self._get_nodes_from_port(self.cout_false)
        if nodes_false: builder.compile_chain(nodes_false[0])

        builder.emit_label(lbl_end)

@Node.register("Loop")
class LoopNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)

        self.cin_exec = self.add_control_input('exec')
        self.cout_body = self.add_control_output('body')
        self.cout_completed = self.add_control_output('completed')

        self.din_start = self.add_data_input('start', data_type=ValueType.INT)
        self.din_end = self.add_data_input('end', data_type=ValueType.INT)
        self.din_step = self.add_data_input('step', data_type=ValueType.INT)
        self.dout_index = self.add_data_output('index', data_type=ValueType.INT)

        self.initalized = False
        self.is_loop_node = True
        self.index = 0
        self.is_flow_control_node = True
        
        # Temp storage for iteration checks
        self.index_start = 0
        self.index_end = 0
        self.index_step = 1

    async def execute_body(self):
        """
        Synchronously executes the loop body for the Python Runtime.
        For Typescript/Rust, this logic would be handled by a Stack-based Runner.
        """
        # NOTE: Loop body might also need async/await execution if nodes inside it are async
        import asyncio
        start_nodes = self._get_nodes_from_port(self.cout_body)
        current_queue = start_nodes
        
        while current_queue:
            # Parallel execution of current step
            tasks = [node.compute() for node in current_queue]
            results = await asyncio.gather(*tasks)
            
            next_step_nodes = []
            for result in results:
                if isinstance(result, ExecutionResult):
                    if result.command == ExecCommand.CONTINUE:
                        next_step_nodes.extend(result.next_nodes)
            current_queue = next_step_nodes

    async def compute(self, executionContext=None) -> ExecutionResult:
        """
        Runtime: Synchronous execution for demo purposes.
        """
        super().precompute() 
        next_nodes = []

        if self.cin_exec.isActive():
            self.cin_exec.deactivate()
            
            # 1. Init
            self.index = int(await self.din_start.getValue())
            end = int(await self.din_end.getValue())
            step = int(await self.din_step.getValue())

            # 2. Run Loop Synchronously
            while self.index < end:
                self.dout_index.setValue(self.index)
                
                self.cout_body.activate()
                # Execute Body completely
                await self.execute_body()
                
                # Increment
                self.index += step

            # 3. Done
            self.cout_completed.activate()
            next_nodes = self._get_nodes_from_port(self.cout_completed)

        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)

    def compile(self, builder: Any):
        """
        Compile Implementation: Linear IR
        Flattens the loop structure into explicit JUMP instructions.
        This is standard compiler design and translates 1:1 to WASM.
        """
        # Compile Time: Linear IR gen
        start_var = builder.get_var(self.din_start.get_source())
        end_var = builder.get_var(self.din_end.get_source())
        step_var = builder.get_var(self.din_step.get_source())
        index_reg = builder.new_temp() 
        builder.set_var(self.dout_index, index_reg)

        lbl_start = builder.new_label("LOOP_START")
        lbl_end = builder.new_label("LOOP_END")

        builder.emit("MOVE", start_var, index_reg)
        builder.emit_label(lbl_start)
        builder.emit("CMP_GE", index_reg, end_var)
        builder.emit("JMP_IF_TRUE", lbl_end)

        # Body
        body_nodes = self._get_nodes_from_port(self.cout_body)
        if body_nodes: builder.compile_chain(body_nodes[0])

        builder.emit("ADD", index_reg, step_var, index_reg)
        builder.emit("JMP", lbl_start)
        builder.emit_label(lbl_end)

        complete_nodes = self._get_nodes_from_port(self.cout_completed)
        if complete_nodes: builder.compile_chain(complete_nodes[0])


@Node.register("Message")
class MessageNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)

        self.cin_msg = self.dataport_msg = self.add_data_input('msg', ValueType.ANY)
        self.cin_exec = self.controlport_exec = self.add_control_input('exec')
        self.cout_next = self.controlport_next = self.add_control_output('next')

        self.is_flow_control_node = True
 
    async def compute(self, executionContext=None) -> ExecutionResult:
        super().precompute()
        next_nodes = []

        if self.cin_exec.isActive():
            self.cin_exec.deactivate()
            msg = await self.dataport_msg.getValue()
            print(f"MESSAGE [{self.id}]: {msg}") 
        
            self.cout_next.activate()
            next_nodes = self._get_nodes_from_port(self.cout_next)

        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)

    def compile(self, builder: Any):
        msg_var = builder.get_var(self.dataport_msg.get_source())
        builder.emit("PRINT", msg_var)
        
        next_nodes = self._get_nodes_from_port(self.cout_next)
        if next_nodes: builder.compile_chain(next_nodes[0])

@Node.register("Log")
class LogNode(Node):
    def __init__(self, id: str, type: str, **kwargs):
        super().__init__(id, type, **kwargs)

        self.add_data_input('msg', ValueType.STRING)
        self.add_control_input('exec')

        self.is_flow_control_node = True

    async def compute(self, executionContext=None) -> ExecutionResult:
        super().precompute()
        
        if self.all_data_inputs_clean():
            msg = await self.inputs['msg'].getValue()
            print("LogNode:", msg) 
        else:
            print("Cannot compute node", self.id, "because inputs are dirty")

        super().postcompute()
        return ExecutionResult(ExecCommand.CONTINUE)

    def compile(self, builder: Any):
        msg_var = builder.get_var(self.inputs['msg'].get_source())
        builder.emit("LOG", msg_var)




    




