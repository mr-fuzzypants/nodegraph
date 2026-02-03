
class AssemblyScriptGenerator:
    """
    Generates AssemblyScript code from Linear IR.
    Supports:
    1. Extism Host Bindings (RabbitMQ)
    2. Basic Block Control Flow (Switch-Dispatcher for Loops/Ifs)
    3. Math and Logic Opcodes
    """
    def __init__(self, debug=False):
        self.debug = debug
        self.indent = 0
        self.lines = []

    def _add(self, line):
        self.lines.append("  " * self.indent + line)

    def generate(self, builder) -> str:
        self.lines = []
        self._add("// ==========================================")
        self._add("//  Generated AssemblyScript (Optimized)")
        self._add("// ==========================================")
        self._add("")
        
        # 1. Imports
        self._add("// Host Functions")
        self._add('@external("extism:host/user", "host_rabbitmq_publish")')
        self._add('declare function host_rabbitmq_publish(q_ptr: u64, q_len: u64, msg_ptr: u64, msg_len: u64): void;')
        self._add('@external("extism:host/env", "input_offset")')
        self._add('declare function extism_input_offset(): u64;')
        self._add('@external("extism:host/env", "input_length")')
        self._add('declare function extism_input_length(): u64;')
        self._add('@external("extism:host/env", "alloc")')
        self._add('declare function extism_alloc(len: u64): u64;')
        # Generic log for debugging
        self._add('@external("extism:host/user", "log")')
        self._add('declare function log(val: u64): void;')
        
        self._add("")

        instructions = builder.instructions
        
        # Split instructions into functions
        # If no FUNCTION_START, treat whole list as 'run' (or main)
        functions = [] # List of (name, args, instrs)
        current_instrs = []
        current_func_info = ("run", []) # Default
        
        for instr in instructions:
            if instr[0] == "FUNCTION_START":
                # Save previous info if it has instructions (and isn't the empty default run start)
                if current_instrs:
                     functions.append((current_func_info[0], current_func_info[1], current_instrs))
                
                current_instrs = []
                # Name, ArgVar
                func_name = instr[1]
                arg_var = instr[2] if len(instr) > 2 else None
                current_func_info = (func_name, [arg_var] if arg_var else [])
            else:
                current_instrs.append(instr)
        
        # Append last function
        if current_instrs:
             functions.append((current_func_info[0], current_func_info[1], current_instrs))

        # Generate each function
        for f_name, f_args, f_instrs in functions:
            self._generate_function(f_name, f_args, f_instrs)
            self._add("")

        return "\n".join(self.lines)

    def _generate_function(self, name, args, instructions):
        # Determine variable types
        var_types = {}
        # Pre-seed arguments as strings for this demo context
        for a in args:
             if a: var_types[a] = "string"

        # Simple type inference pass
        for instr in instructions:
            op = instr[0]
            if op == "CONST":
                 # CONST val -> dest
                 val, dest = instr[1], instr[3]
                 if isinstance(val, (int, float)): var_types[dest] = "f64"
                 elif isinstance(val, bool): var_types[dest] = "bool"
                 else: var_types[dest] = "string"
            elif op == "ADD" or op == "SUB" or op == "MUL":
                 if len(instr) >= 5: dest = instr[4]
                 elif len(instr) == 4: dest = instr[3]
                 else: dest = None
                 
                 if dest: var_types[dest] = "f64"
            elif op == "CMP_LT" or op == "CMP_GE":
                 if len(instr) >= 5: dest = instr[4]
                 elif len(instr) == 4: dest = instr[3]
                 else: dest = None
                 
                 if dest: var_types[dest] = "bool"
            elif op == "CALL_HOST":
                 pass # usually consumes vars

        # === Basic Block Analysis ===
        block_starts = {0}
        label_to_instr_index = {}
        variables = set()

        for i, instr in enumerate(instructions):
            op = instr[0]
            if op == "LABEL":
                block_starts.add(i)
                label_to_instr_index[instr[1]] = i
            
            if op in ["JMP", "JMP_IF_TRUE", "JMP_IF_FALSE", "HALT", "RETURN"]:
                if i + 1 < len(instructions):
                    block_starts.add(i + 1)
            
            # Collect vars
            for part in instr:
                 if isinstance(part, str) and part.startswith("t") and part[1:].isdigit():
                      variables.add(part)

        sorted_starts = sorted(list(block_starts))
        blocks = []
        instr_index_to_block_id = {}
        for i in range(len(sorted_starts)):
            start_idx = sorted_starts[i]
            end_idx = sorted_starts[i+1] if i + 1 < len(sorted_starts) else len(instructions)
            blocks.append({
                "id": i,
                "start_idx": start_idx,
                "instrs": instructions[start_idx:end_idx]
            })
            for k in range(start_idx, end_idx): instr_index_to_block_id[k] = i
        
        # === Emit Function ===
        self._add(f"export function {name}(): i32 {{")
        self.indent += 1
        
        # 1. Locals
        self._add(f"let pc: i32 = 0;")
        self._add(f"let flag: boolean = false;") # For condition results
        
        # Declare vars with inferred types
        for var in sorted(list(variables)):
            vtype = var_types.get(var, "string") # Default to string for RabbitMQ demo if unknown
            if vtype == "f64":
                 self._add(f"let {var}: f64 = 0.0;")
            elif vtype == "bool":
                 self._add(f"let {var}: boolean = false;")
            else:
                 self._add(f"let {var}: string = \"\";")

        # 2. Argument Decoding (Specific to RabbitMQ/Extism demo structure)
        if args and args[0]: # If there's an input arg
             arg_var = args[0]
             self._add(f"let ptr = extism_input_offset();")
             self._add(f"let len = extism_input_length();")
             self._add(f"{arg_var} = String.UTF8.decodeUnsafe(ptr as usize, len as usize);")
             # self._add(f"{arg_var} = \"HARDCODED\";")

        # 3. Dispatch Loop
        self._add("while (true) {")
        self.indent += 1
        self._add("switch (pc) {")
        self.indent += 1

        for block in blocks:
            b_id = block['id']
            b_instrs = block['instrs']
            self._add(f"case {b_id}: {{ // Block at {block['start_idx']}")
            self.indent += 1
            
            for instr in b_instrs:
                op = instr[0]
                self._add(f"// {str(instr)}")
                
                if op == "LABEL":
                     pass

                elif op == "CONST":
                     val, dest = instr[1], instr[3]
                     if var_types.get(dest) == "string":
                          self._add(f"{dest} = \"{val}\";")
                     else:
                          # Boolean or Number
                          v_str = str(val).lower() if isinstance(val, bool) else str(val)
                          self._add(f"{dest} = {v_str};")

                elif op == "MOVE" or op == "ASSIGN":
                     # MOVE src dest  OR  ASSIGN dest src (IRBuilder uses ASSIGN)
                     if op == "ASSIGN":
                          dest, src = instr[1], instr[2]
                     else:
                          src, dest = instr[1], instr[2]
                     self._add(f"{dest} = {src};")
                
                elif op == "CALL_HOST":
                    target, p1, p2 = instr[1], instr[2], instr[3]
                    print("DEBUG: Generating CALL_HOST to", target, p1, p2)
                    if target == "rabbitmq_publish":
                        # Encode queue
                        self._add(f"let q_buf = String.UTF8.encode({p1});")
                        self._add(f"let q_arr = Uint8Array.wrap(q_buf);")
                        self._add(f"let q_len = q_buf.byteLength;")
                        self._add(f"let q_ptr_ext = extism_alloc(q_len);")
                        self._add(f"memory.copy(q_ptr_ext as usize, q_arr.dataStart, q_len);")

                        # Encode payload
                        self._add(f"let m_buf = String.UTF8.encode({p2});")
                        self._add(f"let m_arr = Uint8Array.wrap(m_buf);")
                        self._add(f"let m_len = m_buf.byteLength;")
                        self._add(f"let m_ptr_ext = extism_alloc(m_len);")
                        self._add(f"memory.copy(m_ptr_ext as usize, m_arr.dataStart, m_len);")
                        
                        # Pass Extism pointers
                        self._add(f"host_rabbitmq_publish(q_ptr_ext, q_len as u64, m_ptr_ext, m_len as u64);")
                        self._add("log(22)")  # Debug log after publish
                elif op == "ADD":
                     # ADD a b -> res
                     if len(instr) >= 5: a,b,res = instr[1], instr[2], instr[4]
                     else: a,b,res = instr[1], instr[2], instr[3]
                     self._add(f"{res} = {a} + {b};")

                elif op == "CMP_LT":
                     if len(instr) >= 5: 
                         a,b,res = instr[1], instr[2], instr[4]
                         self._add(f"{res} = ({a} < {b});")
                     elif len(instr) == 4: 
                         a,b,res = instr[1], instr[2], instr[3]
                         self._add(f"{res} = ({a} < {b});")
                     else:
                         a,b = instr[1], instr[2]
                         self._add(f"flag = ({a} < {b});")
                
                elif op == "CMP_GE":
                     if len(instr) >= 5: 
                         a,b,res = instr[1], instr[2], instr[4]
                         self._add(f"{res} = ({a} >= {b});")
                     elif len(instr) == 4: 
                         a,b,res = instr[1], instr[2], instr[3]
                         self._add(f"{res} = ({a} >= {b});")
                     else:
                         a,b = instr[1], instr[2]
                         self._add(f"flag = ({a} >= {b});")

                elif op == "TEST":
                     # TEST var
                     var = instr[1]
                     # Check if boolean
                     if var_types.get(var) == "bool":
                          self._add(f"flag = {var};")
                     else:
                          self._add(f"flag = ({var} != 0.0);")

                elif op == "JMP":
                     target_idx = label_to_instr_index.get(instr[1], 0)
                     target_blk = instr_index_to_block_id.get(target_idx, 0)
                     self._add(f"pc = {target_blk};")
                     self._add("break;")

                elif op == "JMP_IF_TRUE":
                     target_idx = label_to_instr_index.get(instr[1], 0)
                     target_blk = instr_index_to_block_id.get(target_idx, 0)
                     next_blk = b_id + 1
                     self._add(f"if (flag) {{ pc = {target_blk}; }} else {{ pc = {next_blk}; }}")
                     self._add("break;")

                elif op == "JMP_IF_FALSE":
                     target_idx = label_to_instr_index.get(instr[1], 0)
                     target_blk = instr_index_to_block_id.get(target_idx, 0)
                     next_blk = b_id + 1
                     self._add(f"if (!flag) {{ pc = {target_blk}; }} else {{ pc = {next_blk}; }}")
                     self._add("break;")

                elif op == "HALT" or op == "RETURN":
                     self._add("return 0;")
            
            # End of block: Implicit fallthrough if not ended
            last_op = b_instrs[-1][0] if b_instrs else None
            if last_op not in ["JMP", "JMP_IF_TRUE", "JMP_IF_FALSE", "HALT", "RETURN"]:
                 self._add(f"pc = {b_id + 1};")
                 self._add("break;")

            self.indent -= 1
            self._add("}") # End Case

        self._add("default:")
        self._add("  return 0;")
        
        self.indent -= 1
        self._add("}") # End Switch

        self.indent -= 1
        self._add("}") # End While
        
        self._add("return 0;")
        self.indent -= 1
        self._add("}")

