import time
import logging
import sys
import threading
import asyncio

# Add current directory to path so imports work if run directly
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.NodeNetwork import NodeNetwork
from core.Node import Node, ExecutionResult, ExecCommand
from core.NodePort import ValueType
from RabbitMQNodes import RabbitMQProducerNode, RabbitMQConsumerNode
from RabbitMQService import RabbitMQService

# Setup logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Define a simple LogNode for demonstration ---
class LogNode(Node):
    def __init__(self, id: str, type: str = "LogNode", prefix: str = "", **kwargs):
        super().__init__(id, type, **kwargs)
        self.prefix = prefix
        self.add_control_input("run")
        self.add_data_input("message", ValueType.STRING)
        self.add_control_output("done")

    async def compute(self) -> ExecutionResult:
        try:
             msg = await self.get_input_data_port("message").getValue()
        except:
             msg = "(No data)"
             
        print(f"\n[LogNode {self.id}] {self.prefix}: {msg}\n")
        
        # Trigger next if connected
        next_nodes = []
        done_output = self.get_output_control_port("done")
        for conn in done_output.outgoing_connections:
            # Activate and collect
            conn.to_port.activate()
            next_nodes.append(conn.to_port.node)
        return ExecutionResult(ExecCommand.CONTINUE, next_nodes)

# --- Main Example Flow ---
async def main():
    print("--- Starting RabbitMQ Node Demo ---")

    # 1. Create the Network
    net = NodeNetwork("RootNetwork")
    
    # ... (setup code is sync, fine to leave as is inside async def) ...


    # 2. Build the Consumer Chain:  [Consumer] -> [LogNode]
    # This chain will sit waiting for messages.
    # Note: passing `owner=net` is crucial so the consumer knows who to ask to run.
    consumer = RabbitMQConsumerNode(id="consumer_1", queue_name="nexus_demo_queue", owner=net)
    net.add_node(consumer)
    
    logger_node = LogNode(id="logger_1", prefix="Received from RabbitMQ", owner=net)
    net.add_node(logger_node)
    
    # Connect Consumer -> LogNode
    # Flow Control: Consumer.on_message -> Logger.run
    consumer.connect_output_to("on_message", logger_node, "run")
    # Data: Consumer.message_body -> Logger.message
    consumer.connect_output_to("message_body", logger_node, "message")


    # 3. Build the Producer Chain: [Producer]
    # We will trigger this manually in the script to simulate a send event.
    producer = RabbitMQProducerNode(id="producer_1", queue_name="nexus_demo_queue", owner=net)
    net.add_node(producer)
    # Set the payload we want to send
    producer.get_input_data_port("payload").value = "Hello from Nexus8 Nodes!"


    # 4. Start the network (which starts listeners)
    print("System setup complete. Waiting 2 seconds for RabbitMQ connection setup...")
    
    # We explicitly start the consumer service (optional if nodes do it, but good practice)
    # RabbitMQService.get_instance().start_consuming() 
    # (ConsumerNode constructor already called subscribe->start_consuming)
    
    await asyncio.sleep(2)

    # 5. Simulate execution: Trigger the Producer
    print("\n--- Triggering Producer manually ---")
    # In a real graph, something would flow into "send". Here we just run it directly.
    # producer.compute() -> await net.compute(...)
    await net.compute(start_nodes=[producer])

    print("Producer executed. Waiting for Consumer to pick it up...")
    
    # 6. Wait to see the result
    await asyncio.sleep(2)
    
    print("\n--- Sending another message ---")
    producer.get_input_data_port("payload").value = "Message #2: Async Magic"
    await net.compute(start_nodes=[producer])
    
    await asyncio.sleep(2)
    print("\n--- Demo Complete ---")

    RabbitMQService.get_instance().stop()
    # Force exit because daemon threads might linger if not stopped cleanly
    os._exit(0)

if __name__ == "__main__":
    asyncio.run(main())
