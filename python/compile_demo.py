"""
NodeGraph Compiler v2 — Demo
=============================
Compiles the blocking and streaming agent graphs from
langchain_agent_stream_example.py into standalone Python files.

Run from the project root:

    cd /Users/robertpringle/development/nodegraph
    /usr/local/bin/python3 python/compile_demo.py

Output files:
    python/compiled/streaming_agent.py    — streaming graph (ToolAgentStreamNode)
    python/compiled/blocking_agent.py     — blocking graph  (ToolAgentNode)
"""

from __future__ import annotations

import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE      = os.path.dirname(os.path.abspath(__file__))
_ROOT      = os.path.abspath(os.path.join(_HERE, ".."))
_IMPORT    = os.path.abspath(os.path.join(_HERE, "../.."))
for _p in (_IMPORT, _ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Load .env ─────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

# ── Imports ───────────────────────────────────────────────────────────────────
import nodegraph.python.server.langchain_nodes   # noqa: F401  register node types
import nodegraph.python.server.node_definitions  # noqa: F401  register node types

from nodegraph.python.langchain_agent_stream_example import (
    build_blocking,
    build_streaming,
)
from nodegraph.python.compiler2 import compile_graph


# ── Graph definitions ─────────────────────────────────────────────────────────

TASK_SIMPLE    = "What is 123 * 456? Then count the words in the answer."
TOOLS_SIMPLE   = ["calculator", "word_count"]

TASK_MULTISTEP = (
    "Calculate (17 * 23) + (88 / 4). "
    "Then take that result and multiply it by 3."
)
TOOLS_CALC = ["calculator"]


def _write(path: str, source: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(source)
    print(f"  Written → {os.path.relpath(path, _ROOT)}")


def main() -> None:
    print()
    print("NodeGraph Compiler v2 — Demo")
    print("=" * 50)

    # ── 1. Streaming agent (simple) ───────────────────────────────────────
    print("\n[1] Compiling: streaming agent (simple task)")
    net, _ = build_streaming(TASK_SIMPLE, TOOLS_SIMPLE)
    source  = compile_graph(net.graph, graph_name="streaming-agent-simple")
    _write(os.path.join(_HERE, "compiled", "streaming_agent.py"), source)

    # ── 2. Blocking agent (simple) ────────────────────────────────────────
    print("\n[2] Compiling: blocking agent (simple task)")
    net, _ = build_blocking(TASK_SIMPLE, TOOLS_SIMPLE)
    source  = compile_graph(net.graph, graph_name="blocking-agent-simple")
    _write(os.path.join(_HERE, "compiled", "blocking_agent.py"), source)

    # ── 3. Streaming agent (multi-step) ───────────────────────────────────
    print("\n[3] Compiling: streaming agent (multi-step calculator)")
    net, _ = build_streaming(TASK_MULTISTEP, TOOLS_CALC)
    source  = compile_graph(net.graph, graph_name="streaming-agent-multistep")
    _write(os.path.join(_HERE, "compiled", "streaming_agent_multistep.py"), source)

    # ── Preview first compiled file ───────────────────────────────────────
    print()
    print("=" * 50)
    print("Preview: python/compiled/streaming_agent.py")
    print("=" * 50)

    preview_path = os.path.join(_HERE, "compiled", "streaming_agent.py")
    with open(preview_path) as f:
        print(f.read())


if __name__ == "__main__":
    main()
