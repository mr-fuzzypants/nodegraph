"""
NodeGraph Compiler v2 — Python Source Emitter
==============================================
Converts an IRSchedule into a complete, standalone Python source file.

Output structure
----------------
    #!/usr/bin/env python3
    # AUTO-GENERATED …
    from __future__ import annotations
    import asyncio, os
    from dotenv import load_dotenv
    load_dotenv()

    # ── Preambles (tools, helper generators) ─────
    <NodeTemplate.preamble() for each unique type>

    # ── Graph: <graph_name> ───────────────────────
    async def run():
        # preamble nodes (constants, data nodes)
        <emit_inline for each preamble ScheduledNode>

        # [LoopBlock] or [SequenceBlock]
        <block emission>

    if __name__ == "__main__":
        asyncio.run(run())

Loop emission (LoopBlock)
-------------------------
    # initialise output variables
    agent_step_type = ""
    …
    async for _step in <loop_expr>:
        <emit_loop_break>       # unpack + break-on-final
        <emit_inline body[0]>  # e.g. StepPrinterNode
        …
    <emit_inline post[0]>      # e.g. PrintNode
    …
"""

from __future__ import annotations

import datetime
from typing import List, Set

from .ir import IRGraph
from .scheduler import IRSchedule, LoopBlock, ScheduledNode, SequenceBlock
from .templates import CodeWriter, NodeTemplate, get_template


# ── File header ───────────────────────────────────────────────────────────────

def _header(graph_name: str) -> List[str]:
    today = datetime.date.today().isoformat()
    return [
        "#!/usr/bin/env python3",
        '"""',
        f"Compiled from NodeGraph: {graph_name}",
        f"Generated:  {today}",
        "",
        "This file was produced by nodegraph.python.compiler2.",
        "Do not edit by hand — re-run compile_graph() to regenerate.",
        '"""',
        "from __future__ import annotations",
        "",
        "import asyncio",
        "import os",
        "",
        "try:",
        "    from dotenv import load_dotenv",
        "    load_dotenv()",
        "except ImportError:",
        "    pass  # dotenv optional",
        "",
    ]


# ── Preamble deduplication ────────────────────────────────────────────────────

def _collect_preambles(schedule: IRSchedule) -> List[str]:
    """
    Call NodeTemplate.preamble() for each unique node type encountered in
    the schedule.  Each type is processed at most once.
    """
    seen: Set[str] = set()
    lines: List[str] = []

    def _maybe_preamble(snode: ScheduledNode) -> None:
        if snode.type_name in seen:
            return
        seen.add(snode.type_name)
        tmpl = get_template(snode.type_name)
        p = tmpl.preamble(snode)
        if p:
            lines.extend(p)
            lines.append("")

    for snode in schedule.preamble:
        _maybe_preamble(snode)

    for block in schedule.blocks:
        if isinstance(block, LoopBlock):
            _maybe_preamble(block.driver)
            for snode in block.body:
                _maybe_preamble(snode)
            for snode in block.post:
                _maybe_preamble(snode)
        elif isinstance(block, SequenceBlock):
            for snode in block.nodes:
                _maybe_preamble(snode)

    return lines


# ── Initialise loop-driver output variables ──────────────────────────────────

def _loop_driver_inits(driver: ScheduledNode, writer: CodeWriter) -> None:
    """
    Emit zero-value initialisations for all data output ports of a loop driver.
    These variables are updated inside the loop on each iteration.
    """
    for port_name, var_name in driver.output_vars.items():
        # skip control ports
        port = driver.output_vars.get(port_name)
        if port_name in ("loop_body", "completed"):
            continue
        if port_name in ("next", "true_out", "false_out"):
            continue
        # Infer a sensible zero value from the variable name.
        # Only use 0 for explicitly numeric ports; default to "".
        if port_name.endswith("_count") or port_name.endswith("_index") or port_name == "count":
            init = "0"
        else:
            init = '""'
        writer.writeln(f"{var_name} = {init}")


# ── Block emitters ────────────────────────────────────────────────────────────

def _emit_loop_block(block: LoopBlock, writer: CodeWriter) -> None:
    """Emit: init vars → async for _step → body → post."""
    driver = block.driver
    tmpl   = get_template(driver.type_name)

    writer.comment(f"Node: {driver.node_name} ({driver.type_name})")
    _loop_driver_inits(driver, writer)
    writer.blank()

    loop_expr = tmpl.emit_loop_expr(driver)
    writer.writeln(f"async for _step in {loop_expr}:")
    writer.push()

    # unpack step fields + break condition
    tmpl.emit_loop_break(driver, writer)
    writer.blank()

    # body nodes (loop_body branch)
    for snode in block.body:
        get_template(snode.type_name).emit_inline(snode, writer)
        writer.blank()

    writer.pop()  # end loop

    # post nodes (completed branch)
    for snode in block.post:
        writer.blank()
        get_template(snode.type_name).emit_inline(snode, writer)


def _emit_sequence_block(block: SequenceBlock, writer: CodeWriter) -> None:
    for snode in block.nodes:
        get_template(snode.type_name).emit_inline(snode, writer)
        writer.blank()


# ── Main run function ─────────────────────────────────────────────────────────

def _run_function(schedule: IRSchedule) -> List[str]:
    w = CodeWriter(indent=0)
    w.writeln(f"# ── Graph: {schedule.graph_name} {'─' * max(0, 50 - len(schedule.graph_name))}")
    w.writeln("async def run() -> None:")
    w.push()

    # ── Preamble nodes (constants, upstream data nodes) ────────────────
    if schedule.preamble:
        for snode in schedule.preamble:
            get_template(snode.type_name).emit_inline(snode, w)
            w.blank()

    # ── Execution blocks ───────────────────────────────────────────────
    for block in schedule.blocks:
        if isinstance(block, LoopBlock):
            _emit_loop_block(block, w)
        elif isinstance(block, SequenceBlock):
            _emit_sequence_block(block, w)

    if not schedule.preamble and not schedule.blocks:
        w.writeln("pass  # empty graph")

    w.pop()
    return w.lines()


# ── Entrypoint ────────────────────────────────────────────────────────────────

def _entrypoint() -> List[str]:
    return [
        "",
        "",
        'if __name__ == "__main__":',
        "    asyncio.run(run())",
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def emit(schedule: IRSchedule) -> str:
    """
    Emit a complete standalone Python source file from an IRSchedule.

    Args:
        schedule: The execution schedule produced by Scheduler.build().

    Returns:
        Python source code as a single string.
    """
    sections: List[List[str]] = [
        _header(schedule.graph_name),
        _collect_preambles(schedule),
        _run_function(schedule),
        _entrypoint(),
    ]

    # Flatten and normalise trailing blank lines between sections
    lines: List[str] = []
    for section in sections:
        lines.extend(section)

    return "\n".join(lines) + "\n"
