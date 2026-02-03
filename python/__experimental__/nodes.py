

import sys
from collections import OrderedDict

from NodePort import *
from Node import *
from NodeNetwork import NodeNetwork

from NodeRegistry import MessageNode, LoopNode, IfNode, LogNode, AddNode, LessThanNode


 


#===================
# IR GENERATOR
#===================

class NodeError(Exception):
    def __init__(self, node_id, message, phase="runtime"):
        self.node_id = node_id
        self.message = message
        self.phase = phase # 'validation', 'compilation', 'runtime'
        super().__init__(f"[{phase}] Node {node_id}: {message}")

    def to_dict(self):
        return {
            "nodeId": self.node_id,
            "message": self.message,
            "phase": self.phase
        }

class IRGenerator:
    def __init__(self):
        self.instructions = []
        self.temp_counter = 0
        self.label_counter = 0
        self.node_results = {} # Cache for data node results (SSA-like)
        self.errors = []

    def error(self, node, message):
        """Log an error and continue if possible, or mark node as broken"""
        self.errors.append(NodeError(node.id, message, "compilation"))

    def new_temp(self):
        self.temp_counter += 1
        return f"t{self.temp_counter}"

    def new_label(self, prefix="L"):
        self.label_counter += 1
        return f"{prefix}_{self.label_counter}"

    def emit(self, op, *args):
        self.instructions.append(f"{op:<12} {', '.join(map(str, args))}")

    def get_input_node(self, node, port_name):
        """Helper to find the node connected to a specific input port"""
        port = node.inputs.get(port_name)
        if port and port.incoming_connections:
            return port.incoming_connections[0].from_node
        return None

    def get_next_control_node(self, node, port_name):
        """Helper to find the next control node (Deprecated for single output, only returns first)"""
        port = node.outputs.get(port_name)
        if port and port.outgoing_connections:
            return port.outgoing_connections[0].to_node
        return None

    def get_next_control_nodes(self, node, port_name):
        """Helper to find ALL next control nodes from a specific port"""
        port = node.outputs.get(port_name)
        if port and port.outgoing_connections:
            return [conn.to_node for conn in port.outgoing_connections]
        return []

    def compile_data_node(self, node):
        """Recursively compile data dependencies"""
        try:
            if node.id in self.node_results:
                return self.node_results[node.id]

            result = None

            if node.type == 'ConstInt' or node.type == 'ConstString':

                raise ValueError("ConstInt and ConstString nodes are deprecated. Use Parameter nodes instead.")
                # In a real app, value would be stored in node.data
                # Here we infer from ID or hardcode for demo
                val = "0"
                if "c_0" in node.id: val = "0"
                elif "c_5" in node.id: val = "5"
                elif "c_1" in node.id: val = "1"
                elif "c0" in node.id: val = "0"
                elif "c5" in node.id: val = "5"
                elif "c1" in node.id: val = "1"
                elif "msg" in node.id: val = '"Hello World"'
                
                result = self.new_temp()
                self.emit("CONST", val, "->", result)

            elif node.type == 'Parameter':
                val = str(node.param_value)
                result = self.new_temp()
                self.emit("CONST", val, "->", result)

            elif node.type == 'GetVar':
                raise ValueError("GetVar nodes are deprecated. Use Parameter nodes instead.")
                var_name = "i" # inferred for demo
                result = self.new_temp()
                self.emit("LOAD", var_name, "->", result)

            elif node.type == 'LessThan':
                a = self.compile_data_node(self.get_input_node(node, 'a'))
                b = self.compile_data_node(self.get_input_node(node, 'b'))
                result = self.new_temp()
                self.emit("LT", a, b, "->", result)

            elif node.type == 'Add':
                a = self.compile_data_node(self.get_input_node(node, 'a'))
                b = self.compile_data_node(self.get_input_node(node, 'b'))
                result = self.new_temp()
                self.emit("ADD", a, b, "->", result)

            self.node_results[node.id] = result
            return result
        except Exception as e:
            self.error(node, str(e))
            return self.new_temp()

    def compile_control_flow(self, node, stop_nodes=None):
        """Traverse control flow nodes recursively"""
        if not node:
            return

        if stop_nodes and node in stop_nodes:
            return
        
        # Emit DEBUG_LOC so runtime knows where we are
        self.emit("DEBUG_LOC", node.id)
        
        # Helper to process a standard "next" output that supports multiple connections
        def process_next_nodes(port_name):
            targets = self.get_next_control_nodes(node, port_name)
            for target in targets:
                self.compile_control_flow(target, stop_nodes)

        if node.type == 'Start':
            self.emit("ENTRY")
            process_next_nodes('exec')

        elif node.type == 'SetVar':
            val = self.compile_data_node(self.get_input_node(node, 'val'))
            var_name = "i" 
            self.emit("STORE", var_name, val)
            process_next_nodes('next')

        elif node.type == 'Log':
            msg = self.compile_data_node(self.get_input_node(node, 'msg'))
            self.emit("PRINT", msg)
            process_next_nodes('next')

        elif node.type == 'Message':
            msg = self.compile_data_node(self.get_input_node(node, 'msg'))
            self.emit("PRINT", msg)
            process_next_nodes('next')

        elif node.type == 'If':
            label_false = self.new_label("IF_FALSE")
            label_end = self.new_label("IF_END")
            
            # Condition
            cond = self.compile_data_node(self.get_input_node(node, 'condition'))
            self.emit("BR_FALSE", cond, label_false)
            
            # True Path
            process_next_nodes('true')
            
            self.emit("JUMP", label_end)
            
            # False Path
            self.emit("LABEL", label_false)
            process_next_nodes('false')
            
            self.emit("LABEL", label_end)
            node = None


        elif node.type == 'While':
            loop_start = self.new_label("LOOP_START")
            loop_exit = self.new_label("LOOP_EXIT")

            self.emit("LABEL", loop_start)
            
            # Compile Condition
            cond = self.compile_data_node(self.get_input_node(node, 'condition'))
            self.emit("BR_FALSE", cond, loop_exit)

            # Compile Body
            process_next_nodes('body')
            
            # Loop back
            self.emit("JUMP", loop_start)
            
            # Exit label
            self.emit("LABEL", loop_exit)
            
            # Continue main path
            process_next_nodes('exit')
        
        elif node.type == 'ForLoop' or node.type == 'Loop':
            # 1. Setup
            start_val = self.compile_data_node(self.get_input_node(node, 'start'))
            end_val = self.compile_data_node(self.get_input_node(node, 'end'))
            step_val = self.compile_data_node(self.get_input_node(node, 'step'))
            
            index_var = f"i" # Using 'i' to match existing codegen expectations for now
            
            # 2. Init: index = start
            self.emit("STORE", index_var, start_val)
            
            loop_start = self.new_label("LOOP_START")
            loop_exit = self.new_label("LOOP_EXIT")
            
            self.emit("LABEL", loop_start)
            
            # 3. Condition: index < end
            curr_index_tmp = self.new_temp()
            self.emit("LOAD", index_var, "->", curr_index_tmp)
            
            # Register this temp as the result for the ForLoop node (for 'index' output)
            self.node_results[node.id] = curr_index_tmp
            
            cond_tmp = self.new_temp()
            self.emit("LT", curr_index_tmp, end_val, "->", cond_tmp)
            self.emit("BR_FALSE", cond_tmp, loop_exit)
            
            # 4. Body
            body_targets = self.get_next_control_nodes(node, 'body')
            for target in body_targets:
                self.compile_control_flow(target, stop_nodes=[node])
                
            # 5. Increment: index = index + step
            # We need to load index again to be safe (body might have changed it, though not in this simple case)
            # But we can reuse curr_index_tmp if we assume SSA-ish, but STORE breaks SSA for 'i'.
            # So let's load again or use the temp if we know 'i' wasn't stored to.
            # For safety, let's use the temp we loaded at start of loop.
            next_val_tmp = self.new_temp()
            self.emit("ADD", curr_index_tmp, step_val, "->", next_val_tmp)
            self.emit("STORE", index_var, next_val_tmp)
            
            self.emit("JUMP", loop_start)
            self.emit("LABEL", loop_exit)
            
            # Continue to 'completed' output
            process_next_nodes('completed')

        elif node.type == 'End':
            self.emit("HALT")
            
        else:
            print(f"Unknown control node: {node.type}")


# Run the generator
generator = IRGenerator()
print("--- Generated IR ---")
#generator.compile_control_flow(loop)
#for instr in generator.instructions:
#    print(instr)



class PythonCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.current_block_name = None
        self.indent = "    "

    def parse_ir(self, instructions):
        # Pass 1: Group instructions into blocks
        current_block = []
        self.current_block_name = "entry" # Default entry block
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                # Save previous block
                if self.current_block_name:
                    self.blocks[self.current_block_name] = current_block
                
                # Start new block
                self.current_block_name = parts[1]
                current_block = []
            elif op == "ENTRY":
                continue # Just a marker
            else:
                current_block.append(line)
        
        # Save last block
        if self.current_block_name:
            self.blocks[self.current_block_name] = current_block

    def generate(self):
        code = []
        code.append("def generated_program():")
        code.append(f"{self.indent}# Initialize variables")
        code.append(f"{self.indent}i = 0")
        code.append(f"{self.indent}current_block = 'entry'")
        code.append(f"{self.indent}__active_node_id = None")
        code.append("")
        code.append(f"{self.indent}try:")
        code.append(f"{self.indent}{self.indent}while True:")
        
        block_names = list(self.blocks.keys())
        for i, block_name in enumerate(block_names):
            instrs = self.blocks[block_name]
            code.append(f"{self.indent}{self.indent}{self.indent}if current_block == '{block_name}':")
            
            if not instrs:
                # Handle empty block fallthrough
                if i + 1 < len(block_names):
                    next_block = block_names[i+1]
                    code.append(f"{self.indent}{self.indent}{self.indent}{self.indent}current_block = '{next_block}'")
                    code.append(f"{self.indent}{self.indent}{self.indent}{self.indent}continue")
                else:
                    code.append(f"{self.indent}{self.indent}{self.indent}{self.indent}return")
                continue

            for line in instrs:
                self._emit_instruction(line, code, level=4)
            
            # If block doesn't end with a jump/return, we need to handle fallthrough
            last_op = instrs[-1].split()[0] if instrs else ""
            if last_op not in ["JUMP", "BR_FALSE", "HALT"]:
                if i + 1 < len(block_names):
                    next_block = block_names[i+1]
                    code.append(f"{self.indent}{self.indent}{self.indent}{self.indent}current_block = '{next_block}'")
                    # No continue needed here as it will loop back naturally, 
                    # but explicit continue doesn't hurt and makes intent clear
                else:
                    code.append(f"{self.indent}{self.indent}{self.indent}{self.indent}return")

        code.append(f"{self.indent}except Exception as e:")
        code.append(f"{self.indent}{self.indent}# Re-raise with active node ID context")
        code.append(f"{self.indent}{self.indent}if 'NodeError' in globals():")
        code.append(f"{self.indent}{self.indent}{self.indent}raise NodeError(__active_node_id, str(e))")
        code.append(f"{self.indent}{self.indent}else:")
        code.append(f"{self.indent}{self.indent}{self.indent}# Fallback if NodeError not available")
        code.append(f"{self.indent}{self.indent}{self.indent}raise Exception(f'Error in node {{__active_node_id}}: {{str(e)}}')")

        return "\n".join(code)

    def _emit_instruction(self, line, code, level):
        indent = self.indent * level
        
        # Handle CONST specially to preserve string spaces
        if line.strip().startswith("CONST"):
            # Format: CONST val, ->, dest
            parts = line.split('->')
            # parts[0] is "CONST val, "
            # parts[1] is " dest"
            
            val_part = parts[0].strip()
            # Remove "CONST" prefix
            val_part = val_part[5:].strip()
            # Remove trailing comma if present (from IR formatting)
            if val_part.endswith(','):
                val_part = val_part[:-1]
                
            dest = parts[1].replace(',', '').strip()
            code.append(f"{indent}{dest} = {val_part}")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        
        # Remove '->' arrow from args if present
        args = [a for a in args if a != '->']

        if op == "CONST":
            # Should be handled above, but fallback just in case
            val = args[0]
            dest = args[1]
            code.append(f"{indent}{dest} = {val}")

        elif op == "STORE":
            # STORE var val
            var = args[0]
            val = args[1]
            code.append(f"{indent}{var} = {val}")

        elif op == "LOAD":
            # LOAD var dest
            var = args[0]
            dest = args[1]
            code.append(f"{indent}{dest} = {var}")

        elif op == "LT":
            # LT a b dest
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]}")

        elif op == "ADD":
            # ADD a b dest
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]}")

        elif op == "PRINT":
            code.append(f"{indent}print({args[0]})")

        elif op == "BR_FALSE":
            # BR_FALSE cond label
            cond = args[0]
            label = args[1]
            code.append(f"{indent}if not {cond}:")
            code.append(f"{indent}{self.indent}current_block = '{label}'")
            code.append(f"{indent}{self.indent}continue")

        elif op == "JUMP":
            # JUMP label
            label = args[0]
            code.append(f"{indent}current_block = '{label}'")
            code.append(f"{indent}continue")

        elif op == "DEBUG_LOC":
            # DEBUG_LOC node_id
            node_id = args[0]
            code.append(f"{indent}__active_node_id = '{node_id}'")

        elif op == "HALT":
            code.append(f"{indent}return")

# --- Usage ---

# 1. Get the IR from previous step
ir_instructions = generator.instructions

# 2. Generate Python Code
py_gen = PythonCodeGenerator()
py_gen.parse_ir(ir_instructions)
python_source = py_gen.generate()

print("\n--- Generated Python Code ---\n")
print(python_source)

print("\n--- Executing Generated Code ---\n")
exec(python_source)



class AssemblyScriptCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.current_block_name = None
        self.indent = "  "

    def parse_ir(self, instructions):
        # Reuse the same parsing logic or similar
        current_block = []
        self.current_block_name = "entry"
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if self.current_block_name:
                    self.blocks[self.current_block_name] = current_block
                self.current_block_name = parts[1]
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if self.current_block_name:
            self.blocks[self.current_block_name] = current_block

    def generate(self):
        code = []
        code.append("export function generated_program(): void {")
        code.append(f"{self.indent}// Initialize variables")
        code.append(f"{self.indent}var i: i32 = 0;")
        code.append(f"{self.indent}var current_block: string = 'entry';")
        
        # Collect and declare all temporary variables to handle scope across blocks
        temp_vars = {} # name -> type
        for instrs in self.blocks.values():
            for line in instrs:
                parts = [p.strip().replace(',', '') for p in line.split()]
                if not parts: continue
                op = parts[0]
                
                if '->' in parts:
                    idx = parts.index('->')
                    if idx + 1 < len(parts):
                        dest = parts[idx+1]
                        if op == 'LT': 
                            temp_vars[dest] = 'boolean'
                        else: 
                            temp_vars[dest] = 'i32'
                elif op == "CONST" and len(parts) >= 2:
                    # CONST val dest (if no arrow)
                    if len(parts) == 3 and parts[1] != '->':
                        temp_vars[parts[2]] = 'i32'
                elif op == "LOAD":
                    # LOAD var dest
                    if len(parts) >= 3:
                        temp_vars[parts[2]] = 'i32'

        for var_name, var_type in sorted(temp_vars.items()):
            default_val = "0" if var_type == "i32" else "false"
            code.append(f"{self.indent}var {var_name}: {var_type} = {default_val};")

        code.append("")
        code.append(f"{self.indent}while (true) {{")
        
        block_names = list(self.blocks.keys())
        for i, block_name in enumerate(block_names):
            instrs = self.blocks[block_name]
            code.append(f"{self.indent}{self.indent}if (current_block == '{block_name}') {{")
            
            if not instrs:
                if i + 1 < len(block_names):
                    next_block = block_names[i+1]
                    code.append(f"{self.indent}{self.indent}{self.indent}current_block = '{next_block}';")
                    code.append(f"{self.indent}{self.indent}{self.indent}continue;")
                else:
                    code.append(f"{self.indent}{self.indent}{self.indent}return;")
                code.append(f"{self.indent}{self.indent}}}")
                continue

            for line in instrs:
                self._emit_instruction(line, code, level=3)
            
            # If block doesn't end with a jump/return, we need to handle fallthrough
            last_op = instrs[-1].split()[0] if instrs else ""
            if last_op not in ["JUMP", "BR_FALSE", "HALT"]:
                if i + 1 < len(block_names):
                    next_block = block_names[i+1]
                    code.append(f"{self.indent}{self.indent}{self.indent}current_block = '{next_block}';")
                else:
                    code.append(f"{self.indent}{self.indent}{self.indent}return;")
            
            # Close block if
            code.append(f"{self.indent}{self.indent}}}")

        code.append(f"{self.indent}}}") # End while
        code.append("}") # End function
        return "\n".join(code)

    def _emit_instruction(self, line, code, level):
        indent = self.indent * level
        
        # Handle CONST specially to preserve string spaces
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val_part = parts[0].strip()
            val_part = val_part[5:].strip()
            if val_part.endswith(','):
                val_part = val_part[:-1]
            
            dest = parts[1].replace(',', '').strip()
            
            code.append(f"{indent}{dest} = {val_part};")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        args = [a for a in args if a != '->']

        if op == "CONST":
            val = args[0]
            dest = args[1]
            code.append(f"{indent}{dest} = {val};")

        elif op == "STORE":
            var = args[0]
            val = args[1]
            code.append(f"{indent}{var} = {val};")

        elif op == "LOAD":
            var = args[0]
            dest = args[1]
            code.append(f"{indent}{dest} = {var};")

        elif op == "LT":
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]};")

        elif op == "ADD":
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]};")

        elif op == "PRINT":
            code.append(f"{indent}console.log({args[0]}.toString());")

        elif op == "BR_FALSE":
            cond = args[0]
            label = args[1]
            code.append(f"{indent}if (!{cond}) {{")
            code.append(f"{indent}{self.indent}current_block = '{label}';")
            code.append(f"{indent}{self.indent}continue;")
            code.append(f"{indent}}}")

        elif op == "JUMP":
            label = args[0]
            code.append(f"{indent}current_block = '{label}';")
            code.append(f"{indent}continue;")

        elif op == "HALT":
            code.append(f"{indent}return;")

# Usage
as_gen = AssemblyScriptCodeGenerator()
as_gen.parse_ir(ir_instructions)
as_source = as_gen.generate()
print("\n--- Generated AssemblyScript Code (Dispatcher) ---\n")
print(as_source)


class RelooperCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.block_order = []
        self.indent = "  "

    def parse_ir(self, instructions):
        current_block = []
        current_name = "entry"
        self.block_order.append(current_name)
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if current_name:
                    self.blocks[current_name] = current_block
                current_name = parts[1]
                self.block_order.append(current_name)
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if current_name:
            self.blocks[current_name] = current_block

    def generate(self):
        code = []
        code.append("export function generated_program_optimized(): void {")
        code.append(f"{self.indent}// Initialize variables")
        code.append(f"{self.indent}var i: i32 = 0;")
        
        # Analyze loops (simple heuristic: block jumps to itself)
        loop_headers = set()
        for name, instrs in self.blocks.items():
            if instrs:
                last_instr = instrs[-1]
                parts = last_instr.split()
                if parts[0] == "JUMP" and parts[1] == name:
                    loop_headers.add(name)

        current_indent_level = 1

        for i, block_name in enumerate(self.block_order):
            instrs = self.blocks.get(block_name, [])
            indent = self.indent * current_indent_level

            # If this block is a loop header, start a loop
            if block_name in loop_headers:
                code.append(f"{indent}while (true) {{")
                current_indent_level += 1
                indent = self.indent * current_indent_level

            for line in instrs:
                self._emit_instruction(line, code, current_indent_level, block_name, loop_headers)

            # If this block was a loop header, close it
            if block_name in loop_headers:
                current_indent_level -= 1
                code.append(f"{self.indent * current_indent_level}}}")

        code.append("}")
        return "\n".join(code)

    def _emit_instruction(self, line, code, level, current_block_name, loop_headers):
        indent = self.indent * level
        
        # Handle CONST specially
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val_part = parts[0].strip()[5:].strip()
            if val_part.endswith(','): val_part = val_part[:-1]
            dest = parts[1].replace(',', '').strip()
            
            is_number = True
            try: float(val_part)
            except ValueError: is_number = False
            type_decl = "i32" if is_number else "string"
            code.append(f"{indent}let {dest}: {type_decl} = {val_part};")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        args = [a for a in args if a != '->']

        if op == "STORE":
            code.append(f"{indent}{args[0]} = {args[1]};")
        elif op == "LOAD":
            code.append(f"{indent}let {args[1]}: i32 = {args[0]};")
        elif op == "LT":
            code.append(f"{indent}let {args[2]}: boolean = {args[0]} < {args[1]};")
        elif op == "ADD":
            code.append(f"{indent}let {args[2]}: i32 = {args[0]} + {args[1]};")
        elif op == "PRINT":
            code.append(f"{indent}console.log({args[0]}.toString());")
        
        elif op == "BR_FALSE":
            cond = args[0]
            target = args[1]
            # If branching to exit, it's a break
            # We assume if we are in a loop header, and we branch elsewhere, it's a break
            if current_block_name in loop_headers:
                code.append(f"{indent}if (!{cond}) break;")
            else:
                # Fallback for non-loop branches (not fully implemented in this simple version)
                code.append(f"{indent}// Branch to {target} (not implemented in simple relooper)")

        elif op == "JUMP":
            target = args[0]
            if target == current_block_name:
                code.append(f"{indent}continue;")
            else:
                 # If jumping to next block, it's a no-op (fallthrough)
                 pass

        elif op == "HALT":
            code.append(f"{indent}return;")

# Usage Relooper
relooper = RelooperCodeGenerator()
relooper.parse_ir(ir_instructions)
relooper_source = relooper.generate()
print("\n--- Generated AssemblyScript Code (Relooper) ---\n")
print(relooper_source)


class PythonRelooperCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.block_order = []
        self.indent = "    "

    def parse_ir(self, instructions):
        current_block = []
        current_name = "entry"
        self.block_order.append(current_name)
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if current_name:
                    self.blocks[current_name] = current_block
                current_name = parts[1]
                self.block_order.append(current_name)
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if current_name:
            self.blocks[current_name] = current_block

    def generate(self):
        code = []
        code.append("def generated_program_optimized():")
        code.append(f"{self.indent}# Initialize variables")
        code.append(f"{self.indent}i = 0")
        
        # Analyze loops
        loop_headers = set()
        for name, instrs in self.blocks.items():
            if instrs:
                last_instr = instrs[-1]
                parts = last_instr.split()
                if parts[0] == "JUMP" and parts[1] == name:
                    loop_headers.add(name)

        current_indent_level = 1

        for i, block_name in enumerate(self.block_order):
            instrs = self.blocks.get(block_name, [])
            indent = self.indent * current_indent_level

            # If this block is a loop header, start a loop
            if block_name in loop_headers:
                code.append(f"{indent}while True:")
                current_indent_level += 1
                indent = self.indent * current_indent_level

            for line in instrs:
                self._emit_instruction(line, code, current_indent_level, block_name, loop_headers)

            # If this block was a loop header, close it (dedent)
            if block_name in loop_headers:
                current_indent_level -= 1

        return "\n".join(code)

    def _emit_instruction(self, line, code, level, current_block_name, loop_headers):
        indent = self.indent * level
        
        # Handle CONST specially
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val_part = parts[0].strip()[5:].strip()
            if val_part.endswith(','): val_part = val_part[:-1]
            dest = parts[1].replace(',', '').strip()
            code.append(f"{indent}{dest} = {val_part}")
            return

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = parts[1:]
        args = [a for a in args if a != '->']

        if op == "STORE":
            code.append(f"{indent}{args[0]} = {args[1]}")
        elif op == "LOAD":
            code.append(f"{indent}{args[1]} = {args[0]}")
        elif op == "LT":
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]}")
        elif op == "ADD":
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]}")
        elif op == "PRINT":
            code.append(f"{indent}print({args[0]})")
        
        elif op == "BR_FALSE":
            cond = args[0]
            target = args[1]
            if current_block_name in loop_headers:
                code.append(f"{indent}if not {cond}:")
                code.append(f"{indent}{self.indent}break")
            else:
                code.append(f"{indent}# Branch to {target} (not implemented)")

        elif op == "JUMP":
            target = args[0]
            if target == current_block_name:
                code.append(f"{indent}continue")
            else:
                 pass

        elif op == "HALT":
            code.append(f"{indent}return")

# Usage Python Relooper
py_relooper = PythonRelooperCodeGenerator()
py_relooper.parse_ir(ir_instructions)
py_relooper_source = py_relooper.generate()
print("\n--- Generated Python Code (Relooper) ---\n")
print(py_relooper_source)

print("\n--- Executing Optimized Python Code ---\n")
exec(py_relooper_source)
generated_program_optimized()








# Create Loop Node Network
# Define Nodes
# BEGIN LOOP NETWORK DEFINITION

network = NodeNetwork("LoopNetwork")
s = network.create_node('start_param', 'Parameter', 0)
#s = ParamNode('start', 'Parameter', 0)
e = network.create_node('end_param', 'Parameter', 5)
#e = ParamNode('end', 'Parameter', 5)
step = network.create_node('step_param', 'Parameter', 1)
#step = ParamNode('step', 'Parameter', 1)

loop = network.create_node('loop1', 'Loop')
#loop = LoopNode('loop1', 'Loop')

s.connect_output_to('value', loop, 'start')     # inputs to loop node
e.connect_output_to('value', loop, 'end')
step.connect_output_to('value', loop, 'step')   

const_5 = network.create_node('const_5', 'Parameter', 2)
#const_5= ParamNode('ifcompare', 'Parameter', 2)     # if index < 5
lessthan = LessThanNode('lessthan1', 'LessThan')
loop.connect_output_to('index', lessthan, 'a')
const_5.connect_output_to('value', lessthan, 'b')


ifnode = IfNode('ifnode1', 'If')
lessthan.connect_output_to('result', ifnode, 'condition')
loop.connect_output_to('body', ifnode, 'exec')


loopmessage = MessageNode('msgNode', 'Message')
ifnode.connect_output_to('true', loopmessage, 'exec')
loop.connect_output_to('index', loopmessage, 'msg')




print("Executing Loop Node Network:")

loop.get_input_control_port('exec').setValue(True)  # Trigger the loop

network.compute([loop])
# END LOOP NETWORK DEFINITION
#network.compute([loop])

print("\n--- Generating IR from Loop Node Network ---")
generator = IRGenerator()
generator.compile_control_flow(loop)
ir_instructions = generator.instructions
for instr in ir_instructions:
   print(instr)


print("\n--- Exiting ---")



# 1. Create the main NodeNetwork
network = NodeNetwork("MyNetwork")

# 2. Add the Control Input (Pass-through/Tunnel)
# This port allows control flow to enter the network and trigger internal nodes.
# Note: Using the method exactly as defined in your file (with the typo 'inputouput')
net_exec_port = network.add_control_input_port("exec")

# 3. Add the Param Data Input (Pass-through/Tunnel)
# This port allows data to be passed from outside the network to internal nodes.
net_data_port = network.add_data_input_port("param_input")

# 4. Create the internal Message Node
msg_node = network.createNode("internal_msg_node", "Message")
msg_node2 = network.createNode("internal_msg_node2", "Message")

# 5. Connect the Network's input ports to the internal Message Node's input ports.
# We use .connectTo() directly here because we are connecting an Input to an Input (Tunneling),
# whereas standard node connections are Output-to-Input.

# Connect Network Control Input -> Message Node Control Input
#net_exec_port.connectTo(msg_node.get_input_control_port("exec"))
#net_exec_port.connectTo(msg_node2.get_input_control_port("exec"))

network.connect_network_input_to("exec", msg_node, "exec")
network.connect_network_input_to("exec", msg_node2, "exec")

print("::")
print(net_exec_port.outgoing_connections[0].to_port.port_name)
print("::")
# Connect Network Data Input -> Message Node Data Input ('msg')
#net_data_port.connectTo(msg_node.get_input_data_port("msg"))
#net_data_port.connectTo(msg_node2.get_input_data_port("msg"))

network.connect_network_input_to("param_input", msg_node, "msg")
network.connect_network_input_to("param_input", msg_node2, "msg")

param_node= network.create_node("param_node", "Parameter", "Hello from Network!")
#param_node = ParamNode("param_node", "Parameter", "Hello from Network!")
param_node.connect_output_to("value", network, "param_input")



net_exec_port.activate() # Trigger the network execution
network.compute()

print("+++ Running Network Again +++")
print("next run")
net_exec_port.activate()
network.compute()

print("Network created successfully.")




"""sys.exit(0)"""


"""


# 2. Generate Python Code
py_gen = PythonCodeGenerator()
py_gen.parse_ir(ir_instructions)
python_source = py_gen.generate()

print("\n--- Generated Python Code (New Loop) ---\n")
print(python_source)

print("\n--- Executing Generated Python Code ---\n")
exec(python_source)
generated_program()

# 3. Generate AssemblyScript Code
as_gen = AssemblyScriptCodeGenerator()
as_gen.parse_ir(ir_instructions)
as_source = as_gen.generate()

print("\n--- Generated AssemblyScript Code (New Loop) ---\n")
print(as_source)


class AsyncSchedulerAssemblyScriptCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.block_order = []
        self.block_ids = {}
        self.indent = "  "

    def parse_ir(self, instructions):
        # 1. Parse into Blocks
        current_block = []
        current_name = "entry"
        self.block_order.append(current_name)
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if current_name:
                    self.blocks[current_name] = current_block
                current_name = parts[1]
                self.block_order.append(current_name)
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if current_name:
            self.blocks[current_name] = current_block

        # 2. Assign Numeric IDs to Blocks for Switch-Case
        for idx, name in enumerate(self.block_order):
            self.block_ids[name] = idx

    def generate(self):
        code = []
        code.append("// --- Async Scheduler Runtime ---")
        code.append("const taskQueue: i32[] = [];")
        code.append("function schedule(blockId: i32): void {")
        code.append(f"{self.indent}taskQueue.push(blockId);")
        code.append("}")
        code.append("")
        
        code.append("export function generated_program_async(): void {")
        code.append(f"{self.indent}// Global State (Context)")
        code.append(f"{self.indent}var i: i32 = 0;")
        
        # Declare Temps
        temp_vars = self._collect_temps()
        for var_name, var_type in sorted(temp_vars.items()):
            default_val = "0" if var_type == "i32" else "false"
            code.append(f"{self.indent}var {var_name}: {var_type} = {default_val};")

        code.append("")
        code.append(f"{self.indent}// Bootstrap")
        code.append(f"{self.indent}schedule({self.block_ids['entry']});")
        code.append("")
        code.append(f"{self.indent}// Scheduler Loop")
        code.append(f"{self.indent}while (taskQueue.length > 0) {{")
        code.append(f"{self.indent}{self.indent}const currentBlockId = taskQueue.shift();")
        code.append(f"{self.indent}{self.indent}switch (currentBlockId) {{")
        
        for i, block_name in enumerate(self.block_order):
            block_id = self.block_ids[block_name]
            instrs = self.blocks.get(block_name, [])
            
            # Identify Fallthrough Block (next in list)
            fallthrough_id = -1
            if i + 1 < len(self.block_order):
                fallthrough_id = self.block_ids[self.block_order[i+1]]

            code.append(f"{self.indent}{self.indent}{self.indent}case {block_id}: // {block_name}")
            
            # Emit Body
            has_scheduler_action = False
            for line in instrs:
                action = self._emit_instruction(line, code, 4, fallthrough_id)
                if action: has_scheduler_action = True

            # Handle implicit fallthrough if no Jump/Branch was emitted
            if not has_scheduler_action and fallthrough_id != -1:
                 code.append(f"{self.indent*4}schedule({fallthrough_id});")
            
            code.append(f"{self.indent*4}break;")
            

        code.append(f"{self.indent}{self.indent}}}") # End Switch
        code.append(f"{self.indent}}}") # End While
        code.append("}") # End Function
        return "\n".join(code)

    def _collect_temps(self):
        temp_vars = {}
        for instrs in self.blocks.values():
            for line in instrs:
                parts = [p.strip().replace(',', '') for p in line.split()]
                if not parts: continue
                op = parts[0]
                if '->' in parts:
                    idx = parts.index('->')
                    if idx + 1 < len(parts):
                        dest = parts[idx+1]
                        temp_vars[dest] = 'boolean' if op == 'LT' else 'i32'
        return temp_vars

    def _emit_instruction(self, line, code, level, fallthrough_id):
        indent = self.indent * level
        
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val = parts[0].strip()[5:].strip().rstrip(',')
            dest = parts[1].replace(',', '').strip()
            code.append(f"{indent}{dest} = {val};")
            return False

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = [a for a in parts[1:] if a != '->']

        if op == "STORE":
            code.append(f"{indent}{args[0]} = {args[1]};")
            return False
        elif op == "LOAD":
            code.append(f"{indent}{args[1]} = {args[0]};")
            return False
        elif op == "LT":
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]};")
            return False
        elif op == "ADD":
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]};")
            return False
        elif op == "PRINT":
            code.append(f"{indent}console.log({args[0]}.toString());")
            return False
        
        elif op == "BR_FALSE":
            cond = args[0]
            target_label = args[1]
            target_id = self.block_ids.get(target_label, -1)
            
            code.append(f"{indent}if (!{cond}) {{")
            code.append(f"{indent}{self.indent}schedule({target_id});")
            code.append(f"{indent}{self.indent}break;")
            code.append(f"{indent}}}")
            return False

        elif op == "JUMP":
            target_label = args[0]
            target_id = self.block_ids.get(target_label, -1)
            code.append(f"{indent}schedule({target_id});")
            return True

        elif op == "HALT":
            code.append(f"{indent}// End of flow")
            return True
            
        return False

# 4. Generate Async Scheduler Code
async_gen = AsyncSchedulerAssemblyScriptCodeGenerator()
async_gen.parse_ir(ir_instructions)
async_source = async_gen.generate()

print("\n--- Generated AssemblyScript Code (Async Scheduler) ---\n")
print(async_source)


class AsyncSchedulerPythonCodeGenerator:
    def __init__(self):
        self.blocks = {}
        self.block_order = []
        self.block_ids = {}
        self.indent = "    "

    def parse_ir(self, instructions):
        # 1. Parse into Blocks
        current_block = []
        current_name = "entry"
        self.block_order.append(current_name)
        
        for line in instructions:
            parts = line.split()
            op = parts[0]
            
            if op == "LABEL":
                if current_name:
                    self.blocks[current_name] = current_block
                current_name = parts[1]
                self.block_order.append(current_name)
                current_block = []
            elif op == "ENTRY":
                continue
            else:
                current_block.append(line)
        
        if current_name:
            self.blocks[current_name] = current_block

        # 2. Assign Numeric IDs to Blocks
        for idx, name in enumerate(self.block_order):
            self.block_ids[name] = idx

    def generate(self):
        code = []
        code.append("import collections")
        code.append("")
        code.append("# --- Async Scheduler Runtime (Python) ---")
        code.append("task_queue = collections.deque()")
        code.append("")
        code.append("def schedule(block_id):")
        code.append(f"{self.indent}task_queue.append(block_id)")
        code.append("")
        
        code.append("def generated_program_async_python():")
        code.append(f"{self.indent}# Global State (Context)")
        code.append(f"{self.indent}i = 0")
        
        # Declare Temps
        temp_vars = self._collect_temps()
        for var_name, var_type in sorted(temp_vars.items()):
            # In Python local vars don't strictly need declaration, but we'll init them 
            # to simulate state persistence across blocks (which would be on 'self' in a class)
            # However, since this whole function runs as a closure, they persist for the while loop scope.
            default_val = "0" if var_type == "i32" else "False"
            code.append(f"{self.indent}{var_name} = {default_val}")

        code.append("")
        code.append(f"{self.indent}# Bootstrap")
        code.append(f"{self.indent}schedule({self.block_ids['entry']})")
        code.append("")
        code.append(f"{self.indent}# Scheduler Loop")
        code.append(f"{self.indent}while task_queue:")
        code.append(f"{self.indent}{self.indent}current_block_id = task_queue.popleft()")
        code.append("")
        
        # Dispatcher
        if_keyword = "if"
        for i, block_name in enumerate(self.block_order):
            block_id = self.block_ids[block_name]
            code.append(f"{self.indent}{self.indent}{if_keyword} current_block_id == {block_id}: # {block_name}")
            if_keyword = "elif"
            
            instrs = self.blocks.get(block_name, [])
            
            # Identify Fallthrough Block
            fallthrough_id = -1
            if i + 1 < len(self.block_order):
                fallthrough_id = self.block_ids[self.block_order[i+1]]

            has_scheduler_action = False
            stmts_start = len(code)

            for line in instrs:
                action = self._emit_instruction(line, code, 3, fallthrough_id)
                if action: has_scheduler_action = True

            # Handle implicit fallthrough
            if not has_scheduler_action and fallthrough_id != -1:
                 code.append(f"{self.indent*3}schedule({fallthrough_id})")
                 has_scheduler_action = True

            if len(code) == stmts_start:
                code.append(f"{self.indent*3}pass")
            
        return "\n".join(code)

    def _collect_temps(self):
        temp_vars = {}
        for instrs in self.blocks.values():
            for line in instrs:
                parts = [p.strip().replace(',', '') for p in line.split()]
                if not parts: continue
                op = parts[0]
                if '->' in parts:
                    idx = parts.index('->')
                    if idx + 1 < len(parts):
                        dest = parts[idx+1]
                        temp_vars[dest] = 'boolean' if op == 'LT' else 'i32'
        return temp_vars

    def _emit_instruction(self, line, code, level, fallthrough_id):
        indent = self.indent * level
        
        if line.strip().startswith("CONST"):
            parts = line.split('->')
            val = parts[0].strip()[5:].strip().rstrip(',')
            dest = parts[1].replace(',', '').strip()
            code.append(f"{indent}{dest} = {val}")
            return False

        parts = [p.strip().replace(',', '') for p in line.split()]
        op = parts[0]
        args = [a for a in parts[1:] if a != '->']

        if op == "STORE":
            code.append(f"{indent}{args[0]} = {args[1]}")
            return False
        elif op == "LOAD":
            code.append(f"{indent}{args[1]} = {args[0]}")
            return False
        elif op == "LT":
            code.append(f"{indent}{args[2]} = {args[0]} < {args[1]}")
            return False
        elif op == "ADD":
            code.append(f"{indent}{args[2]} = {args[0]} + {args[1]}")
            return False
        elif op == "PRINT":
            code.append(f"{indent}print({args[0]})")
            return False
        
        elif op == "BR_FALSE":
            cond = args[0]
            target_label = args[1]
            target_id = self.block_ids.get(target_label, -1)
            
            code.append(f"{indent}if not {cond}:")
            code.append(f"{indent}{self.indent}schedule({target_id})")
            code.append(f"{indent}{self.indent}continue")
            
            # If true, we just fall through to the next instruction in this block
            # No 'else' needed here because we 'continue'd on the if branch
            return False # We return False so the outer loop knows we didn't terminate the block UNCONDITIONALLY

        elif op == "JUMP":
            target_label = args[0]
            target_id = self.block_ids.get(target_label, -1)
            code.append(f"{indent}schedule({target_id})")
            code.append(f"{indent}continue")
            return True

        elif op == "HALT":
            code.append(f"{indent}return")
            return True
            
        return False

# 5. Generate Async Scheduler Code (Python)
async_py_gen = AsyncSchedulerPythonCodeGenerator()
async_py_gen.parse_ir(ir_instructions)
async_py_source = async_py_gen.generate()

print("\n--- Generated Python Code (Async Scheduler) ---\n")
print(async_py_source)

print("\n--- Executing Async Python Code ---\n")
exec(async_py_source)


"""