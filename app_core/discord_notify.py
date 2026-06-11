"""Staff/player-facing Discord notifications via webhook."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)


def _webhook_url() -> str | None:
    url = (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()
    return url or None


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
