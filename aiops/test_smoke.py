"""Validation gate for the agent's edits.

An import check alone is a weak gate: the agent can produce logically broken
code and still go green, which means the retry loop almost never fires and
"validation passed" carries little information. Add real assertions about the
behaviour you care about here — this file is what stands between the agent and
your default branch.
"""
from __future__ import annotations

import importlib

import pytest


def test_app_imports():
    """The application module imports cleanly with all dependencies."""
    module = importlib.import_module("app.main")
    assert getattr(module, "app", None) is not None


def test_no_syntax_errors_anywhere():
    """Catches the most common way an LLM edit breaks a repo: a file that
    parses locally but not after a partial rewrite."""
    import pathlib
    import py_compile
    failures = []
    for path in pathlib.Path("app").rglob("*.py"):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append(f"{path}: {exc}")
    assert not failures, "syntax errors introduced:\n" + "\n".join(failures)


@pytest.mark.parametrize("attr", ["app"])
def test_public_surface_is_intact(attr):
    """Guards against an edit that quietly drops a public name."""
    module = importlib.import_module("app.main")
    assert hasattr(module, attr), f"app.main no longer exports {attr!r}"


def test_schemas_imports_and_exposes_alert_out():
    """app.schemas imports cleanly and exposes AlertOut."""
    module = importlib.import_module("app.schemas")
    assert hasattr(module, "AlertOut"), "app.schemas no longer exports 'AlertOut'"
