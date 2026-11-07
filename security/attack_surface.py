#!/usr/bin/env python3
"""Attack-surface report: entry points (Flask routes) mapped to risky sinks.

Static and approximate. It finds candidates for a human or a verifier agent to check; it does
not prove anything. Every finding must be reproduced before it is reported (see
docs/CHANGE_PIPELINE.md, gate 2).

    python security/attack_surface.py                 # markdown report on stdout
    python security/attack_surface.py --json          # machine-readable
    python security/attack_surface.py --only no_auth_mutating

Do not commit the generated report to the public repo; review it privately.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"tests", "node_modules", "scratch", "scripts", "mcp-server", ".git", "attack_scripts", "migrations", "venv", ".venv"}
MUTATING = {"POST", "PUT", "DELETE", "PATCH"}
AUTH_DECORATORS = {"login_required", "admin_required", "auth_required"}
AUTH_CALLS = ("admin_only_guard", "admin_diag_or_session", "admin_diag_authorized", "_require_admin_diag_or_session", "blocks_interaction")
INPUT_RE = re.compile(r"request\.(form|args|json|values|files|data|get_json|cookies|headers)")
GOLD_WRITE_RE = re.compile(r"UPDATE\s+stats\s+SET\s+gold", re.I)
SESSION_USER_RE = re.compile(r"session(\.get\(|\[)\s*['\"]user_id['\"]")


def iter_files():
    for p in ROOT.rglob("*.py"):
        parts = set(p.relative_to(ROOT).parts)
        if parts & SKIP_DIRS:
            continue
        yield p


def _decorator_names(fn: ast.FunctionDef) -> List[str]:
    names = []
    for d in fn.decorator_list:
        node = d.func if isinstance(d, ast.Call) else d
        if isinstance(node, ast.Attribute):
            names.append(node.attr)
        elif isinstance(node, ast.Name):
            names.append(node.id)
    return names


def _route_info(fn: ast.FunctionDef):
    """Return list of (path, methods) for each @x.route(...) decorator."""
    out = []
    for d in fn.decorator_list:
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "route"):
            continue
        path = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else "?"
        methods = ["GET"]
        for kw in d.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple)):
                methods = [e.value.upper() for e in kw.value.elts if isinstance(e, ast.Constant)]
        out.append((path, methods))
    return out


def _dynamic_sql_calls(fn: ast.FunctionDef) -> List[int]:
    """Lines of .execute()/.executemany() calls whose SQL is built with f-strings, %, + or .format."""
    lines = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("execute", "executemany") and node.args:
            a = node.args[0]
            dynamic = isinstance(a, ast.JoinedStr) or (isinstance(a, ast.BinOp) and isinstance(a.op, (ast.Mod, ast.Add))) or (
                isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and a.func.attr == "format"
            )
            if dynamic:
                lines.append(node.lineno)
    return lines


def csrf_exempt_names(trees: Dict[Path, ast.AST]) -> set:
    names = set()
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "exempt" and node.args:
                a = node.args[0]
                names.add(a.id if isinstance(a, ast.Name) else getattr(a, "attr", ""))
    return names


def scan() -> List[dict]:
    sources, trees = {}, {}
    for p in iter_files():
        try:
            text = p.read_text(encoding="utf-8")
            trees[p] = ast.parse(text)
            sources[p] = text
        except (SyntaxError, UnicodeDecodeError):
            continue
    exempt = csrf_exempt_names(trees)
    routes: List[dict] = []
    for p, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            infos = _route_info(node)
            if not infos:
                continue
            src = ast.get_source_segment(sources[p], node) or ""
            decos = _decorator_names(node)
            has_login = bool(AUTH_DECORATORS & set(decos))
            has_guard = any(c in src for c in AUTH_CALLS)
            has_session = bool(SESSION_USER_RE.search(src))
            for path, methods in infos:
                routes.append(
                    {
                        "file": str(p.relative_to(ROOT)),
                        "line": node.lineno,
                        "function": node.name,
                        "path": path,
                        "methods": methods,
                        "mutating": bool(MUTATING & set(methods)),
                        "login_required": has_login,
                        "guard_call": has_guard,
                        "session_user": has_session,
                        "reads_input": bool(INPUT_RE.search(src)),
                        "dynamic_sql_lines": _dynamic_sql_calls(node),
                        "raw_gold_write": bool(GOLD_WRITE_RE.search(src)),
                        "csrf_exempt": node.name in exempt,
                    }
                )
    routes.sort(key=lambda r: (r["file"], r["line"]))
    return routes


def classify(routes: List[dict]) -> Dict[str, List[dict]]:
    return {
        "no_auth_mutating": [r for r in routes if r["mutating"] and not (r["login_required"] or r["guard_call"])],
        "session_only_mutating": [
            r for r in routes if r["mutating"] and not (r["login_required"] or r["guard_call"]) and r["session_user"]
        ],
        "input_to_dynamic_sql": [r for r in routes if r["reads_input"] and r["dynamic_sql_lines"]],
        "csrf_exempt": [r for r in routes if r["csrf_exempt"]],
        "raw_gold_write_in_route": [r for r in routes if r["raw_gold_write"]],
    }


TITLES = {
    "no_auth_mutating": "State-changing routes with no login decorator or admin guard",
    "session_only_mutating": "...of which check the session user inside the function (likely fine, verify)",
    "input_to_dynamic_sql": "Routes that read request input and build SQL dynamically (entry point to sink)",
    "csrf_exempt": "CSRF-exempt routes",
    "raw_gold_write_in_route": "Routes that write gold directly (should go through the ledger)",
}


def markdown(routes: List[dict], only: str | None = None) -> str:
    groups = classify(routes)
    out = [f"# Attack-surface report", "", f"{len(routes)} routes scanned. Candidates only: reproduce each before reporting.", ""]
    for key, rows in groups.items():
        if only and key != only:
            continue
        out += [f"## {TITLES[key]} ({len(rows)})", ""]
        for r in rows:
            extra = f" sql lines {r['dynamic_sql_lines']}" if r["dynamic_sql_lines"] else ""
            out.append(f"- `{r['path']}` {','.join(r['methods'])} {r['file']}:{r['line']} `{r['function']}`{extra}")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", choices=list(TITLES))
    a = ap.parse_args(argv)
    routes = scan()
    if a.json:
        print(json.dumps({"routes": routes, "groups": {k: len(v) for k, v in classify(routes).items()}}, indent=1))
    else:
        print(markdown(routes, a.only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
