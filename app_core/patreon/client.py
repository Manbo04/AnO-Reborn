"""Patreon API v2 client.

Read-only. Three entry points:
  - fetch_campaign_summary(): patron count + monthly $ (used by /patreon).
  - fetch_campaign_tiers(): the campaign's published tier catalog (name +
    price), used by /patreon to list the Gems bonus per tier.
  - fetch_active_members(): per-patron tier + linked Discord account, used
    by the monthly Gems bonus (see app_core/patreon/service.py).

There is no "connect your Patreon to AnO" flow -- a patron is matched to
their AnO account purely via their Discord account, which Patreon already
exposes through fields[user]=social_connections once they've linked Discord
on Patreon's side. NOTE: that response shape (social_connections.discord.
user_id) is documented by Patreon but has not been exercised against a real
campaign yet -- PATREON_ACCESS_TOKEN/PATREON_CAMPAIGN_ID aren't configured
in any environment as of this writing. Verify live once they are.
"""
import json
import logging
import os
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

_MEMBERS_URL = "https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members"
_CAMPAIGN_URL = "https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}"
_SUMMARY_FIELDS = "patron_status,currently_entitled_amount_cents"
_MEMBER_FIELDS = "patron_status,currently_entitled_amount_cents"
_TIER_FIELDS = "title,amount_cents,published"
_USER_FIELDS = "social_connections"
_MAX_PAGES = 25  # hard cap so a malformed/looping cursor can't run forever


def is_configured() -> bool:
    return bool(os.getenv("PATREON_ACCESS_TOKEN")) and bool(os.getenv("PATREON_CAMPAIGN_ID"))


def _get(url: str) -> Optional[dict]:
    token = os.getenv("PATREON_ACCESS_TOKEN")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_campaign_summary() -> Optional[dict]:
    """Returns {"count": int, "monthly_usd": float} for active, paying
    patrons, or None if not configured / the API call fails."""
    if not is_configured():
        return None
    campaign_id = os.getenv("PATREON_CAMPAIGN_ID")
    url = (
        _MEMBERS_URL.format(campaign_id=campaign_id)
        + f"?page%5Bcount%5D=200&fields%5Bmember%5D={_SUMMARY_FIELDS}"
    )
    try:
        data = _get(url)
    except Exception:
        logger.exception("Patreon summary fetch failed")
        return None
    members = data.get("data", [])
    active = [
        m for m in members
        if m.get("attributes", {}).get("patron_status") == "active_patron"
        and m.get("attributes", {}).get("currently_entitled_amount_cents", 0) > 0
    ]
    cents = sum(m["attributes"]["currently_entitled_amount_cents"] for m in active)
    return {"count": len(active), "monthly_usd": round(cents / 100, 2)}


def fetch_campaign_tiers() -> Optional[list]:
    """Returns the campaign's published tiers, cheapest first:
        [{"title": str, "amount_cents": int}, ...]

    Returns None if not configured or the API call fails.
    """
    if not is_configured():
        return None
    campaign_id = os.getenv("PATREON_CAMPAIGN_ID")
    url = (
        _CAMPAIGN_URL.format(campaign_id=campaign_id)
        + f"?include=tiers&fields%5Btier%5D={_TIER_FIELDS}"
    )
    try:
        data = _get(url)
    except Exception:
        logger.exception("Patreon tiers fetch failed")
        return None
    tiers = [
        {
            "title": item.get("attributes", {}).get("title"),
            "amount_cents": item.get("attributes", {}).get("amount_cents", 0),
        }
        for item in data.get("included", [])
        if item.get("type") == "tier" and item.get("attributes", {}).get("published")
    ]
    tiers.sort(key=lambda t: t["amount_cents"])
    return tiers


def fetch_active_members() -> Optional[list]:
    """Returns a list of dicts, one per (active patron, entitled tier):
        {"member_id": str, "tier_title": str, "discord_id": str or None}

    A patron on multiple tiers appears once per tier -- callers that want a
    single grant per patron should dedupe (see service.py).

    Returns None if not configured, or if any page of the API call fails.
    Callers must treat None as "don't touch anything this run", never as
    "zero patrons" -- an API hiccup must never look like a mass-revoke.
    """
    if not is_configured():
        return None
    campaign_id = os.getenv("PATREON_CAMPAIGN_ID")
    url = (
        _MEMBERS_URL.format(campaign_id=campaign_id)
        + f"?page%5Bcount%5D=200"
        + f"&include=currently_entitled_tiers,user"
        + f"&fields%5Bmember%5D={_MEMBER_FIELDS}"
        + f"&fields%5Btier%5D={_TIER_FIELDS}"
        + f"&fields%5Buser%5D={_USER_FIELDS}"
    )

    results = []
    pages = 0
    while url and pages < _MAX_PAGES:
        pages += 1
        try:
            data = _get(url)
        except Exception:
            logger.exception("Patreon members fetch failed (page %d)", pages)
            return None

        included = data.get("included", [])
        tiers_by_id = {
            item["id"]: item.get("attributes", {}).get("title")
            for item in included if item.get("type") == "tier"
        }
        social_by_user_id = {
            item["id"]: item.get("attributes", {}).get("social_connections") or {}
            for item in included if item.get("type") == "user"
        }

        for member in data.get("data", []):
            attrs = member.get("attributes", {})
            if attrs.get("patron_status") != "active_patron":
                continue
            if not attrs.get("currently_entitled_amount_cents"):
                continue

            rel = member.get("relationships", {})
            tier_refs = (rel.get("currently_entitled_tiers", {}) or {}).get("data") or []
            user_ref = (rel.get("user", {}) or {}).get("data") or {}
            social = social_by_user_id.get(user_ref.get("id")) or {}
            discord_id = (social.get("discord") or {}).get("user_id")

            for tier_ref in tier_refs:
                title = tiers_by_id.get(tier_ref.get("id"))
                if not title:
                    continue
                results.append({
                    "member_id": member.get("id"),
                    "tier_title": title,
                    "discord_id": discord_id,
                })

        url = (data.get("links", {}) or {}).get("next")

    return results
