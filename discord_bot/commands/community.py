"""Community-facing utility commands: server stats, Patreon, live status,
changelog, bug reports, and suggestions.

Deliberately read-only/informational, matching the same principle as the
rest of this bot -- these make things easier to look up, they never touch
gameplay decisions (no war calculators, no market timing, no
nation-optimization tools).
"""

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Optional

import discord
from discord import app_commands

from database import QueryHelper
from discord_bot.backend import BotBackend
from discord_bot.config import GAME_BASE_URL

logger = logging.getLogger(__name__)

GITHUB_REPO = "Manbo04/AnO-Reborn"


def _get_signup_stats() -> dict:
    total = QueryHelper.fetch_one(
        "SELECT COUNT(*) FROM users WHERE COALESCE(auth_type, 'normal') = 'normal'"
    )
    signups_24h = QueryHelper.fetch_one(
        "SELECT COUNT(*) FROM users WHERE date >= to_char(NOW() - INTERVAL '24 hours', 'YYYY-MM-DD')"
    )
    dau = QueryHelper.fetch_one(
        "SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '24 hours'"
    )
    return {
        "total": int(total[0]) if total else 0,
        "signups_24h": int(signups_24h[0]) if signups_24h else 0,
        "dau": int(dau[0]) if dau else 0,
    }


def _get_patreon_stats() -> Optional[dict]:
    token = os.getenv("PATREON_ACCESS_TOKEN")
    campaign_id = os.getenv("PATREON_CAMPAIGN_ID")
    if not token or not campaign_id:
        return None
    fields = "patron_status,currently_entitled_amount_cents"
    url = (
        f"https://www.patreon.com/api/oauth2/v2/campaigns/{campaign_id}/members"
        f"?page%5Bcount%5D=200&fields%5Bmember%5D={fields}"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.exception("Patreon fetch failed")
        return None
    members = data.get("data", [])
    active = [
        m for m in members
        if m.get("attributes", {}).get("patron_status") == "active_patron"
        and m.get("attributes", {}).get("currently_entitled_amount_cents", 0) > 0
    ]
    cents = sum(m["attributes"]["currently_entitled_amount_cents"] for m in active)
    return {"count": len(active), "monthly_usd": round(cents / 100, 2)}


def _check_site_status() -> str:
    start = time.time()
    try:
        req = urllib.request.Request(GAME_BASE_URL, method="HEAD", headers={"User-Agent": "AnO-Bot-StatusCheck/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            elapsed_ms = round((time.time() - start) * 1000)
            return f"🟢 {GAME_BASE_URL} is up (HTTP {resp.status}, {elapsed_ms}ms)."
    except urllib.error.HTTPError as e:
        elapsed_ms = round((time.time() - start) * 1000)
        return f"🟡 {GAME_BASE_URL} responded with HTTP {e.code} ({elapsed_ms}ms)."
    except Exception:
        return f"🔴 {GAME_BASE_URL} didn't respond within 8s -- might be down."


def _fetch_changelog() -> str:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls?state=closed&sort=updated&direction=desc&per_page=10"
    req = urllib.request.Request(url, headers={"User-Agent": "AnO-Bot-Changelog/1.0", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            prs = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"Couldn't pull recent changes right now: {e}"

    merged = [p for p in prs if p.get("merged_at")][:5]
    if not merged:
        return "No recently merged changes to show."
    lines = ["**Recent changes**"]
    for p in merged:
        date = p["merged_at"][:10]
        lines.append(f"• {p['title']} (#{p['number']}, {date})")
    return "\n".join(lines)


def register_commands(tree: app_commands.CommandTree, backend: BotBackend) -> None:
    @tree.command(name="help", description="List available bot commands")
    async def help_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "**Player commands**\n"
            "`/register` `/me` `/nation` `/wars` `/resources` — link and check nation data\n\n"
            "**Info commands**\n"
            "`/stats` `/patreon` `/status` `/changelog` `/site` `/bugreport` `/suggest`",
            ephemeral=True,
        )

    @tree.command(name="stats", description="Real player/signup numbers")
    async def stats_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            s = await asyncio.to_thread(_get_signup_stats)
            await interaction.followup.send(
                f"{s['total']:,} total nations ({s['signups_24h']} new in the last 24h). "
                f"{s['dau']:,} active in the last day."
            )
        except Exception:
            logger.exception("/stats failed")
            await interaction.followup.send("Couldn't pull stats right now.", ephemeral=True)

    @tree.command(name="patreon", description="Current patron count and monthly support")
    async def patreon_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        stats = await asyncio.to_thread(_get_patreon_stats)
        if stats is None:
            await interaction.followup.send("Patreon isn't wired up right now.", ephemeral=True)
            return
        await interaction.followup.send(
            f"{stats['count']} paying patron(s) right now, ${stats['monthly_usd']}/mo. "
            f"Thank you to everyone supporting the game."
        )

    @tree.command(name="status", description="Is the live game up right now")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        msg = await asyncio.to_thread(_check_site_status)
        await interaction.followup.send(msg)

    @tree.command(name="changelog", description="Recently merged game updates")
    async def changelog_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        msg = await asyncio.to_thread(_fetch_changelog)
        await interaction.followup.send(msg)

    @tree.command(name="site", description="Game and community links")
    async def site_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"**Game**: {GAME_BASE_URL}\n**Bugs**: #bug-reports", ephemeral=False
        )

    @tree.command(name="bugreport", description="Where and how to report a bug")
    async def bugreport_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Found a bug? Post it in #bug-reports with what happened and how to reproduce it -- "
            "that's the one place we actually track them from.",
            ephemeral=True,
        )

    @tree.command(name="suggest", description="Log a quick suggestion")
    @app_commands.describe(text="Your suggestion")
    async def suggest_cmd(interaction: discord.Interaction, text: str) -> None:
        await interaction.response.send_message(
            f"Got it: \"{text}\" -- also worth posting in #suggestions so it doesn't get lost "
            "and others can react to it.",
            ephemeral=True,
        )
