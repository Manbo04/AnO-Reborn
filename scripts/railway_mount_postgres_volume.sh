#!/usr/bin/env bash
# Attach the floating postgres-volume to the Postgres service on Railway.
#
# Prereqs:
#   npm i -g @railway/cli   # or: npx @railway/cli
#   railway login
#   railway link            # select project: natural-gratitude, env: production
#
# SAFETY:
#   - Postgres must have exactly ONE volume at /var/lib/postgresql/data
#   - The May 8 snapshot volume may be EMPTY (economy froze when it was attached)
#   - The floating "postgres-volume" is likely the LIVE data — attach that one
#
# Usage:
#   ./scripts/railway_mount_postgres_volume.sh
#   ./scripts/railway_mount_postgres_volume.sh --dry-run
#   VOLUME_NAME=postgres-volume SERVICE=Postgres ./scripts/railway_mount_postgres_volume.sh

set -euo pipefail

MOUNT_PATH="/var/lib/postgresql/data"
VOLUME_NAME="${VOLUME_NAME:-postgres-volume}"
SERVICE_NAME="${SERVICE:-Postgres}"
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

if ! command -v railway >/dev/null 2>&1; then
  echo "Install Railway CLI: npm i -g @railway/cli"
  exit 1
fi

echo "=== Railway volume audit ==="
echo "Project context:"
railway status || { echo "Run: railway login && railway link"; exit 1; }

echo ""
echo "All volumes (JSON):"
railway volume list --json 2>/dev/null || railway volume list

echo ""
echo "Volumes on service '${SERVICE_NAME}':"
railway volume list --service "$SERVICE_NAME" --json 2>/dev/null \
  || railway volume list --service "$SERVICE_NAME" || true

echo ""
echo "Plan:"
echo "  1. Detach any extra volume on ${SERVICE_NAME} mounted at ${MOUNT_PATH}"
echo "     (e.g. postgres-2026-05-08-* if that volume is empty / wrong)"
echo "  2. Attach '${VOLUME_NAME}' to ${SERVICE_NAME} at ${MOUNT_PATH}"
echo "  3. Redeploy Postgres, then web + celery-worker + beat"
echo ""

if [[ "$DRY_RUN" == true ]]; then
  echo "Dry run — no changes made."
  echo "To attach manually:"
  echo "  railway volume attach --volume ${VOLUME_NAME} --service ${SERVICE_NAME} --mount-path ${MOUNT_PATH} -y"
  exit 0
fi

read -r -p "Detach ALL volumes from ${SERVICE_NAME} first? [y/N] " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
  while read -r vid; do
    [[ -z "$vid" ]] && continue
    echo "Detaching volume $vid ..."
    railway volume detach --volume "$vid" --service "$SERVICE_NAME" -y || true
  done < <(railway volume list --service "$SERVICE_NAME" --json 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join(v.get('id','') for v in (d if isinstance(d,list) else d.get('volumes',[]))))" 2>/dev/null || true)
fi

echo "Attaching ${VOLUME_NAME} -> ${SERVICE_NAME}:${MOUNT_PATH}"
railway volume attach \
  --volume "$VOLUME_NAME" \
  --service "$SERVICE_NAME" \
  --mount-path "$MOUNT_PATH" \
  -y

echo ""
echo "Done. In Railway dashboard:"
echo "  1. Open Postgres -> Settings -> Volume: should show ${VOLUME_NAME} at ${MOUNT_PATH}"
echo "  2. Deploy Postgres (wait for healthy)"
echo "  3. Deploy beat, celery-worker, web"
echo "  4. Verify: DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py"
echo "     user_economy.updated_at should be within the last hour after tasks run."
