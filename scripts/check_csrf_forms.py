#!/usr/bin/env python3
"""Warn if POST forms in templates lack explicit csrf_token (layout JS is not enough)."""


import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Auth flows may submit before layout JS injects CSRF (reCAPTCHA); require explicit token.
AUTH_TEMPLATES = {
    "login.html",
    "signup.html",
    "forgot_password.html",
    "reset_password.html",
    "reset_password_discord.html",
}
FORM_RE = re.compile(r"<form[^>]+method=[\"']POST[\"'][^>]*>", re.I)
CSRF_RE = re.compile(r"csrf_token", re.I)
FAILED = []


def main() -> int:
    for path in sorted((ROOT / "templates").rglob("*.html")):
        if path.name not in AUTH_TEMPLATES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in FORM_RE.finditer(text):
            start = match.start()
            end = text.find("</form>", start)
            if end == -1:
                continue
            chunk = text[start:end]
            if not CSRF_RE.search(chunk):
                rel = path.relative_to(ROOT)
                FAILED.append(str(rel))
                break
    if FAILED:
        print("POST forms missing explicit csrf_token in:")
        for f in FAILED:
            print(f"  {f}")
        return 1
    print("OK: all template POST forms include csrf_token or none found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
