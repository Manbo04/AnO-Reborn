"""Regression: coalition page SQL must interpolate membership table names."""

import re
from pathlib import Path


def _coalition_function_source() -> str:
    text = Path(__file__).resolve().parents[1].joinpath("coalitions.py").read_text()
    match = re.search(r"^def coalition\(.*?(?=^def \w)", text, re.MULTILINE | re.DOTALL)
    assert match, "coalition() not found in coalitions.py"
    return match.group(0)


def test_coalition_function_has_no_non_fstring_members_tbl_sql():
    """Plain db.execute(\"\"\"...) sent literal '{_members_tbl()}' to Postgres (My Coalition 500)."""
    src = _coalition_function_source()
    bad = re.findall(
        r"db\.execute\(\s*\"\"\"[\s\S]{0,1200}?\{_members_tbl\(\)\}",
        src,
    )
    assert not bad, (
        "coalition() has db.execute(\"\"\"...) with {_members_tbl()} — use f\"\"\" instead"
    )


def test_no_literal_brace_members_tbl_fallback():
    text = Path(__file__).resolve().parents[1].joinpath("coalitions.py").read_text()
    assert 'or "{_members_tbl()}"' not in text
