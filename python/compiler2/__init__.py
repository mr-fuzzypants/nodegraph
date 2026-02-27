"""
NodeGraph Compiler v2
=====================
Converts a live nodegraph Graph into a standalone Python source file.

Pipeline:
    Graph  →  [extractor]  →  IRGraph
    IRGraph →  [scheduler]  →  IRSchedule
    IRSchedule → [emitter]  →  Python source str

Public API
----------
    from nodegraph.python.compiler2 import compile_graph

    source = compile_graph(graph, graph_name="my_pipeline")
    print(source)
    # or
    with open("output.py", "w") as f:
        f.write(source)
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .extractor import extract
from .scheduler import Scheduler
from .emitter import emit

if TYPE_CHECKING:
    from nodegraph.python.core.GraphPrimitives import Graph


def compile_graph(
    graph: "Graph",
    graph_name: Optional[str] = None,
) -> str:
    """
    Compile a live nodegraph Graph into standalone Python source code.

    The output script:
      - Has no nodegraph imports.
      - Requires only langchain + openai (and dotenv, optionally).
      - Can be run with:  python output.py

    Args:
        graph:       The Graph object to compile (from net.graph).
        graph_name:  Human-readable name embedded in the output header.
                     Defaults to the graph's network id.

    Returns:
        Complete Python source as a single string.
    """
    ir       = extract(graph, graph_name=graph_name or "compiled-graph")
    schedule = Scheduler(ir).build(graph_name=ir.name)
    return emit(schedule)


__all__ = ["compile_graph"]
