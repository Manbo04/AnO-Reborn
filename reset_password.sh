#!/bin/bash
# Deploy and run password reset on Railway
#
# Usage: ./reset_password.sh <username> [new_password]
# If new_password is omitted, you'll be prompted (input hidden).

set -euo pipefail

USERNAME="${1:?Usage: ./reset_password.sh <username> [new_password]}"
NEW_PASSWORD="${2:-}"

if [ -z "$NEW_PASSWORD" ]; then
    read -r -s -p "New password for $USERNAME: " NEW_PASSWORD
    echo
fi

railway run python3 admin_reset_password.py "$USERNAME" "$NEW_PASSWORD"
