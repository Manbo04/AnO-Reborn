"""Guard: the war supply system was removed (2026-10-11).

The routes no longer put a "supplies" key in attacker_info/defender_info or
the /wars list dicts. war_v2.html still did `defender_info['supplies'] / 20`
after the removal, and Jinja's Undefined / int raises TypeError, which 500'd
every /war/<id> page for players on the v2 theme. Fail fast if any template
reads a supplies key again.
"""

import pathlib
import re

import pytest

pytestmark = pytest.mark.no_server

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / "templates"
SUPPLIES_KEY = re.compile(r"""\[\s*["']supplies["']\s*\]|\.supplies\b""")


def test_no_template_reads_war_supplies():
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if SUPPLIES_KEY.search(line):
                offenders.append(f"{path.relative_to(TEMPLATES)}:{lineno}")
    assert not offenders, "templates still read removed war supplies: " + ", ".join(
        offenders
    )
