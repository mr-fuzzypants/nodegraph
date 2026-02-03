from typing import List, Optional
from core.Node import Node, ExecCommand, ExecutionResult
from core.NodePort import ValueType
from RabbitMQService import RabbitMQService
import threading

class RabbitMQProducerNode(Node):
    def __init__(self, id: str, type: str = "RabbitMQProducer", queue_name: str = "default", **kwargs):
        super().__init__(id, type, **kwargs)
        self.queue_name = queue_name
        
        # Inputs: Trigger and Data
        self.add_control_input("send")
        self.add_data_input("payload", ValueType.STRING) 
        
        # Outputs: Signal when sent
        self.add_control_output("sent")

    async def compute(self) -> ExecutionResult:
        # 1. Get Data from input port
        try:
            payload_port = self.get_input_data_port("payload")
            payload = str(await payload_port.getValue())
        except Exception:
            payload = "" # Default or error handle?

        # 2. Publish
        RabbitMQService.get_instance().publish(self.queue_name, payload)
        
        # 3. Continue execution
        next_nodes = []
        sent_output = self.get_output_control_port("sent")
        for conn in sent_output.outgoing_connections:
            # if conn.to_port.isActive(): # Removed isActive check? usually we just activate next node.
            # But here we are looking for next nodes to compute.
            # Standard pattern:
            conn.to_port.activate()
            next_nodes.append(conn.to_port.node)
                
        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)

    def compile(self, builder):
        """
        [Compile Phase]
        Generate IR instructions to publish the message.
        """
        # 1. Get the variable holding the input data
        #    This automatically triggers compilation of upstream nodes if needed!
        payload_port = self.get_input_data_port("payload")
        input_var = builder.get_var(payload_port.get_source()) # e.g., "t14"

        # 2. Emit the instruction to call the host
        #    Opcode: CALL_HOST, Function Name, Queue Name, Payload Var
        builder.emit("CALL_HOST", "rabbitmq_publish", f'"{self.queue_name}"', input_var)
        
        # 3. Handle Control Flow (Explicit Push)
        #    If specific nodes follow this in control flow, compile them.
        output_ctrl = self.get_output_control_port("sent")
        for conn in output_ctrl.outgoing_connections:
            builder.compile_chain(conn.to_port.node)


class RabbitMQConsumerNode(Node):
    def __init__(self, id: str, type: str = "RabbitMQConsumer", queue_name: str = "default", **kwargs):
        super().__init__(id, type, **kwargs)
        self.queue_name = queue_name
        
        # Outputs: Message content and trigger
        self.add_control_output("on_message")
        self.add_data_output("message_body", ValueType.STRING)
        
        # Register callback
        RabbitMQService.get_instance().subscribe(self.queue_name, self.handle_message)

    def handle_message(self, body: bytes):
        """
        Called by RabbitMQService thread.
        We must be careful about thread safety here depending on how NodeNetwork is implemented.
        For this demo, we assume we can trigger compute from another thread 
        or we are okay with the consequences.
        """
        message_str = body.decode('utf-8')
        
        # 1. Update local state (data output)
        self.get_output_data_port("message_body").value = message_str
        self.markDirty() # Mark self as needing update/processing if caching was involved
        
        # 2. Trigger Network Execution
        # We need to find our owner (NodeNetwork) and ask it to run starting from us.
        if self.owner and hasattr(self.owner, 'compute'):
            print(f"ConsumerNode {self.id} triggered! message: {message_str}")
            # In a real GUI app, we might need to invoke this on the main thread.
            import asyncio
            try:
                # If we are in a thread with no loop, run a new one
                asyncio.run(self.owner.compute(start_nodes=[self]))
            except RuntimeError:
                # If a loop is already running (unlikely in this thread setup but possible)
                # handle gracefully or use run_coroutine_threadsafe if we had reference to main loop
                print("Error: Could not run async compute from thread.")
        else:
            print(f"ConsumerNode {self.id} received message but has no owner/runner to trigger.")

    async def compute(self) -> ExecutionResult:
        # When the network actually runs us (triggered by handle_message -> owner.compute -> us),
        # we just continue flow.
        
        next_nodes = []
        trigger_output = self.get_output_control_port("on_message")
        for conn in trigger_output.outgoing_connections:
            if conn.to_port.isActive():
                next_nodes.append(conn.to_port.node)

        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)
    
    
    #    def activateOutputPorts(self, networkRunner):
    #    # Overridden to ensure output ports are marked active when we get a message
    
    # def deactivateInputPorts(self, networkRunner):
    #    # Overridden to prevent deactivation since we are event-driven


    def compile(self, builder):
        """
        [Compile Phase]
        This node IS the entry point, so it defines the function signature.
        """
        # 1. Allocate a variable for the incoming message
        msg_var = builder.new_temp() # e.g., "t1"
        
        # 2. Tell IR that we are starting a function here
        #    This unique function name maps to the queue in our Host
        func_name = f"trigger_{self.id}" 
        builder.emit("FUNCTION_START", func_name, msg_var)
        
        # 3. Register that our output port's value is in 'msg_var'
        #    So anyone connecting to us gets 't1'
        #    Note: We need to use set_var on builder usually, if NodePort doesn't support set_compiled_var
        builder.set_var(self.get_output_data_port("message_body"), msg_var)
        
        # 4. Compile immediate downstream neighbors to continue the chain
        output_ctrl = self.get_output_control_port("on_message")
        for conn in output_ctrl.outgoing_connections:
            builder.compile_chain(conn.to_port.node)

