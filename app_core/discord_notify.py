"""Staff/player-facing Discord notifications via webhook."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

DISCORD_API_BASE = os.environ.get("API_BASE_URL", "https://discord.com/api")


def _webhook_url() -> str | None:
    url = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
    return url or None


def send_staff_bot_dm(discord_user_id: str, message: str) -> bool:
    """Send a Discord bot DM to a specific staff/admin Discord user id.

    Reuses the same bot-DM pattern already proven live in this codebase
    (change.py's send_discord_password_reset_dm) -- unlike DISCORD_WEBHOOK_URL
    (unset in this deployment as of 2026-09-13, so _post() above silently
    no-ops), DISCORD_BOT_TOKEN is actually configured, so this is the real,
    working notification path today. Added for the identity_diagnostic_log
    CRITICAL-severity tripwire (app_core/identity_diagnostics.py) so an
    anomaly pages a real person immediately instead of sitting in a DB row
    until someone thinks to query it.
    """
    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    if not bot_token or not discord_user_id:
        return False

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    try:
        channel_resp = requests.post(
            f"{DISCORD_API_BASE}/users/@me/channels",
            headers=headers,
            json={"recipient_id": str(discord_user_id)},
            timeout=10,
        )
        if not channel_resp.ok:
            logger.warning(
                "send_staff_bot_dm: channel create failed: status=%s body=%s",
                channel_resp.status_code,
                channel_resp.text[:200],
            )
            return False

        channel_id = channel_resp.json().get("id")
        if not channel_id:
            return False

        msg_resp = requests.post(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=headers,
            json={"content": message[:1900]},
            timeout=10,
        )
        if not msg_resp.ok:
            logger.warning(
                "send_staff_bot_dm: send failed: status=%s body=%s",
                msg_resp.status_code,
                msg_resp.text[:200],
            )
            return False
        return True
    except Exception:
        logger.exception("send_staff_bot_dm failed")
        return False


def _post(content: str) -> None:
    url = _webhook_url()
    if not url or not content:
        return
    try:
        requests.post(
            url,
            json={"content": content[:1900], "username": "Affairs & Order"},
            timeout=8,
        )
    except Exception:
        logger.exception("Discord webhook post failed")


def notify_war_result(
    attacker_name: str,
    defender_name: str,
    winner: str,
    win_condition: str | None = None,
) -> None:
    cond = f" ({win_condition})" if win_condition else ""
    _post(
        f"**War resolved** — {attacker_name} vs {defender_name}\n"
        f"Winner: **{winner}**{cond}"
    )


def notify_peace_offer(sender_name: str, recipient_name: str) -> None:
    _post(f"**Peace offer** — {sender_name} → {recipient_name}")


def notify_trade_failure(buyer_name: str, seller_name: str, resource: str) -> None:
    _post(
        f"**Trade agreement failed** — {buyer_name} / {seller_name} ({resource})"
    )
