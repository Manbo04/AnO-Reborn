"""Local-only tests: extract and exec specific functions from countries.py
to avoid importing the whole Flask app and its heavy dependencies.

These tests intentionally load function bodies via AST and exec them into
isolated namespaces so we can stub only the exact DB helpers needed.
"""

import ast
import types
import sys


class DummyCursor:
    def __init__(self, rows=None):
        self.rows = rows or []

    def execute(self, sql, params=None):
        pass

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return []


def _load_function_from_file(fn_name: str) -> str:
    src = open("countries.py").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.get_source_segment(src, node)
    raise RuntimeError("function not found")


def test_next_turn_rations_handles_missing_rations(monkeypatch):
    """If the resources.rations row is missing, the function should use 0 and
    not raise."""

    dummy = DummyCursor(rows=[None])

    class ConnCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return types.SimpleNamespace(cursor=lambda: self._cursor)

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_db = types.SimpleNamespace(
        get_db_connection=lambda *a, **k: ConnCtx(dummy),
        fetchone_first=lambda cursor, default=None: default,
    )
    monkeypatch.setitem(sys.modules, "database", fake_db)

    # Provide a stub for calc_pg which should not be called in this test
    monkeypatch.setitem(
        sys.modules, "tasks", types.SimpleNamespace(calc_pg=lambda pid, r: (r, r))
    )

    fn_src = _load_function_from_file("next_turn_rations")
    ns = {}
    exec(fn_src, ns)
    fn = ns["next_turn_rations"]

    # No provinces, so result should be prod_rations
    assert fn(5, 10) == 10


def test_cg_need_handles_none_population(monkeypatch):
    """SUM(population) can be NULL; cg_need should treat it as 0."""

    dummy = DummyCursor(rows=[None])

    class ConnCtx:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return types.SimpleNamespace(cursor=lambda: self._cursor)

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_db = types.SimpleNamespace(
        get_db_connection=lambda *a, **k: ConnCtx(dummy),
        fetchone_first=lambda cursor, default=None: default,
    )
    monkeypatch.setitem(sys.modules, "database", fake_db)
    monkeypatch.setitem(
        sys.modules, "variables", types.SimpleNamespace(CONSUMER_GOODS_PER=80000)
    )

    fn_src = _load_function_from_file("cg_need")
    ns = {
        "math": __import__("math"),
        "variables": types.SimpleNamespace(CONSUMER_GOODS_PER=80000),
    }
    exec(fn_src, ns)
    fn = ns["cg_need"]

    # Should not raise and should return an int
    res = fn(1)
    assert isinstance(res, int)


# (end of tests)
