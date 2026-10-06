"""Tests for scripts/check_sql_against_schema.py (the CI SQL-vs-schema gate).

The extraction tests need no database. The validation test runs only against a
LOCAL database built from db/schema.sql (CI's prod-shaped job).
"""
import importlib.util
import os
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_sql_against_schema", ROOT / "scripts" / "check_sql_against_schema.py"
)
chk = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = chk  # dataclasses need the module registered
_spec.loader.exec_module(chk)


def _extract(tmp_path, source):
    path = tmp_path / "mod.py"
    path.write_text(textwrap.dedent(source))
    old_root = chk.ROOT
    chk.ROOT = tmp_path
    try:
        return chk.extract(path)
    finally:
        chk.ROOT = old_root


def test_extracts_literals_variables_and_concatenation(tmp_path):
    queries = _extract(
        tmp_path,
        '''
        QUERY = "SELECT id FROM users WHERE id=%s"

        def f(db, uid):
            db.execute(QUERY, (uid,))
            sql = "SELECT gold FROM stats "
            sql += "WHERE id=%s"
            db.execute(sql, (uid,))
            db.execute("UPDATE stats SET gold=%s " "WHERE id=%s", (1, uid))
            db.execute("CREATE TABLE IF NOT EXISTS x (id int)")  # DDL: skipped
        ''',
    )
    sqls = sorted(q.sql for q in queries)
    assert "SELECT id FROM users WHERE id=%s" in sqls
    assert "SELECT gold FROM stats WHERE id=%s" in sqls
    assert "UPDATE stats SET gold=%s WHERE id=%s" in sqls
    assert not any("CREATE TABLE" in s for s in sqls)
    assert not any(q.dynamic for q in queries)


def test_fstring_with_constant_is_static_otherwise_dynamic(tmp_path):
    queries = _extract(
        tmp_path,
        '''
        TABLE = "provinces"

        def f(db, col, uid):
            db.execute(f"SELECT id FROM {TABLE} WHERE userid=%s", (uid,))
            db.execute(f"SELECT {col} FROM provinces WHERE userid=%s", (uid,))
        ''',
    )
    by_sql = {q.sql: q for q in queries}
    assert not by_sql["SELECT id FROM provinces WHERE userid=%s"].dynamic
    assert sum(q.dynamic for q in queries) == 1


def test_placeholder_translation():
    assert chk.to_prepare_sql(
        "SELECT 1 FROM t WHERE a=%s AND b IN %s AND c NOT IN %s AND e LIKE 'x%%';"
    ) == "SELECT 1 FROM t WHERE a=$1 AND b = ANY($2) AND c <> ALL($3) AND e LIKE 'x%'"
    assert chk.to_prepare_sql(
        "SELECT 1 FROM t WHERE c IN %(ids)s AND d=%(uid)s AND e=%(ids)s"
    ) == "SELECT 1 FROM t WHERE c = ANY($1) AND d=$2 AND e=$1"


def _local_db():
    dsn = os.getenv("DATABASE_URL", "")
    host = urlparse(dsn).hostname if dsn else None
    return dsn if host in {"localhost", "127.0.0.1", "postgres"} else None


@pytest.mark.skipif(not _local_db(), reason="needs a local DB built from db/schema.sql")
def test_flags_missing_column_like_the_2026_10_03_outage():
    # b027fdab: the revenue tick selected provinces.location, which does not
    # exist (biome lives on stats.location). This must be a hard error.
    bad = chk.Query("x.py", 1, "SELECT id, location FROM provinces WHERE id = %s", False)
    good = chk.Query("x.py", 2, "SELECT id, population FROM provinces WHERE id = %s", False)
    errors, warnings, ok, _ = chk.check([bad, good], _local_db())
    assert [e[0] for e in errors] == [bad]
    assert errors[0][1] == "42703"
    assert ok == 1
