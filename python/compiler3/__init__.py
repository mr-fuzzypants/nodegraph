"""
NodeGraph Compiler v3 — Level 3 / Zero-Framework Output
=========================================================
Compiles a live nodegraph Graph into a fully standalone Python file.

Output dependencies: pip install openai python-dotenv
No langchain, langgraph, or nodegraph runtime required.

Pipeline (shared with compiler2 up to the template layer):
    Graph  →  [compiler2.extractor]  →  IRGraph
    IRGraph →  [compiler2.scheduler]  →  IRSchedule
    IRSchedule → [compiler3.emitter]  →  Python source str

Public API
----------
    from nodegraph.python.compiler3 import compile_graph_l3

    source = compile_graph_l3(graph, graph_name="my_pipeline")
    print(source)
    # or
    with open("output.py", "w") as f:
        f.write(source)
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from nodegraph.python.compiler2.extractor import extract
from nodegraph.python.compiler2.scheduler import Scheduler
from .emitter import emit

if TYPE_CHECKING:
    from nodegraph.python.core.GraphPrimitives import Graph


def compile_graph_l3(
    graph: "Graph",
    graph_name: Optional[str] = None,
) -> str:
    """
    Compile a live nodegraph Graph into standalone Python (zero-framework).

    The output script requires only: openai, python-dotenv.
    No langchain, langgraph, or nodegraph packages needed to run it.

    Args:
        graph:       The Graph object to compile (from net.graph).
        graph_name:  Human-readable name embedded in the output header.

    Returns:
        Complete Python source as a single string.
    """
    ir       = extract(graph, graph_name=graph_name or "compiled-graph")
    schedule = Scheduler(ir).build(graph_name=ir.name)
    return emit(schedule)


__all__ = ["compile_graph_l3"]
