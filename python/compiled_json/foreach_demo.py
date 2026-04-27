#!/usr/bin/env python3
"""
Compiled from NodeGraph: foreach-demo
Generated:  2026-02-21

Level 3 / Zero-Framework output.
Dependencies: pip install openai python-dotenv
No langchain, langgraph, or nodegraph runtime required.

This file was produced by nodegraph.python.compiler3.
Do not edit by hand — re-run compile_graph_l3() to regenerate.
"""
from __future__ import annotations

import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — set OPENAI_API_KEY in environment manually

async def _foreach_stream(items):
    """Async generator — yields one dict per list element, then a done sentinel."""
    _items = list(items) if items is not None else []
    _total = len(_items)
    for _i, _v in enumerate(_items):
        yield {"_done": False, "item": _v, "index": _i, "total": _total}
    yield {"_done": True, "item": None, "index": -1, "total": _total}


# ── Graph: foreach-demo ──────────────────────────────────────
async def run() -> None:
    # Node: Items (ConstantNode)
    items_out = ['Process step 1', 'Process step 2', 'Process step 3']

    # Node: ForEach (ForEachNode)
    foreach_item = ""
    foreach_index = ""
    foreach_total = ""

    async for _step in _foreach_stream(items_out):
        foreach_item  = _step['item']
        foreach_index = _step['index']
        foreach_total = _step['total']
        if _step['_done']:
            break

        # Node: ItemPrinter (PrintNode)
        print(f'[ItemPrinter] ' + str(foreach_item))


    # Node: Done (PrintNode)
    print(f'[Done] ' + str(foreach_total))


if __name__ == "__main__":
    asyncio.run(run())
