"""Keeps the test-realm scrub honest as the schema grows (no database needed)."""
import pathlib
import re

import pytest

pytestmark = pytest.mark.no_server

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "db" / "schema.sql").read_text()
SCRUB = (ROOT / "testrealm" / "scrub.sql").read_text()
BUILD = (ROOT / "testrealm" / "build.sh").read_text()

SENSITIVE = re.compile(
    r"email|hash|token|secret|password|\bip\b|ip_addr|address|discord_id|recovery|totp|stripe|patreon|"
    r"phone|api_key|webhook|cookie|session|fingerprint|user_agent|message|content|body|dm_",
    re.I,
)
# Tables that match the pattern but hold public game content or non-personal text.
PUBLIC_OK = {"devlog_entries", "game_tick_logs", "gem_packages", "news", "world_events"}


def schema_tables():
    tables, cur = {}, None
    for line in SCHEMA.splitlines():
        m = re.match(r"CREATE TABLE public\.(\w+) \(", line)
        if m:
            cur = m.group(1)
            tables[cur] = []
            continue
        if line.startswith(");"):
            cur = None
            continue
        if cur:
            col = line.strip().split(" ")[0]
            if col and not col.startswith(("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK")):
                tables[cur].append(col)
    return tables


def test_every_sensitive_table_is_scrubbed_or_marked_public():
    missing = []
    for table, cols in schema_tables().items():
        if not any(SENSITIVE.search(c) for c in cols):
            continue
        if table in PUBLIC_OK or table.startswith("discord_"):
            continue
        if not re.search(rf"\b{table}\b", SCRUB):
            missing.append(table)
    assert not missing, f"Add these tables to testrealm/scrub.sql (or PUBLIC_OK if public): {missing}"


def test_discord_tables_are_truncated():
    assert "discord\\_%" in SCRUB


def test_scrub_references_only_real_tables_and_user_columns():
    tables = schema_tables()
    for stmt in re.findall(r"UPDATE (\w+) SET", SCRUB):
        assert stmt in tables, f"scrub updates unknown table {stmt}"
    trunc = re.search(r"TRUNCATE (.*?);", SCRUB, re.S).group(1)
    for t in re.split(r"[,\s]+", trunc.strip()):
        if t:
            assert t in tables, f"scrub truncates unknown table {t}"
    for col in ("email", "hash", "verification_token", "discord_id", "recovery_key", "totp_secret_encrypted", "totp_enabled"):
        assert col in tables["users"], f"users.{col} missing from schema"
        assert re.search(rf"\b{col}\b", SCRUB)


def test_build_script_has_safety_rails():
    for needle in ("set -euo pipefail", "same database", "must contain 'test'", "verify_scrub.py", "pg_dump"):
        assert needle in BUILD
    assert "psql \"$SOURCE_DATABASE_URL\"" not in BUILD  # source is only dumped, never written


def test_compose_has_no_outbound_credentials():
    text = (ROOT / "testrealm" / "docker-compose.testrealm.yml").read_text()
    for var in ("DISCORD_BOT_TOKEN", "RESEND_API_KEY", "STRIPE_SECRET_KEY", "PATREON_ACCESS_TOKEN"):
        assert re.search(rf'{var}: ""', text)
