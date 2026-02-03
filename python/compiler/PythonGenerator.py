
import sys

class PythonGenerator:
    """
    Generates Executable Python code from the Linear IR.
    Uses an Optimized Basic Block Dispatcher to reduce loop overhead.
    """
    def __init__(self, debug=False):
        self.debug = debug

    def generate(self, builder) -> str:
        instructions = builder.instructions
        
        # --- Pass 1: Identify Basic Block Boundaries ---
        block_starts = {0}
        label_to_instr_index = {}
        variables = set()
        
        for i, instr in enumerate(instructions):
            op = instr[0]
            if op == "LABEL":
                block_starts.add(i)
                label_to_instr_index[instr[1]] = i
            
            # Control flow ops end a block
            if op in ["JMP", "JMP_IF_TRUE", "JMP_IF_FALSE", "HALT"]:
                if i + 1 < len(instructions):
                    block_starts.add(i + 1)
            
            # Variable extraction
            for part in instr:
                if isinstance(part, str) and (part.startswith("t") and part[1:].isdigit()):
                    variables.add(part)

        sorted_starts = sorted(list(block_starts))
        
        # --- Pass 2: Create Basic Blocks ---
        blocks = []
        instr_index_to_block_id = {} 

        for i in range(len(sorted_starts)):
            start_idx = sorted_starts[i]
            end_idx = sorted_starts[i+1] if i + 1 < len(sorted_starts) else len(instructions)
            
            block_instrs = instructions[start_idx:end_idx]
            block_id = i
            blocks.append({
                "id": block_id,
                "start_idx": start_idx,
                "instrs": block_instrs
            })
            for k in range(start_idx, end_idx):
                instr_index_to_block_id[k] = block_id

        # --- Pass 3: Generate Code ---
        lines = []
        lines.append("import sys")
        lines.append("")
        lines.append("def run_program():")
        lines.append("    # --- Variables ---")
        for var in sorted(list(variables)):
            lines.append(f"    {var} = None")
        lines.append("    __flag = False")
        lines.append("")
        lines.append("    # --- Execution Loop ---")
        lines.append("    pc = 0")
        lines.append("    while True:")
        
        # Use if/elif chain for block dispatch (Faster than O(N) sequential ifs)
        # Note: In Python 3.10+, match/case would be cleaner
        for idx, block in enumerate(blocks):
            b_id = block["id"]
            if idx == 0:
                lines.append(f"        if pc == {b_id}:")
            else:
                lines.append(f"        elif pc == {b_id}:")
            
            for i, instr in enumerate(block["instrs"]):
                op = instr[0]
                lines.append(f"            # {instr}")
                
                if op == "LABEL":
                    pass

                elif op == "CONST":
                    lines.append(f"            {instr[3]} = {repr(instr[1])}")

                elif op == "MOVE":
                    lines.append(f"            {instr[2]} = {instr[1]}")

                elif op == "ADD":
                    # Robust check
                    if len(instr) >= 5 and instr[3] == "->":
                        a, b, dst = instr[1], instr[2], instr[4]
                    else:
                        a, b, dst = instr[1], instr[2], instr[3]
                    lines.append(f"            {dst} = {a} + {b}")

                elif op == "PRINT":
                    lines.append(f"            print({instr[1]})")
                
                elif op == "LOG":
                    lines.append(f"            print('LOG:', {instr[1]})")

                elif op == "CMP_GE":
                    lines.append(f"            __flag = ({instr[1]} >= {instr[2]})")
                
                elif op == "CMP_LT":
                    if len(instr) >= 5 and instr[3] == "->":
                         a, b, dst = instr[1], instr[2], instr[4]
                    else:
                         a, b, dst = instr[1], instr[2], instr[3]
                    lines.append(f"            {dst} = ({a} < {b})")

                elif op == "TEST":
                    lines.append(f"            __flag = bool({instr[1]})")

                elif op == "JMP":
                    label = instr[1]
                    target_idx = label_to_instr_index.get(label)
                    target_block = instr_index_to_block_id.get(target_idx, 0)
                    lines.append(f"            pc = {target_block}")
                    lines.append(f"            continue")

                elif op == "JMP_IF_TRUE":
                    label = instr[1]
                    target_idx = label_to_instr_index.get(label)
                    target_block = instr_index_to_block_id.get(target_idx, 0)
                    next_block = b_id + 1
                    lines.append(f"            if __flag:")
                    lines.append(f"                pc = {target_block}")
                    lines.append(f"            else:")
                    lines.append(f"                pc = {next_block}")
                    lines.append(f"            continue")

                elif op == "JMP_IF_FALSE":
                    label = instr[1]
                    target_idx = label_to_instr_index.get(label)
                    target_block = instr_index_to_block_id.get(target_idx, 0)
                    next_block = b_id + 1
                    lines.append(f"            if not __flag:")
                    lines.append(f"                pc = {target_block}")
                    lines.append(f"            else:")
                    lines.append(f"                pc = {next_block}")
                    lines.append(f"            continue")
                
                elif op == "HALT":
                    lines.append("            return")

            # Block fallthrough
            last_op = block["instrs"][-1][0] if block["instrs"] else "None"
            if last_op not in ["JMP", "JMP_IF_TRUE", "JMP_IF_FALSE", "HALT"]:
                # If we are at the last block, simple break/return
                if idx == len(blocks) - 1:
                    lines.append("            return")
                else:
                    lines.append(f"            pc = {b_id + 1}")
                    # Usually no 'continue' needed if we trust the if/elif chain to end here,
                    # but inside a while loop, we just loop again.
        
        lines.append("")
        lines.append("if __name__ == '__main__':")
        lines.append("    run_program()")
        
        return "\n".join(lines)

