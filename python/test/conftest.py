"""
pytest fixtures shared across the python/test/ suite.

All server-module imports are deferred to fixture-call time (not module import
time) to avoid the ForLoopNode double-registration error that occurs when pytest
collects both test_dbos_nodes.py and test_loop_node.py in the same session.
"""
from __future__ import annotations

import os
import sys

# Ensure the project root is importable from any working directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

import pytest


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def null_backend():
    """A NullBackend instance — calls compute() directly with no persistence."""
    from nodegraph.python.core.DurabilityBackend import NullBackend
    return NullBackend()


@pytest.fixture
def file_backend(tmp_path):
    """A FileBackend instance writing checkpoints to pytest's tmp_path."""
    from nodegraph.python.core.DurabilityBackend import FileBackend
    return FileBackend(str(tmp_path / "checkpoints"))


# ---------------------------------------------------------------------------
# Executor factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_executor(null_backend):
    """
    Factory fixture: returns a function that builds a configured Executor.

    Usage::

        def test_something(make_executor):
            graph  = _build_my_graph()
            ex     = make_executor(graph)              # NullBackend + sequential
            ex2    = make_executor(graph, sequential=False)
            asyncio.run(ex.cook_flow_control_nodes(start_node))

    Parameters (of the returned factory)
    -------------------------------------
    graph : Graph
        The Graph the Executor will operate on.
    backend : DurabilityBackend | None
        Explicit backend. Defaults to the ``null_backend`` fixture value.
    sequential : bool
        Sets ``_sequential_batches``.  Defaults to True for deterministic tests.
    run_id : str | None
        Sets ``executor.run_id``.  Defaults to None.
    """
    def _factory(graph, *, backend=None, sequential: bool = True, run_id=None):
        from nodegraph.python.core.Executor import Executor
        ex = Executor(graph)
        ex.backend = backend if backend is not None else null_backend
        ex._sequential_batches = sequential
        ex.run_id = run_id
        return ex
    return _factory


# ---------------------------------------------------------------------------
# HumanInputNode helper
# ---------------------------------------------------------------------------

@pytest.fixture
def auto_human_input():
    """
    Returns a helper ``configure(node, response)`` that sets ``auto_respond``
    on a HumanInputNode so it resolves immediately without blocking.

    ``response`` can be a plain string or a zero-arg callable::

        def test_hitl(auto_human_input):
            node = HumanInputNode("ask", "HumanInputNode", network_id="n1")
            auto_human_input(node, "Alice")       # static
            auto_human_input(node, lambda: "Bob") # dynamic / callable
    """
    def configure(node, response):
        node.auto_respond = response
    return configure
