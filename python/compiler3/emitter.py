"""
NodeGraph Compiler v3 — Python Source Emitter (Level 3 / Zero Framework)
=========================================================================
Same structure as compiler2/emitter.py.
The only difference is the template registry — all helpers target the raw
openai SDK instead of langchain.

Imports compiler2's scheduler types (IRSchedule, LoopBlock, SequenceBlock)
since graph scheduling is output-format-agnostic.
"""

from __future__ import annotations

import datetime
from typing import List, Set

from nodegraph.python.compiler2.scheduler import (
    IRSchedule,
    LoopBlock,
    ScheduledNode,
    SequenceBlock,
)
from nodegraph.python.compiler2.templates import CodeWriter

# Pull templates from compiler3 — this is the only L3-specific import
from .templates import get_template


# ── File header ───────────────────────────────────────────────────────────────

def _header(graph_name: str) -> List[str]:
    today = datetime.date.today().isoformat()
    return [
        "#!/usr/bin/env python3",
        '"""',
        f"Compiled from NodeGraph: {graph_name}",
        f"Generated:  {today}",
        "",
        "Level 3 / Zero-Framework output.",
        "Dependencies: pip install openai python-dotenv",
        "No langchain, langgraph, or nodegraph runtime required.",
        "",
        "This file was produced by nodegraph.python.compiler3.",
        "Do not edit by hand — re-run compile_graph_l3() to regenerate.",
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
        "    pass  # dotenv optional — set OPENAI_API_KEY in environment manually",
        "",
    ]


# ── Preamble deduplication ────────────────────────────────────────────────────

def _collect_preambles(schedule: IRSchedule) -> List[str]:
    seen: Set[str] = set()
    lines: List[str] = []

    def _maybe(snode: ScheduledNode) -> None:
        if snode.type_name in seen:
            return
        seen.add(snode.type_name)
        tmpl = get_template(snode.type_name)
        p = tmpl.preamble(snode)
        if p:
            lines.extend(p)
            lines.append("")

    for snode in schedule.preamble:
        _maybe(snode)

    for block in schedule.blocks:
        if isinstance(block, LoopBlock):
            _maybe(block.driver)
            for snode in block.body:
                _maybe(snode)
            for snode in block.post:
                _maybe(snode)
        elif isinstance(block, SequenceBlock):
            for snode in block.nodes:
                _maybe(snode)

    return lines


# ── Loop-driver variable initialisers ─────────────────────────────────────────

def _loop_driver_inits(driver: ScheduledNode, writer: CodeWriter) -> None:
    for port_name, var_name in driver.output_vars.items():
        if port_name in ("loop_body", "completed", "next", "true_out", "false_out"):
            continue
        init = "0" if port_name.endswith("_count") or port_name.endswith("_index") else '""'
        writer.writeln(f"{var_name} = {init}")


# ── Block emitters ────────────────────────────────────────────────────────────

def _emit_loop_block(block: LoopBlock, writer: CodeWriter) -> None:
    driver = block.driver
    tmpl   = get_template(driver.type_name)

    writer.comment(f"Node: {driver.node_name} ({driver.type_name})")
    _loop_driver_inits(driver, writer)
    writer.blank()

    loop_expr = tmpl.emit_loop_expr(driver)
    writer.writeln(f"async for _step in {loop_expr}:")
    writer.push()

    tmpl.emit_loop_break(driver, writer)
    writer.blank()

    for snode in block.body:
        get_template(snode.type_name).emit_inline(snode, writer)
        writer.blank()

    writer.pop()

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

    if schedule.preamble:
        for snode in schedule.preamble:
            get_template(snode.type_name).emit_inline(snode, w)
            w.blank()

    for block in schedule.blocks:
        if isinstance(block, LoopBlock):
            _emit_loop_block(block, w)
        elif isinstance(block, SequenceBlock):
            _emit_sequence_block(block, w)

    if not schedule.preamble and not schedule.blocks:
        w.writeln("pass  # empty graph")

    w.pop()
    return w.lines()


def _entrypoint() -> List[str]:
    return [
        "",
        "",
        'if __name__ == "__main__":',
        "    asyncio.run(run())",
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def emit(schedule: IRSchedule) -> str:
    sections = [
        _header(schedule.graph_name),
        _collect_preambles(schedule),
        _run_function(schedule),
        _entrypoint(),
    ]
    lines: List[str] = []
    for section in sections:
        lines.extend(section)
    return "\n".join(lines) + "\n"
