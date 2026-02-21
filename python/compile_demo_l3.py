"""
NodeGraph Compiler v3 — Demo (Level 3 / Zero-Framework)
=========================================================
Compiles the same graphs as compile_demo.py but targets the raw
openai SDK instead of langchain.

Output: python/compiled_l3/
  streaming_agent.py          — ToolAgentStreamNode, step-by-step, zero-framework
  blocking_agent.py           — ToolAgentNode, blocking, zero-framework
  streaming_agent_multistep.py — multi-step calculator, zero-framework

Dependencies of the OUTPUT files (not this script):
    pip install openai python-dotenv

Run from the project root:

    cd /Users/robertpringle/development/nodegraph
    /usr/local/bin/python3 python/compile_demo_l3.py
"""

from __future__ import annotations

import os
import sys

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE   = os.path.dirname(os.path.abspath(__file__))
_ROOT   = os.path.abspath(os.path.join(_HERE, ".."))
_IMPORT = os.path.abspath(os.path.join(_HERE, "../.."))
for _p in (_IMPORT, _ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

import nodegraph.python.server.langchain_nodes   # noqa: F401
import nodegraph.python.server.node_definitions  # noqa: F401

from nodegraph.python.langchain_agent_stream_example import (
    build_blocking,
    build_streaming,
)
from nodegraph.python.compiler3 import compile_graph_l3

# ── Scenarios ─────────────────────────────────────────────────────────────────

TASK_SIMPLE    = "What is 123 * 456? Then count the words in the answer."
TOOLS_SIMPLE   = ["calculator", "word_count"]

TASK_MULTISTEP = (
    "Calculate (17 * 23) + (88 / 4). "
    "Then take that result and multiply it by 3."
)
TOOLS_CALC = ["calculator"]

OUT_DIR = os.path.join(_HERE, "compiled_l3")


def _write(filename: str, source: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w") as f:
        f.write(source)
    print(f"  Written → {os.path.relpath(path, _ROOT)}")
    return path


def main() -> None:
    print()
    print("NodeGraph Compiler v3 — Level 3 / Zero-Framework Demo")
    print("=" * 55)
    print("Output dependencies: pip install openai python-dotenv")
    print("=" * 55)

    # ── 1. Streaming agent (simple) ───────────────────────────────────────
    print("\n[1] Compiling: streaming agent (simple) → compiled_l3/streaming_agent.py")
    net, _ = build_streaming(TASK_SIMPLE, TOOLS_SIMPLE)
    s1 = compile_graph_l3(net.graph, graph_name="streaming-agent-simple")
    p1 = _write("streaming_agent.py", s1)

    # ── 2. Blocking agent (simple) ────────────────────────────────────────
    print("\n[2] Compiling: blocking agent (simple) → compiled_l3/blocking_agent.py")
    net, _ = build_blocking(TASK_SIMPLE, TOOLS_SIMPLE)
    s2 = compile_graph_l3(net.graph, graph_name="blocking-agent-simple")
    p2 = _write("blocking_agent.py", s2)

    # ── 3. Streaming agent (multi-step) ───────────────────────────────────
    print("\n[3] Compiling: streaming agent (multi-step) → compiled_l3/streaming_agent_multistep.py")
    net, _ = build_streaming(TASK_MULTISTEP, TOOLS_CALC)
    s3 = compile_graph_l3(net.graph, graph_name="streaming-agent-multistep")
    _write("streaming_agent_multistep.py", s3)

    # ── Side-by-side comparison with L2 ───────────────────────────────────
    print()
    print("=" * 55)
    print("Dependency comparison")
    print("=" * 55)

    l2_blocking = os.path.join(_HERE, "compiled", "blocking_agent.py")
    if os.path.exists(l2_blocking):
        with open(l2_blocking) as f:
            l2_src = f.read()
        l2_imports = [l for l in l2_src.splitlines() if l.startswith("from ") or l.startswith("import ")]
        l3_imports = [l for l in s2.splitlines() if l.startswith("from ") or l.startswith("import ")]
        print("\nL2 (langchain) imports inside run() and helpers:")
        for i in l2_imports:
            print(f"  {i}")
        print("\nL3 (openai SDK only) imports inside run() and helpers:")
        for i in l3_imports:
            print(f"  {i}")
    else:
        print("(run compile_demo.py first to generate L2 output for comparison)")

    # ── Preview first compiled file ───────────────────────────────────────
    print()
    print("=" * 55)
    print("Preview: compiled_l3/streaming_agent.py")
    print("=" * 55)
    with open(p1) as f:
        print(f.read())


if __name__ == "__main__":
    main()
