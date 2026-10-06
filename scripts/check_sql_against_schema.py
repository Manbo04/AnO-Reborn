#!/usr/bin/env python3
"""Check every SQL query in the app code against the real database schema.

Why: the most common way AnO breaks in production is code that references a
table or column that does not exist in the live database (e.g. b027fdab:
`provinces.location` killed resource production for ~12 hours). Nothing caught
it because no test ran that exact query.

How: parse the Python source, pull out the SQL passed to `.execute()` /
`.executemany()` (string literals, string variables assigned in the same
function or module, `+` concatenations, and f-strings), and ask Postgres to
`PREPARE` each one against a database built from `db/schema.sql`. PREPARE
parses and resolves every table/column/function without running anything, so
it is safe and fast.

Severity:
  * static SQL (plain strings)  -> a missing table/column/ambiguous column is
    an ERROR and fails CI unless listed in db/sql_check_baseline.txt.
  * dynamic SQL (f-strings)     -> interpolated parts are guessed, so problems
    are only reported as warnings.

Usage (needs a DB loaded from db/schema.sql):
    DATABASE_URL=postgresql://... python scripts/check_sql_against_schema.py
    ... --update-baseline   # rewrite the baseline with the current errors
    ... --verbose           # print warnings too
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "db" / "sql_check_baseline.txt"

# Directories that are not part of the running game (one-off scripts, tests,
# scratch work, vendored envs). Everything else that ships is checked.
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "tests", "scratch",
    "scripts", "debug_scripts", "attack_scripts", "migrations", "graphify-out",
    "mcp-server", "__pycache__", ".agents", ".claude",
}
EXECUTE_METHODS = {"execute", "executemany"}

# SQLSTATEs that mean "this query references something that does not exist".
HARD_SQLSTATES = {
    "42P01": "undefined table",
    "42703": "undefined column",
    "42702": "ambiguous column",
    "42601": "syntax error",
    "42803": "grouping error",
}
# Statements PREPARE can analyse. Anything else (DDL, SET, LOCK, ...) is skipped.
PREPARABLE = re.compile(r"^\s*(\(\s*)*(SELECT|INSERT|UPDATE|DELETE|WITH|VALUES)\b", re.I)
DYNAMIC_MARK = "__ano_dyn__"


@dataclass
class Query:
    path: str
    line: int
    sql: str
    dynamic: bool

    @property
    def key(self) -> str:
        norm = re.sub(r"\s+", " ", self.sql.strip()).lower()
        return f"{self.path}::{hashlib.sha1(norm.encode()).hexdigest()[:12]}"


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def _fstring_template(node: ast.JoinedStr, resolve=None) -> str:
    parts = []
    for v in node.values:
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            parts.append(v.value)
            continue
        if resolve is not None and isinstance(v, ast.FormattedValue) and v.format_spec is None:
            res = resolve(v.value)
            if res is not None and not res[1]:
                parts.append(res[0])
                continue
        parts.append(DYNAMIC_MARK)
    return "".join(parts)


class _Resolver:
    """Resolve the SQL text of an execute() argument where it is knowable."""

    def __init__(self, module: ast.Module):
        self.module_assigns = self._collect(module.body)

    @staticmethod
    def _collect(body) -> dict[str, list[tuple[int, ast.AST]]]:
        out: dict[str, list[tuple[int, ast.AST]]] = {}
        for stmt in body:
            for node in ast.walk(stmt) if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else [stmt]:
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    out.setdefault(node.targets[0].id, []).append((node.lineno, node.value))
                elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                    out.setdefault(node.target.id, []).append((node.lineno, ast.BinOp(left=ast.Name(id=node.target.id), op=ast.Add(), right=node.value)))
        return out

    def resolve(self, node, func_assigns, line, depth=0) -> tuple[str, bool] | None:
        if depth > 6:
            return None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, False
        if isinstance(node, ast.JoinedStr):
            tpl = _fstring_template(
                node, lambda n: self.resolve(n, func_assigns, line, depth + 1)
            )
            return tpl, DYNAMIC_MARK in tpl
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self.resolve(node.left, func_assigns, line, depth + 1)
            right = self.resolve(node.right, func_assigns, line, depth + 1)
            if left is None and right is None:
                return None
            ls, ld = left if left else (DYNAMIC_MARK, True)
            rs, rd = right if right else (DYNAMIC_MARK, True)
            return ls + rs, ld or rd
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            # "... %s ..." % (x,)  -> old-style interpolation, treat as dynamic
            inner = self.resolve(node.left, func_assigns, line, depth + 1)
            if inner:
                return re.sub(r"%[sd]", DYNAMIC_MARK, inner[0]), True
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            inner = self.resolve(node.func.value, func_assigns, line, depth + 1)
            if inner:
                return re.sub(r"\{[^{}]*\}", DYNAMIC_MARK, inner[0]), True
            return None
        if isinstance(node, ast.Name):
            for assigns in (func_assigns, self.module_assigns):
                cands = [(ln, v) for ln, v in assigns.get(node.id, []) if ln <= line]
                if cands:
                    # Several assignments (if/else branches) -> take the last
                    # one before the call; good enough for a static check.
                    ln, v = max(cands, key=lambda x: x[0])
                    if isinstance(v, ast.BinOp) and isinstance(v.left, ast.Name) and v.left.id == node.id:
                        prev = [(l2, v2) for l2, v2 in assigns[node.id] if l2 < ln]
                        if not prev:
                            return None
                        base = self.resolve(ast.Name(id=node.id), {node.id: prev}, ln - 1, depth + 1)
                        tail = self.resolve(v.right, func_assigns, line, depth + 1)
                        if base is None or tail is None:
                            return None
                        return base[0] + tail[0], base[1] or tail[1]
                    return self.resolve(v, func_assigns, ln, depth + 1)
        return None


def extract(path: Path) -> list[Query]:
    rel = str(path.relative_to(ROOT))
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    resolver = _Resolver(tree)
    out: list[Query] = []

    def visit(body_owner, func_assigns):
        for node in ast.walk(body_owner):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in EXECUTE_METHODS and node.args:
                res = resolver.resolve(node.args[0], func_assigns, node.lineno)
                if res is None:
                    continue
                sql, dynamic = res
                if PREPARABLE.match(sql):
                    out.append(Query(rel, node.lineno, sql, dynamic))

    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    seen_lines: set[int] = set()
    # Smallest (innermost) function first so nested defs use their own assignments.
    for fn in sorted(funcs, key=lambda f: (f.end_lineno - f.lineno)):
        assigns = _Resolver._collect(fn.body)
        before = len(out)
        visit(fn, assigns)
        # de-duplicate calls already captured by a more specific (inner) function
        kept = []
        for q in out[before:]:
            if q.line not in seen_lines:
                seen_lines.add(q.line)
                kept.append(q)
        out[before:] = kept
    # module-level calls
    before = len(out)
    visit(tree, {})
    kept = []
    for q in out[before:]:
        if q.line not in seen_lines:
            seen_lines.add(q.line)
            kept.append(q)
    out[before:] = kept
    return out


def iter_sources():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.startswith(".")]
        for f in filenames:
            if f.endswith(".py") and not f.startswith("._"):
                yield Path(dirpath) / f


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def to_prepare_sql(sql: str) -> str:
    """Turn psycopg2 placeholders into $n so PREPARE accepts the statement."""
    counter = {"n": 0}
    names: dict[str, int] = {}

    def named(m):
        name = m.group(1)
        if name not in names:
            counter["n"] += 1
            names[name] = counter["n"]
        return f"${names[name]}"

    def positional(_m):
        counter["n"] += 1
        return f"${counter['n']}"

    # psycopg2 expands a tuple bound to "IN %s"; PREPARE needs ANY($n).
    sql = re.sub(r"\bNOT\s+IN\s+(%s|%\(\w+\)s)", r"<> ALL(\1)", sql, flags=re.I)
    sql = re.sub(r"\bIN\s+(%s|%\(\w+\)s)", r"= ANY(\1)", sql, flags=re.I)
    sql = re.sub(r"%\((\w+)\)s", named, sql)
    sql = re.sub(r"%s", positional, sql)
    sql = sql.replace("%%", "%")
    # Guess for interpolated fragments: most are values or IN-lists.
    sql = sql.replace(DYNAMIC_MARK, "NULL")
    return sql.strip().rstrip(";")


def check(queries: list[Query], dsn: str):
    import psycopg2

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    errors, warnings, ok, inconclusive = [], [], 0, 0
    for q in queries:
        try:
            cur.execute("PREPARE ano_chk AS " + to_prepare_sql(q.sql))
            cur.execute("DEALLOCATE ano_chk")
            ok += 1
        except psycopg2.Error as exc:
            state = exc.pgcode or ""
            msg = (exc.pgerror or str(exc)).strip().splitlines()[0]
            if state in HARD_SQLSTATES and not q.dynamic:
                errors.append((q, state, msg))
            elif state in ("42P01", "42703") and "null" not in msg.lower():
                # Dynamic SQL: only a clean missing table/column (not one caused
                # by our placeholder guess) is worth a warning.
                warnings.append((q, state, msg))
            else:
                inconclusive += 1  # e.g. parameter types Postgres cannot infer
    conn.close()
    return errors, warnings, ok, inconclusive


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.split("#", 1)[0].strip()
        for line in BASELINE.read_text().splitlines()
        if line.split("#", 1)[0].strip()
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    dsn = os.getenv("SCHEMA_CHECK_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: set DATABASE_URL to a database loaded from db/schema.sql")
        return 2

    queries = [q for p in sorted(iter_sources()) for q in extract(p)]
    errors, warnings, ok, inconclusive = check(queries, dsn)
    baseline = load_baseline()

    new = [e for e in errors if e[0].key not in baseline]
    known = [e for e in errors if e[0].key in baseline]
    fixed = baseline - {e[0].key for e in errors}

    print(
        f"SQL schema check: {len(queries)} queries "
        f"({sum(not q.dynamic for q in queries)} static, {sum(q.dynamic for q in queries)} dynamic) | "
        f"ok={ok} errors={len(errors)} (new={len(new)}, known={len(known)}) "
        f"warnings={len(warnings)} inconclusive={inconclusive}"
    )

    if args.update_baseline:
        lines = [
            "# Known SQL-vs-schema errors that existed when the check was introduced.",
            "# CI fails on any error NOT listed here. Fix these and delete the lines;",
            "# never add new entries to make CI pass.",
        ]
        for q, state, msg in sorted(errors, key=lambda e: e[0].key):
            lines.append(f"{q.key}  # {q.path}:{q.line} {HARD_SQLSTATES[state]}: {msg[:120]}")
        BASELINE.write_text("\n".join(lines) + "\n")
        print(f"Baseline written: {len(errors)} entries -> {BASELINE.relative_to(ROOT)}")
        return 0

    for q, state, msg in new:
        print(f"ERROR {q.path}:{q.line} [{HARD_SQLSTATES[state]}] {msg}")
    if args.verbose:
        for q, state, msg in known:
            print(f"known {q.path}:{q.line} [{HARD_SQLSTATES[state]}] {msg}")
        for q, state, msg in warnings:
            print(f"warn  {q.path}:{q.line} [{HARD_SQLSTATES[state]}] (dynamic SQL) {msg}")
    if fixed:
        print(f"note: {len(fixed)} baseline entries no longer fail -- delete them from {BASELINE.relative_to(ROOT)}")
    if new:
        print(
            "\nThese queries reference tables/columns that do not exist in the production schema "
            "(db/schema.sql). Fix the query, or add a migration AND refresh db/schema.sql."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
