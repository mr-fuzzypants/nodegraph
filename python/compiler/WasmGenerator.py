import json

class WasmGenerator:
    """
    Generates WebAssembly Text Format (WAT) from the Linear IR.
    Uses a 'Program Counter' dispatcher loop and `br_table` to simulate unstructured jumps
    efficiently in Wasm's structured control flow.
    """
    def __init__(self, debug=False):
        self.debug = debug

    def generate(self, builder) -> str:
        instructions = builder.instructions
        
        # 1. Pass 1: Collect Labels, Variables, and Map Instructions
        labels = {}
        variables = set()
        
        # Variable extraction
        for i, instr in enumerate(instructions):
            op = instr[0]
            if op == "LABEL":
                labels[instr[1]] = i
            
            # Extract potential variables (starting with 't')
            for part in instr:
                if isinstance(part, str) and (part.startswith("t") and part[1:].isdigit()):
                    variables.add(part)
        
        # Sort vars to ensure deterministic order
        sorted_vars = sorted(list(variables))
        
        # 2. Start Generating WAT
        lines = []
        lines.append('(module')
        lines.append('  ;; Connect to host for logging')
        lines.append('  (import "env" "log" (func $log (param f64)))')
        # lines.append('  (import "env" "print_str" (func $print_str (param i32 i32)))') # Future: strings
        lines.append('  (memory 1)')
        lines.append('  (export "memory" (memory 0))')
        
        lines.append('  (func $run (export "run")')
        lines.append('    (local $pc i32)')
        lines.append('    (local $flag i32)') # Boolean flag for comparisons
        
        # Declare all data variables as f64 (simplification)
        for var in sorted_vars:
            lines.append(f'    (local ${var} f64)')
            
        lines.append('')
        lines.append('    ;; --- Execution Loop ---')
        lines.append('    (loop $main_loop')
        
        # 3. Create instruction dispatch structure using nested blocks
        # Pattern:
        # (block $instr_N
        #   ... 
        #   (block $instr_1
        #     (block $instr_0
        #       (br_table $instr_0 $instr_1 ... $instr_N (local.get $pc))
        #     ) ;; end $instr_0, fallthrough to code for 0
        #     ;; CODE FOR INSTR 0
        #     (local.set $pc (i32.const 1))
        #     (br $main_loop)
        #   ) ;; end $instr_1, fallthrough to code for 1
        #   ;; CODE FOR INSTR 1
        #   ...
        # )
        
        # A. Open Blocks (Reverse order nesting)
        num_instr = len(instructions)
        default_label = f"$instr_default" # Should not happen if PC is correct
        
        # We need a list of labels for br_table in index order: 0, 1, 2...
        br_targets = [f"$instr_{i}" for i in range(num_instr)]
        br_targets_str = " ".join(br_targets)
        
        # Limit nesting if too deep? Wasm allows deep nesting mostly, 
        # but thousands of blocks might be extreme. For a demo it's fine.
        
        for i in reversed(range(num_instr)):
             lines.append(f'    (block $instr_{i}')
             
        # Dispatcher
        lines.append(f'      (br_table {br_targets_str} {br_targets[0]} (local.get $pc))')
        
        # B. Close Blocks and emit code
        for i, instr in enumerate(instructions):
            op = instr[0]
            
            # Close the block for this instruction (Pass control here)
            lines.append(f'    ) ;; Target for $instr_{i}') 
            
            lines.append(f'      ;; {i}: {instr}')
            
            # --- Instruction Implementation ---
            
            if op == "LABEL":
                # No-op
                pass
                
            elif op == "CONST":
                # ("CONST", val, "->", target)
                val = instr[1]
                target = instr[3]
                try:
                     # Wasm only supports numbers in this simple gen
                    float_val = float(val)
                    lines.append(f'      (local.set ${target} (f64.const {float_val}))')
                except ValueError:
                    # Pass 0.0 for strings/objects for now
                    lines.append(f'      ;; WARN: Skipped non-numeric CONST {val}')
                    lines.append(f'      (local.set ${target} (f64.const 0.0))')

            elif op == "MOVE":
                # ("MOVE", src, dst)
                src = instr[1]
                dst = instr[2]
                lines.append(f'      (local.set ${dst} (local.get ${src}))')

            elif op == "ADD":
                # ("ADD", a, b, "->", dst)
                # Note: node.py emits "->" before dst, IRBuilder example showed: ("ADD", a, b, dst) in PythonGen?
                # Let's check IRBuilder usage in PythonGenerator: 
                #   elif op == "ADD": a = instr[1]; b = instr[2]; dst = instr[3]
                # But NodeRegistry's compile says: builder.emit("ADD", var_a, var_b, "->", result_var)
                # This suggests PythonGenerator was reading index 3, but tuple has 5 items? 
                #   ("ADD", a, b, "->", dst) -> index 4 is dst!
                #   Wait, PythonGenerator snippet:
                #     dst = instr[3] 
                #     If instr is ("ADD", a, b, "->", dst), instr[3] is "->".
                #     So PythonGenerator is likely BROKEN for the NodeRegistry output or vice versa.
                #     Let's look at `NodeRegistry.py` again: `builder.emit("ADD", var_a, var_b, "->", result_var)`
                #     Tuple len is 5. dst is at index 4.
                #     Let's look at `PythonGenerator.py` again: `dst = instr[3]`
                #     Wait, `instr` is parts split by space? NO, it's a tuple from IRBuilder.
                #
                #     I will assume the NodeRegistry format is correct ("->", dst at 4) 
                #     and try to robustly find the dest or adapt.
                #     If I see "->" at index 3, then dst is index 4.
                
                # Robust extraction
                if len(instr) >= 5 and instr[3] == "->":
                    a, b, dst = instr[1], instr[2], instr[4]
                elif len(instr) == 4:
                    a, b, dst = instr[1], instr[2], instr[3]
                else:
                    a, b, dst = instr[1], instr[2], "UNKNOWN"

                lines.append(f'      (local.set ${dst} (f64.add (local.get ${a}) (local.get ${b})))')

            elif op == "PRINT" or op == "LOG":
                # ("PRINT", val)
                val = instr[1]
                lines.append(f'      (call $log (local.get ${val}))')
            
            elif op == "CMP_GE":
                # ("CMP_GE", a, b) -> Flag
                a = instr[1]
                b = instr[2]
                lines.append(f'      (local.set $flag (f64.ge (local.get ${a}) (local.get ${b})))')
            
            elif op == "CMP_LT":
                 # ("CMP_LT", a, b, "->", dst)
                if len(instr) >= 5 and instr[3] == "->":
                    a, b, dst = instr[1], instr[2], instr[4]
                else:
                    a, b, dst = instr[1], instr[2], instr[3]
                
                # Wasm comparisons return i32 (0 or 1). Cast to f64 for storage?
                # Data types are ANY/f64. 
                lines.append(f'      (local.set ${dst} (f64.promote_f32 (f32.convert_i32_s (f64.lt (local.get ${a}) (local.get ${b})))))')
                # Wait, simpler: (f64.convert_i32_s ...)
                lines.append(f'      (local.set ${dst} (f64.convert_i32_s (f64.lt (local.get ${a}) (local.get ${b}))))')

            elif op == "TEST":
                # ("TEST", val) -> Flag
                val = instr[1]
                # $flag = (val != 0.0)
                lines.append(f'      (local.set $flag (f64.ne (local.get ${val}) (f64.const 0.0)))')

            elif op == "JMP":
                # ("JMP", label)
                label = instr[1]
                target_pc = labels.get(label, 0)
                lines.append(f'      (local.set $pc (i32.const {target_pc}))')
                lines.append(f'      (br $main_loop)')
                continue # Skip the default PC increment

            elif op == "JMP_IF_TRUE":
                # ("JMP_IF_TRUE", label)
                label = instr[1]
                target_pc = labels.get(label, 0)
                lines.append(f'      (if (local.get $flag)')
                lines.append(f'        (then')
                lines.append(f'          (local.set $pc (i32.const {target_pc}))')
                lines.append(f'          (br $main_loop)')
                lines.append(f'        )')
                lines.append(f'      )')

            elif op == "JMP_IF_FALSE":
                # ("JMP_IF_FALSE", label)
                label = instr[1]
                target_pc = labels.get(label, 0)
                lines.append(f'      (if (i32.eqz (local.get $flag))')
                lines.append(f'        (then')
                lines.append(f'          (local.set $pc (i32.const {target_pc}))')
                lines.append(f'          (br $main_loop)')
                lines.append(f'        )')
                lines.append(f'      )')
            
            elif op == "HALT":
                 lines.append(f'      (return)')

            # Auto-Advance PC (Fallthrough)
            if i < len(instructions) - 1:
                lines.append(f'      (local.set $pc (i32.const {i + 1}))')
                lines.append(f'      (br $main_loop)')
            else:
                 # End of program
                 lines.append(f'      (return)')

        lines.append('    ) ;; end loop $main_loop')
        lines.append('  )')
        lines.append(')')
        
        return "\n".join(lines)
