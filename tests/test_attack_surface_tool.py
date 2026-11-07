"""The attack-surface scanner classifies routes correctly on a tiny synthetic source."""
import ast
import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.no_server

_spec = importlib.util.spec_from_file_location(
    "attack_surface", pathlib.Path(__file__).resolve().parents[1] / "security" / "attack_surface.py"
)
attack_surface = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(attack_surface)

SAMPLE = '''
@bp.route("/safe", methods=["POST"])
@login_required
def safe():
    return "ok"

@bp.route("/open", methods=["POST"])
def open_route():
    name = request.form["name"]
    db.execute(f"SELECT * FROM users WHERE username = '{name}'")

@bp.route("/page")
def page():
    return "read only"

@bp.route("/guarded", methods=["POST"])
def guarded():
    denied = admin_only_guard(session.get("user_id"))
    return denied
'''


def _routes():
    tree = ast.parse(SAMPLE)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for path, methods in attack_surface._route_info(node):
                src = ast.get_source_segment(SAMPLE, node)
                out.append(
                    {
                        "name": node.name,
                        "mutating": bool(attack_surface.MUTATING & set(methods)),
                        "login": bool(attack_surface.AUTH_DECORATORS & set(attack_surface._decorator_names(node))),
                        "guard": any(c in src for c in attack_surface.AUTH_CALLS),
                        "sql": attack_surface._dynamic_sql_calls(node),
                        "input": bool(attack_surface.INPUT_RE.search(src)),
                    }
                )
    return {r["name"]: r for r in out}


def test_authenticated_post_is_not_flagged():
    r = _routes()["safe"]
    assert r["mutating"] and r["login"]


def test_open_post_with_input_and_fstring_sql_is_flagged():
    r = _routes()["open_route"]
    assert r["mutating"] and not r["login"] and not r["guard"]
    assert r["input"] and r["sql"]


def test_get_only_route_is_not_mutating():
    assert not _routes()["page"]["mutating"]


def test_admin_guard_counts_as_auth():
    assert _routes()["guarded"]["guard"]


def test_scan_runs_on_this_repo():
    routes = attack_surface.scan()
    assert len(routes) > 100
    assert set(attack_surface.classify(routes)) == set(attack_surface.TITLES)
