import os
import json
import sys
import time
import subprocess
import extism
from core.NodeNetwork import NodeNetwork
from RabbitMQNodes import RabbitMQProducerNode, RabbitMQConsumerNode
from RabbitMQService import RabbitMQService
from compiler.IRBuilder import IRBuilder
from compiler.AssemblyScriptGenerator import AssemblyScriptGenerator
from extism import Plugin, ValType, CurrentPlugin, host_fn

# Ensure build dir exists
BUILD_DIR = "build"
if not os.path.exists(BUILD_DIR):
    os.makedirs(BUILD_DIR)

def run_interpreted_demo():
    print("\n--- [INTERPRETED MODE] ---")
    net = NodeNetwork("InterpretedNet")
    
    # 1. Consumer (Entry Point)
    consumer = RabbitMQConsumerNode("cons1", queue_name="input_queue", owner=net)
    net.add_node(consumer)
    
    # 2. Producer (Exit Point)
    producer = RabbitMQProducerNode("prod1", queue_name="output_queue", owner=net)

    net.add_node(producer)
    
    # Connect
    net.connectNodes(consumer.id, "message_body", producer.id, "payload")
    net.connectNodes(consumer.id, "on_message", producer.id, "send")
    
    # Simulate Message Arrival (Manually triggering the consumer callback logic)
    print(">> Simulating incoming message 'Hello Interpreted'...")
    # Typically RabbitMQService triggers this. We do it manually for demo.
    #consumer.handle_message(b"Hello Interpreted")

    
    
    # Note: The 'Producer' will print/send via RabbitMQService. 
    # Since we don't have a real broker, we might see connection errors or logs.
    time.sleep(5) 


def run_compiled_demo():
    print("\n--- [COMPILED MODE] ---")
    
    # 1. Setup Graph (Same topology)
    net = NodeNetwork("CompiledNet")
    consumer = RabbitMQConsumerNode("cons1", queue_name="input_queue") # ID must be cleaner for function names?
    consumer.id = "cons1" # Ensure clean ID
    net.add_node(consumer)
    
    producer = RabbitMQProducerNode("prod1", queue_name="output_queue")
    producer.id = "prod1"
    net.add_node(producer)
    
    net.connectNodes("cons1", "message_body", "prod1", "payload")
    net.connectNodes("cons1", "on_message", "prod1", "send")
    
    # 2. Compile to IR
    print(">> Compiling to IR...")
    builder = IRBuilder()
    
    # We compile the "Entry Point" node. 
    # This triggers the cascade to downstream nodes.
    builder.compile_node(consumer)
    
    # Debug IR
    builder.print_ir()
    
    # 3. Compile to AssemblyScript
    print(">> Generating AssemblyScript...")
    gen = AssemblyScriptGenerator()
    as_code = gen.generate(builder)
    
    ts_path = os.path.join(BUILD_DIR, "graph.ts")
    #with open(ts_path, "w") as f:
    #    f.write(as_code)
    print(f">> Wrote {ts_path}")
    print(f"\n--- GENERATED CODE ---\n{as_code}\n----------------------\n")
    
    # 4. Compile to Wasm (using asc)
    wasm_path = os.path.join(BUILD_DIR, "graph.wasm")
    print(f">> Compiling to Wasm: {wasm_path}")
    
    try:
        # Use list args for safety
        asc_bin = "../../../node_modules/.bin/asc"
        args = [
            "node",
            asc_bin,
            ts_path,
            "-o", wasm_path,  # Output binary
            "-O3",
            "--runtime", "stub", # Use stub for predictable memory layout
            "--use", "abort="
        ]
        print(f"   Command: {' '.join(args)}")
        subprocess.run(args, check=True)
    except Exception as e:
        print(f"!! Compilation Failed (Is AssemblyScript installed?): {e}")
        print("!! Skipping Wasm execution step.")
        return

    # 5. Run with Extism
    print(">> Running Wasm with Extism...")
    
    # Define Host Function
    @extism.host_fn(
        namespace="extism:host/user",
        name="host_rabbitmq_publish",
        signature=([extism.ValType.I64, extism.ValType.I64, extism.ValType.I64, extism.ValType.I64], [])
    )
    def host_rabbitmq_publish(plugin, inputs, user_data):
        q_ptr = inputs[0].value
        q_len = inputs[1].value
        m_ptr = inputs[2].value
        m_len = inputs[3].value
        
        #producer = RabbitMQProducerNode("prod1", queue_name="output_queue", owner=net)
        RabbitMQService.get_instance().publish("nexus_demo_queue",  "<WASM PUBLISH SIMULATION>")

        try:
            # DEBUGGING RAW MEMORY BLOCKS
            h_q = plugin.memory_at_offset(q_ptr)
            mem_q = plugin.memory(h_q)
            print(f"DEBUG: Q Ptr {q_ptr}, Mem View Len: {len(mem_q)}")
            print(f"DEBUG: Q Bytes (First 20): {bytes(mem_q[:20]).hex()}")
            
            queue = "<error>"
            # Try Block Assumption (Index 0)
            if len(mem_q) >= q_len:
                    queue = bytes(mem_q[:q_len]).decode('utf-8')
            
            h_m = plugin.memory_at_offset(m_ptr)
            mem_m = plugin.memory(h_m)
            print(f"DEBUG: M Ptr {m_ptr}, Mem View Len: {len(mem_m)}")
            print(f"DEBUG: M Bytes (First 20): {bytes(mem_m[:20]).hex()}")
            
            msg = "<error>"
            if len(mem_m) >= m_len:
                    msg = bytes(mem_m[:m_len]).decode('utf-8')

            print(f"[HOST] Wasm asked to publish: '{msg}' -> '{queue}'")

        except Exception as e:
            print(f"[HOST] Error: {e}")

    # Define Abort (Required for non-stub AS runtime)
    @extism.host_fn(
        namespace="env",
        name="abort",
        signature=([extism.ValType.I32, extism.ValType.I32, extism.ValType.I32, extism.ValType.I32], [])
    )
    def host_abort(plugin, inputs, outputs, user_data=None):
        msg_ptr = inputs[0].value
        file_ptr = inputs[1].value
        line = inputs[2].value
        col = inputs[3].value
        print(f"!! WASM ABORT !! Line: {line}, Col: {col}")
            # Could read strings if needed

    def decode_string_from_wasm(plugin, ptr: int) -> str:
        handle = plugin.memory_at_offset(ptr)
        mem_bytes = plugin.memory(handle)
        msg = bytes(mem_bytes).decode('utf-8')
        return msg
    
    def decode_json_from_wasm(plugin, ptr: int) -> dict:
        handle = plugin.memory_at_offset(ptr)
        mem_bytes = plugin.memory(handle)
        msg_str = bytes(mem_bytes).decode('utf-8')
        data = json.loads(msg_str)
        return data
    
    def encode_string_to_wasm(plugin, text: str) -> int:
        response_bytes = text.encode('utf-8')
        mem_handle = plugin.alloc(len(response_bytes))
        mem_buf = plugin.memory(mem_handle)
        mem_buf[:] = response_bytes
        return mem_handle.offset
    
    
    @host_fn(
        namespace="extism:host/user",
        name="logme",
        signature=([ValType.I64], [ValType.I64])
    )
    def logme(plugin: CurrentPlugin, inputs, outputs, user_data=None):
        """
        Host function 'logme'.
        Accepts a string pointer from WASM, prints it, and returns a modified string pointer.
        """
        # 1. Get arguments
        # Input is a pointer (I64) to the string in WASM memory
        #ptr = inputs[0].value
        
        # 2. Read string from WASM memory
        # Get memory handle from offset
        #mem_handle = plugin.memory_at_offset(ptr)
        # Get bytes from handle
        #mem_bytes = plugin.memory(mem_handle)
        #msg = bytes(mem_bytes).decode('utf-8')

        # we know inputs[0] is the pointer to the string
        msg = decode_string_from_wasm(plugin, inputs[0].value)
        
        print(f"\n[Python Host] 'logme' was called with message: '{msg}'")
        
        # 3. Prepare response
        response_text = msg + " [Acknowledged by Python Host!!]"
        
        # 4. Allocate memory for response in WASM
        # alloc returns a MemoryHandle, we need the offset
        #response_bytes = response_text.encode('utf-8')
        #mem_handle = plugin.alloc(len(response_bytes))
        
        # Write to memory
        #mem_buf = plugin.memory(mem_handle)
        #mem_buf[:] = response_bytes
        
        # 5. Return the result
        # We write the offset (I64) to the outputs
        #outputs[0].value = mem_handle.offset

        outputs[0].value = encode_string_to_wasm(plugin, response_text)


    @extism.host_fn(
        namespace="extism:host/user",
        name="log",
        signature=([extism.ValType.I64], [])
    )
    def host_log(plugin, inputs, user_data):
        print(f"[WASM LOG] {inputs[0].value}")

    @extism.host_fn(
        namespace="extism:host/user",
        name="log_raw",
        signature=([extism.ValType.I32, extism.ValType.I32], [])
    )
    def host_log_raw(plugin, inputs, user_data):
        ptr = inputs[0].value
        length = inputs[1].value
        try:
            h = plugin.memory_at_offset(ptr)
            mem = plugin.memory(h)
            data = bytes(mem[:length])
            print(f"[WASM RAW LOG] {data}", length, mem, data.decode('utf-8'))
        except Exception as e:
            print(f"[WASM RAW LOG ERROR] {e}")


    # Enable Extism logging to stdout
    extism.set_log_file("stdout", "debug")

    functions = [host_rabbitmq_publish, host_abort, host_log, host_log_raw, logme]
    #functions = [logme]

    
    # Disable WASI to minimize interference, or check if that helps memory mapping
    plugin = extism.Plugin(open(wasm_path, "rb").read(), functions=functions, wasi=True)
    
    # Trigger the exported function from the Consumer
    entry_point = "trigger_cons1" 
    print(f">> Calling Wasm Export: {entry_point}('Hello Wasm')")
    
    # Helper to write string to memory
    # Since we are using raw pointers in AS, we need to alloc and write
    # But for a simple test, we assume we can pass a pointer?
    # Extism 'ptr' calling convention usually involves allocation.
    # To keep this demo simple, we assume the AS side expects a pointer to a pre-existing string in logic 
    # OR we use extism's alloc.
    
    # Proper Extism string passing:
    msg_str = "Hello Wasm"
    # Alloc memory in Wasm
    # Note: 'alloc' might need to be exported or available. 
    # With 'stub' runtime, alloc might not be there standardly. 
    # But usually Extism plugins export 'alloc'.
    # If not, we might fail here.
    
    try:
        # We'll try to just run it. If alloc fails, we catch.
        # Ideally, we write the string into the plugin memory
        # plugin.call(entry_point, msg_str) -- higher level SDKs might support this
        # Python SDK supports string args if the plugin expects generic inputs, 
        # but our AS code expects 'ptr: u64'.
        
        # NOTE: Using extism.Plugin.call with bytes/string usually handles allocation if params match.
        # But here we defined explicit args "ptr: u64".
        # Let's try direct call.
        result = plugin.call(entry_point, msg_str.encode('utf-8'))
        print(">> Wasm Execution Complete.")
    except Exception as e:
        print(f"!! Extism Execution Error: {e}")

if __name__ == "__main__":
    try:
        run_interpreted_demo()
        run_compiled_demo()
    except KeyboardInterrupt:
        pass
