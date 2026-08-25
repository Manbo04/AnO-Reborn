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
from discord_bot import suggestions_store
from discord_bot.backend import BotBackend
from discord_bot.config import GAME_BASE_URL
from discord_bot.permissions import require_guild_admin

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


def _channel_tag(guild: Optional[discord.Guild], name: str) -> str:
    """Real clickable mention if the channel exists in this guild, else plain text.

    Matches by substring (not equality) because servers commonly prefix channel
    names with an emoji/separator, e.g. the real name is "🐞┃bug-reports", not
    "bug-reports". Searches all channel types (guild.channels), not just
    guild.text_channels -- confirmed live that #bug-reports is a Forum channel,
    which guild.text_channels excludes entirely.
    """
    if guild:
        target = name.lower()
        for channel in guild.channels:
            if target in channel.name.lower() and hasattr(channel, "mention"):
                return channel.mention
    return f"#{name}"


def _find_channel_by_name(guild: Optional[discord.Guild], name: str) -> Optional[discord.TextChannel]:
    """Same substring-match convention as _channel_tag, but returns the real channel."""
    if not guild:
        return None
    target = name.lower()
    for channel in guild.text_channels:
        if target in channel.name.lower():
            return channel
    return None


def _tick_schedule_info() -> dict:
    from datetime import datetime, timezone

    from app_core.celery_schedule import CELERY_BEAT_SCHEDULE

    schedule = CELERY_BEAT_SCHEDULE["global_tick"]["schedule"]
    minutes = sorted(schedule.minute)
    hours = sorted(schedule.hour)

    interval_desc = None
    if hours == list(range(24)) and len(minutes) > 1:
        gaps = {b - a for a, b in zip(minutes, minutes[1:])}
        gaps.add((minutes[0] + 60) - minutes[-1])
        if len(gaps) == 1:
            interval_desc = f"every {gaps.pop()} minutes"
    if interval_desc is None:
        interval_desc = (
            f"at minute(s) {', '.join(str(m) for m in minutes)} "
            f"of hour(s) {', '.join(str(h) for h in hours)} (UTC)"
        )

    now = datetime.now(timezone.utc)
    next_in = schedule.remaining_estimate(now)
    next_at_epoch = int((now + next_in).timestamp())
    return {"interval_desc": interval_desc, "next_at_epoch": next_at_epoch}


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
            "`/stats` `/patreon` `/status` `/changelog` `/site` `/tick` `/bugreport` `/suggest`",
            ephemeral=True,
        )

    @tree.command(name="tick", description="How often the game's economy tick runs, and when the next one fires")
    async def tick_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            info = await asyncio.to_thread(_tick_schedule_info)
        except Exception:
            logger.exception("/tick failed")
            await interaction.followup.send(
                "Couldn't read the tick schedule right now.", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"🕒 The game tick runs **{info['interval_desc']}** "
            "(production, consumption, tax, and upkeep all settle on this cycle).\n"
            f"Next tick: <t:{info['next_at_epoch']}:R> (<t:{info['next_at_epoch']}:t>)."
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
        bugs = _channel_tag(interaction.guild, "bug-reports")
        await interaction.response.send_message(
            f"**Game**: {GAME_BASE_URL}\n**Bugs**: {bugs}", ephemeral=False
        )

    @tree.command(name="bugreport", description="Where and how to report a bug")
    async def bugreport_cmd(interaction: discord.Interaction) -> None:
        bugs = _channel_tag(interaction.guild, "bug-reports")
        await interaction.response.send_message(
            f"Found a bug? Post it in {bugs} with what happened and how to reproduce it -- "
            "that's the one place we actually track them from.",
            ephemeral=True,
        )

    @tree.command(name="suggest", description="Post a suggestion for staff to review")
    @app_commands.describe(text="Your suggestion")
    async def suggest_cmd(interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        config = suggestions_store.get_suggestions_config(guild_id)
        channel = None
        if config.channel_id:
            ch = interaction.guild.get_channel(int(config.channel_id))
            channel = ch if isinstance(ch, discord.TextChannel) else None
        if channel is None:
            channel = _find_channel_by_name(interaction.guild, "suggestions")
        if channel is None:
            await interaction.followup.send(
                "No suggestions channel is configured yet — ask an admin to set one "
                "on the dashboard's Community page.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="New suggestion",
            description=text[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Suggested by {interaction.user} — Pending")
        try:
            message = await channel.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")
        except discord.Forbidden:
            await interaction.followup.send(
                f"Missing permission to post in {channel.mention}.", ephemeral=True
            )
            return

        suggestion_id = suggestions_store.create_suggestion(
            guild_id, str(interaction.user.id), str(channel.id), text
        )
        suggestions_store.set_suggestion_message(suggestion_id, str(message.id))
        await interaction.followup.send(f"Suggestion #{suggestion_id} posted in {channel.mention}.", ephemeral=True)

    suggestion_group = app_commands.Group(
        name="suggestion",
        description="Decide on posted suggestions",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    async def _decide(interaction: discord.Interaction, message_id: str, status: str, label: str) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild.id)
        suggestion = suggestions_store.get_suggestion_by_message(guild_id, message_id)
        if not suggestion:
            await interaction.followup.send("No suggestion found for that message ID.", ephemeral=True)
            return
        suggestions_store.decide_suggestion(suggestion.id, status, str(interaction.user.id))

        channel = interaction.guild.get_channel(int(suggestion.channel_id))
        if isinstance(channel, discord.TextChannel):
            try:
                message = await channel.fetch_message(int(message_id))
                embed = message.embeds[0] if message.embeds else discord.Embed(description=suggestion.content)
                embed.color = {
                    "approved": discord.Color.green(),
                    "denied": discord.Color.red(),
                    "implemented": discord.Color.gold(),
                }.get(status, embed.color)
                embed.set_footer(text=f"{label} by {interaction.user}")
                await message.edit(embed=embed)
            except (discord.NotFound, discord.Forbidden):
                pass
        await interaction.followup.send(f"Suggestion #{suggestion.id} marked {label.lower()}.", ephemeral=True)

    @suggestion_group.command(name="approve", description="Mark a suggestion approved")
    @app_commands.describe(message_id="Message ID of the suggestion embed")
    @require_guild_admin()
    async def suggestion_approve(interaction: discord.Interaction, message_id: str) -> None:
        await _decide(interaction, message_id, "approved", "Approved")

    @suggestion_group.command(name="deny", description="Mark a suggestion denied")
    @app_commands.describe(message_id="Message ID of the suggestion embed")
    @require_guild_admin()
    async def suggestion_deny(interaction: discord.Interaction, message_id: str) -> None:
        await _decide(interaction, message_id, "denied", "Denied")

    @suggestion_group.command(name="implemented", description="Mark a suggestion implemented")
    @app_commands.describe(message_id="Message ID of the suggestion embed")
    @require_guild_admin()
    async def suggestion_implemented(interaction: discord.Interaction, message_id: str) -> None:
        await _decide(interaction, message_id, "implemented", "Implemented")

    tree.add_command(suggestion_group)
