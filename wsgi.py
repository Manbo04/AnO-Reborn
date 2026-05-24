"""WSGI entry — run migrations before workers serve traffic (Procfile-safe)."""

from __future__ import annotations

import os


def _boot_once() -> None:
    """Idempotent startup: SQL migrations + schema compat (survives Procfile-only gunicorn)."""
    if os.getenv("ANO_BOOT_DONE") == "1":
        return
    os.environ["ANO_BOOT_MARKER"] = os.getenv("RAILWAY_GIT_COMMIT_SHA", "local")[:12]
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[wsgi] No DATABASE_URL — skip boot migrations")
        os.environ["ANO_BOOT_DONE"] = "1"
        return
    try:
        import subprocess
        import sys

        r = subprocess.run(
            [sys.executable, "scripts/apply_all_pending_migrations.py"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if r.stdout:
            print(r.stdout.strip()[:2000])
        if r.returncode != 0:
            print(f"[wsgi] WARN migrations exit {r.returncode}: {(r.stderr or '')[:500]}")
    except Exception as exc:
        print(f"[wsgi] WARN apply_all_pending_migrations: {exc}")
    try:
        from database import ensure_schema_compat, schema_compat_succeeded

        ensure_schema_compat()
        print(f"[wsgi] schema_compat={'ok' if schema_compat_succeeded() else 'failed'}")
    except Exception as exc:
        print(f"[wsgi] WARN ensure_schema_compat: {exc}")
    os.environ["ANO_BOOT_DONE"] = "1"


_boot_once()

from app import app  # noqa: E402

if __name__ == "__main__":
    app.run()
