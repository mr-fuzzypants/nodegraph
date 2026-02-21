"""
compile_from_json.py — CLI for the NodeGraph JSON compiler
===========================================================
Compiles a serialised graph JSON file into a standalone Python script.

Usage
-----
    python python/compile_from_json.py <graph.json> [options]

Options
-------
    --target  {l2,l3}   Output target framework (default: l3)
                          l2 — LangChain output (requires langchain + langchain-openai)
                          l3 — Zero-framework output (requires openai only)
    --out     <dir>     Output directory (default: python/compiled_json/)
    --print             Print the generated source to stdout instead of writing a file
    --strict            Treat unknown node types as errors (default: warnings only)

Examples
--------
    # Compile to zero-framework (L3) output:
    python python/compile_from_json.py python/graphs/streaming_agent.json

    # Compile all three graphs to a custom output directory:
    python python/compile_from_json.py python/graphs/streaming_agent.json --out python/compiled_l3/ --target l3
    python python/compile_from_json.py python/graphs/blocking_agent.json  --out python/compiled_l3/
    python python/compile_from_json.py python/graphs/streaming_agent_multistep.json --out python/compiled_l3/

    # Print the generated source without writing a file:
    python python/compile_from_json.py python/graphs/blocking_agent.json --print
"""

from __future__ import annotations

import argparse
import sys
import os
from pathlib import Path

# ── path bootstrap ────────────────────────────────────────────────────────────
# Allow running this script from anywhere without installing the package.
# The `nodegraph` package lives at <repo-root>/  (the directory that contains
# the `python/` folder), so we need <repo-root>'s *parent* on sys.path.
# File layout:  <repo-root>/python/compile_from_json.py
#               <repo-root>/python/compiler3/...
# The importable package root is the directory that CONTAINS `nodegraph/`,
# which is the parent of the repo root itself.
#   compile_from_json.py  → .parent → python/  → .parent → nodegraph/  → .parent → dev/
_REPO_ROOT   = Path(__file__).resolve().parent.parent   # …/nodegraph
_IMPORT_ROOT = _REPO_ROOT.parent                        # …/development
for _p in (_IMPORT_ROOT, _REPO_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="compile_from_json",
        description="Compile a NodeGraph JSON graph to standalone Python.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "graph_json",
        metavar="graph.json",
        help="Path to the graph JSON file to compile.",
    )
    p.add_argument(
        "--target",
        choices=["l2", "l3"],
        default="l3",
        help=(
            "Output target. l3 (default) = raw openai SDK only. "
            "l2 = LangChain output."
        ),
    )
    p.add_argument(
        "--out",
        metavar="DIR",
        default="python/compiled_json",
        help="Output directory for the compiled .py file (default: python/compiled_json/).",
    )
    p.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print generated source to stdout instead of writing a file.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Treat unknown node types as errors rather than warnings.",
    )
    return p


def _graph_name_to_filename(graph_name: str) -> str:
    """Turn 'streaming-agent-simple' → 'streaming_agent_simple.py'."""
    safe = graph_name.lower().replace("-", "_").replace(" ", "_")
    return f"{safe}.py"


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    json_path = Path(args.graph_json)
    if not json_path.exists():
        print(f"[error] File not found: {json_path}", file=sys.stderr)
        return 1

    # ── Validate JSON ────────────────────────────────────────────────────────
    from nodegraph.python.compiler3.schema import validate_file, SchemaError
    try:
        data = validate_file(json_path, strict=args.strict)
    except SchemaError as exc:
        print(f"[error] Schema validation failed: {exc}", file=sys.stderr)
        return 1

    graph_name = data.get("graph_name", json_path.stem)
    print(f"[compile_from_json] graph  : {graph_name}")
    print(f"[compile_from_json] target : {args.target}")

    # ── Deserialise JSON → IRGraph ───────────────────────────────────────────
    from nodegraph.python.compiler3.deserialiser import json_to_ir
    ir = json_to_ir(data)
    print(f"[compile_from_json] nodes  : {len(ir.nodes)}")
    print(f"[compile_from_json] edges  : {len(ir.edges)}")

    # ── Schedule ─────────────────────────────────────────────────────────────
    from nodegraph.python.compiler2.scheduler import Scheduler
    schedule = Scheduler(ir).build(graph_name=ir.name)

    # ── Emit ─────────────────────────────────────────────────────────────────
    if args.target == "l3":
        from nodegraph.python.compiler3.emitter import emit
        source = emit(schedule)
    else:
        from nodegraph.python.compiler2.emitter import emit as emit_l2
        source = emit_l2(schedule)

    # ── Output ───────────────────────────────────────────────────────────────
    if args.print_only:
        print(source)
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / _graph_name_to_filename(graph_name)
    out_path.write_text(source, encoding="utf-8")

    print(f"[compile_from_json] wrote  : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
