"""AnO-themed Discord embed panels for guild channels."""


import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord

from discord_bot.config import GAME_BASE_URL
from discord_bot.panels import data

logger = logging.getLogger(__name__)

ANO_BLUE = discord.Color.from_rgb(45, 95, 145)
ANO_GOLD = discord.Color.from_rgb(201, 162, 39)


def _footer() -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Affairs & Order · {GAME_BASE_URL} · Refreshed: {now_str}"


def build_readme_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📜 Affairs & Order — Discord Commandery",
        description=(
            "Link your **nation** to Discord, then use slash commands to read live game data."
        ),
        color=ANO_BLUE,
    )
    embed.add_field(
        name="🪪 Your nation",
        value=(
            f"• `/register code:XXXXXXXX` — link your nation (code from [Account]({GAME_BASE_URL}/account))\n"
            "• `/me` — your nation dashboard (economy, military, resources, wars)\n"
            "• `/nation` — look up any nation's full stats\n"
            "• `/wars` — list active wars for you or another nation\n"
            "• `/resources` — top resources for you or another nation"
        ),
        inline=False,
    )
    embed.add_field(
        name="ℹ️ Game info",
        value=(
            "• `/stats` — real player/signup numbers\n"
            "• `/patreon` — current patron count and monthly support\n"
            "• `/status` — is the live game up right now\n"
            "• `/changelog` — recently merged game updates\n"
            "• `/tick` — how often the game tick runs and when the next one fires\n"
            "• `/site` — game and community links\n"
            "• `/bugreport` — where and how to report a bug\n"
            "• `/suggest` — log a quick suggestion"
        ),
        inline=False,
    )
    embed.add_field(
        name="🎲 Server fun",
        value=(
            "• `/rank` — your (or someone else's) level and XP\n"
            "• `/leaderboard` — top members by XP in this server\n"
            "• `/poll` — post a quick yes/no poll"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Staff only",
        value=(
            "`/guild_*` `/admin_*` `/levels` `/welcome` `/reactionrole` `/giveaway` — "
            "panels, broadcasts, and server config; non-admins cannot run these."
        ),
        inline=False,
    )
    embed.add_field(
        name="Panels in this server",
        value=(
            "🏆 **influence-board** — top nations by treasury\n"
            "⚔️ **war-feed** — active conflicts\n"
            "🔬 **nation-inspector** — realm statistics\n"
            "🌍 **global-affairs** — world snapshot\n"
            "📢 **realm-alerts** — staff announcements\n"
            "📊 **analytics** — growth chart (staff)"
        ),
        inline=False,
    )
    embed.set_footer(text=_footer())
    return embed


def build_leaderboard_embed(rows: Optional[List[Dict[str, Any]]] = None) -> discord.Embed:
    rows = rows if rows is not None else data.fetch_leaderboard(10)
    embed = discord.Embed(
        title="🏆 Influence Board — Top Nations",
        description="Ranked by **treasury** (gold held).",
        color=ANO_GOLD,
    )
    if not rows:
        embed.add_field(name="—", value="No nations found.", inline=False)
    else:
        lines = []
        for i, row in enumerate(rows, 1):
            loc = row.get("location") or "?"
            lines.append(
                f"**{i}.** [{row['username']}]({GAME_BASE_URL}/country/id={row['id']}) "
                f"— **{int(row.get('influence') or 0):,}** influence · {loc}"
            )
        embed.add_field(name="Top 10", value="\n".join(lines)[:1020], inline=False)
    embed.set_footer(text=_footer())
    return embed


def build_war_feed_embed(wars: Optional[List[Dict[str, Any]]] = None) -> discord.Embed:
    wars = wars if wars is not None else data.fetch_active_wars(12)
    embed = discord.Embed(
        title="⚔️ War Feed — Active Conflicts",
        description="Open wars across the realm. Declare peace in-game to remove entries.",
        color=discord.Color.dark_red(),
    )
    if not wars:
        embed.add_field(name="Status", value="☮️ No active wars.", inline=False)
    else:
        lines = [
            f"**#{w['war_id']}** {w['attacker_name']} vs **{w['defender_name']}** "
            f"({w.get('war_type') or 'war'})"
            for w in wars
        ]
        embed.add_field(name=f"{len(wars)} active", value="\n".join(lines)[:1020], inline=False)
    embed.set_footer(text=_footer())
    return embed


def build_inspector_embed(stats: Optional[Dict[str, Any]] = None) -> discord.Embed:
    stats = stats if stats is not None else data.fetch_realm_inspector()
    embed = discord.Embed(
        title="🔬 Nation Inspector — Realm Telemetry",
        description="Aggregate game database snapshot.",
        color=ANO_BLUE,
    )
    embed.add_field(name="Nations", value=f"{stats['nations']:,}", inline=True)
    embed.add_field(name="Provinces", value=f"{stats['provinces']:,}", inline=True)
    embed.add_field(name="Active wars", value=str(stats["active_wars"]), inline=True)
    embed.add_field(name="Coalitions", value=str(stats["coalitions"]), inline=True)
    embed.add_field(
        name="Coalition members", value=str(stats["coalition_members"]), inline=True
    )
    embed.add_field(
        name="Discord linked", value=str(stats["discord_linked"]), inline=True
    )
    tick = stats.get("last_revenue_tick")
    tick_str = "—"
    if tick is not None:
        if hasattr(tick, "strftime"):
            tick_str = tick.strftime("%Y-%m-%d %H:%M UTC")
        else:
            tick_str = str(tick)
    embed.add_field(name="Last revenue tick", value=tick_str, inline=False)
    embed.set_footer(text=_footer())
    return embed


def build_world_embed(snapshot: Optional[Dict[str, Any]] = None) -> discord.Embed:
    snapshot = snapshot if snapshot is not None else data.fetch_world_snapshot()
    embed = discord.Embed(
        title="🌍 Global Affairs — World Snapshot",
        description="Terrain spread and current economic apex.",
        color=discord.Color.teal(),
    )
    terrain = snapshot.get("terrain_rows") or []
    if terrain:
        lines = []
        for row in terrain:
            loc = row[0] if isinstance(row, (list, tuple)) else row.get("location")
            cnt = row[1] if isinstance(row, (list, tuple)) else row.get("cnt")
            lines.append(f"**{loc}** — {cnt} nations")
        embed.add_field(name="Terrain", value="\n".join(lines)[:1020], inline=False)
    richest = snapshot.get("richest")
    if richest:
        name = richest[0] if isinstance(richest, (list, tuple)) else richest.get("username")
        gold = richest[1] if isinstance(richest, (list, tuple)) else richest.get("gold")
        embed.add_field(
            name="Largest treasury",
            value=f"**{name}** — {int(gold or 0):,} gold",
            inline=False,
        )
    embed.set_footer(text=_footer())
    return embed


def build_alerts_embed(
    *,
    headline: Optional[str] = None,
    body: Optional[str] = None,
) -> discord.Embed:
    embed = discord.Embed(
        title="📢 Realm Alerts",
        description=headline or "Official announcements from server staff.",
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="Latest",
        value=body or "_No active alert. Staff: `/admin_broadcast` to post._",
        inline=False,
    )
    embed.set_footer(text=_footer())
    return embed


ANALYTICS_CHART_FILENAME = "signups_chart.png"


def _render_signup_chart(daily_signups: List[Any]) -> Optional[io.BytesIO]:
    """Real bar chart of daily signups -- returns None (never fabricated
    placeholder data) if there's nothing to plot or matplotlib isn't
    available, so the panel just falls back to text-only stats."""
    if not daily_signups:
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not installed -- analytics panel will be text-only")
        return None

    dates = [str(d) for d, _ in daily_signups]
    counts = [c for _, c in daily_signups]

    try:
        fig, ax = plt.subplots(figsize=(7, 3), dpi=130)
        ax.bar(dates, counts, color="#2D5F91")
        ax.set_title("New signups per day (last 14 days)", fontsize=11, color="#222222")
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.tick_params(axis="y", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        logger.exception("Failed to render signup chart")
        return None


def build_analytics_embed(
    stats: Optional[Dict[str, Any]] = None,
) -> Tuple[discord.Embed, Optional[io.BytesIO]]:
    stats = stats if stats is not None else data.fetch_analytics_snapshot()
    embed = discord.Embed(
        title="📊 Analytics — Growth Snapshot",
        description="Real player growth, pulled live from the game database.",
        color=ANO_BLUE,
    )
    embed.add_field(name="Total nations", value=f"{stats['total_nations']:,}", inline=True)
    embed.add_field(name="Active (24h)", value=f"{stats['dau']:,}", inline=True)
    embed.add_field(name="New signups (24h)", value=f"{stats['signups_24h']:,}", inline=True)

    chart = _render_signup_chart(stats.get("daily_signups") or [])
    if chart is not None:
        embed.set_image(url="attachment://signups_chart.png")
    embed.set_footer(text=_footer())
    return embed, chart


PANEL_BUILDERS = {
    "readme": lambda: build_readme_embed(),
    "leaderboard": lambda: build_leaderboard_embed(),
    "war_feed": lambda: build_war_feed_embed(),
    "inspector": lambda: build_inspector_embed(),
    "world_status": lambda: build_world_embed(),
    "alerts": lambda: build_alerts_embed(),
}

# Panels that also produce an image attachment -- kept separate from
# PANEL_BUILDERS so every existing builder's (embed-only) signature stays
# untouched; panel_service.py checks this dict first.
PANEL_FILE_BUILDERS = {
    "analytics": lambda: build_analytics_embed(),
}
