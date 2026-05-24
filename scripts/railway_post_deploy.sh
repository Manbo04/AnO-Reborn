#!/usr/bin/env bash
# Run on Railway after web deploy (requires DATABASE_PUBLIC_URL).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Schema migrations ==="
python3 scripts/apply_all_pending_migrations.py

echo "=== Schema diagnose ==="
python3 scripts/diagnose_schema.py

echo "=== Route SQL replay (user 16) ==="
python3 scripts/diagnose_all_routes.py 16

echo "=== Done ==="
