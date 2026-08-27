"""Discord embed builders for nation summaries."""


# Bump when embed layout changes — visible in footer so you can confirm bot deploy.
EMBED_UI_VERSION = "2.1"

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord

from discord_bot.config import GAME_BASE_URL

ANO_BLUE = discord.Color.from_rgb(45, 95, 145)
ANO_GOLD = discord.Color.from_rgb(201, 162, 39)
ANO_CRIMSON = discord.Color.from_rgb(140, 45, 55)

MILITARY_UNIT_ORDER = (
    "soldiers",
    "tanks",
    "artillery",
    "fighters",
    "bombers",
    "apaches",
    "submarines",
    "destroyers",
    "cruisers",
    "icbms",
    "nukes",
    "spies",
)

MILITARY_SKIP_KEYS = frozenset({"default_defense", "manpower"})

UNIT_EMOJI = {
    "soldiers": "🪖",
    "tanks": "🛡️",
    "artillery": "💣",
    "fighters": "✈️",
    "bombers": "🎯",
    "apaches": "🚁",
    "submarines": "🌊",
    "destroyers": "⚓",
    "cruisers": "🚢",
    "icbms": "🚀",
    "nukes": "☢️",
    "spies": "🕵️",
}

RESOURCE_EMOJI = {
    "rations": "🌾",
    "coal": "⛏️",
    "oil": "🛢️",
    "copper": "🔶",
    "lumber": "🪵",
    "steel": "🔩",
    "uranium": "☢️",
    "bauxite": "🪨",
    "lead": "⚙️",
    "components": "⚙️",
    "gold": "💰",
    "consumer_goods": "🛒",
    "aluminium": "🔧",
    "iron": "⛓️",
    "energy": "⚡",
}


def _country_url(nation_id: int) -> str:
    return f"{GAME_BASE_URL}/country/id={nation_id}"


def _fmt_num(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_compact(value: Any) -> str:
    """Human-readable large numbers for embed density."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _truncate(text: str, limit: int = 1020) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _pct_bar(value: Optional[float], *, width: int = 8) -> str:
    try:
        pct = max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        return "—"
    filled = int(round(pct / 100 * width))
    bar = "▰" * filled + "▱" * (width - filled)
    if pct >= 70:
        mood = "🟢"
    elif pct >= 40:
        mood = "🟡"
    else:
        mood = "🔴"
    return f"{mood} `{bar}` **{pct:.1f}%**"


def _format_military(military: Optional[Dict[str, Any]]) -> str:
    if not military:
        return "_No military data on file._"
    lines: List[str] = []
    mp = int(military.get("manpower") or 0)
    if mp:
        lines.append(f"👥 **Manpower** · {_fmt_compact(mp)} ({_fmt_num(mp)})")
    defense = military.get("default_defense")
    if defense:
        lines.append(f"🛡️ **Defense** · {defense}")

    chips: List[str] = []
    for key in MILITARY_UNIT_ORDER:
        qty = int(military.get(key) or 0)
        if qty > 0:
            emoji = UNIT_EMOJI.get(key, "•")
            label = key.replace("_", " ").title()
            chips.append(f"{emoji} {label} **{_fmt_num(qty)}**")
    for key, qty in sorted(military.items()):
        if key in MILITARY_SKIP_KEYS or key in MILITARY_UNIT_ORDER:
            continue
        qty = int(qty or 0)
        if qty > 0:
            label = str(key).replace("_", " ").title()
            chips.append(f"• {label} **{_fmt_num(qty)}**")

    if chips:
        lines.append(_truncate(" · ".join(chips), 980))
    elif not lines:
        return "_No units deployed._"
    return _truncate("\n".join(lines))


def _format_resources_grid(resources: Optional[Dict[str, Any]], limit: int = 12) -> str:
    if not resources:
        return "_No commodities stored (treasury gold is listed above)._"
    items = sorted(
        ((k, int(v)) for k, v in resources.items() if int(v or 0) > 0),
        key=lambda x: x[1],
        reverse=True,
    )[:limit]
    if not items:
        return "_No commodities stored._"

    # Two-column monospace grid for scanability
    rows: List[str] = []
    half = (len(items) + 1) // 2
    left = items[:half]
    right = items[half:]
    for i in range(half):
        l_name, l_qty = left[i]
        l_emoji = RESOURCE_EMOJI.get(l_name, "▫️")
        l_cell = f"{l_emoji}`{l_name[:10]:<10}` {_fmt_compact(l_qty):>7}"
        if i < len(right):
            r_name, r_qty = right[i]
            r_emoji = RESOURCE_EMOJI.get(r_name, "▫️")
            r_cell = f"{r_emoji}`{r_name[:10]:<10}` {_fmt_compact(r_qty):>7}"
            rows.append(f"{l_cell}  {r_cell}")
        else:
            rows.append(l_cell)
    return "```\n" + "\n".join(rows) + "\n```"


def _format_coalition(coalition: Optional[Dict[str, Any]]) -> str:
    if not coalition or not coalition.get("coalition_name"):
        return "🏳️ **Independent** — no coalition"
    name = coalition["coalition_name"]
    role = coalition.get("role") or "member"
    col_id = coalition.get("coalition_id")
    tax = coalition.get("tax_rate")
    line = f"🤝 **{name}** · #{col_id} · _{role}_"
    if tax is not None and int(tax) > 0:
        line += f" · **{int(tax)}%** coalition tax"
    return line


def _format_wars(wars: Optional[List[Dict[str, Any]]], active_count: int) -> Optional[str]:
    if not wars and not active_count:
        return None
    if not wars:
        return f"⚔️ **{active_count}** active war(s) — open the game for details."
    lines: List[str] = []
    for w in wars[:8]:
        opp = w.get("opponent_name", "?")
        oid = w.get("opponent_id")
        if oid is not None:
            try:
                opp = f"[{opp}]({_country_url(int(oid))})"
            except (TypeError, ValueError):
                opp = f"**{opp}**"
        else:
            opp = f"**{opp}**"
        lines.append(
            f"**#{w.get('war_id')}** vs {opp} · you are **{w.get('side', '?')}**"
        )
    if active_count > len(wars):
        lines.append(f"_…and {active_count - len(wars)} more_")
    return _truncate("\n".join(lines))


def _title_for_context(title: str, username: str) -> Tuple[str, discord.Color]:
    lower = title.lower()
    if "your nation" in lower or "resources" in lower:
        return f"🏛️ {username}", ANO_GOLD
    if "staff" in lower or "intel" in lower or "linked" in lower:
        return f"🔎 {username}", ANO_CRIMSON
    return f"🏛️ {username}", ANO_BLUE


def build_nation_embed(data: Dict[str, Any], title: str) -> discord.Embed:
    """Nation dashboard card: grouped stats, compact numbers, AnO theme."""
    nation_id = data.get("id")
    username = data.get("username") or "Unknown"
    url = _country_url(nation_id) if nation_id else None
    prov = data.get("provinces") or {}

    embed_title, color = _title_for_context(title, username)
    meta_lines: List[str] = []
    if nation_id is not None:
        meta_lines.append(f"**Nation #{nation_id}**")
    if data.get("join_number") is not None:
        meta_lines.append(f"Member **#{data['join_number']}**")
    if url:
        meta_lines.append(f"[Country page]({url})")

    description_parts: List[str] = []
    if meta_lines:
        description_parts.append(" · ".join(meta_lines))
    sub: List[str] = []
    if data.get("date_joined"):
        sub.append(f"📅 Joined **{data['date_joined']}**")
    if data.get("last_active"):
        sub.append(f"🕐 Active **{data['last_active']}**")
    if sub:
        description_parts.append("\n".join(sub))

    embed = discord.Embed(
        title=embed_title,
        description="\n".join(description_parts) if description_parts else None,
        color=color,
        url=url,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=title, url=url or GAME_BASE_URL)

    gold = int(data.get("gold") or 0)
    embed.add_field(
        name="💰 Treasury",
        value=f"**{_fmt_compact(gold)}**\n`{_fmt_num(gold)}` gold",
        inline=True,
    )
    embed.add_field(
        name="📊 Influence",
        value=f"**{_fmt_compact(data.get('influence', 0))}**\n`{_fmt_num(data.get('influence', 0))}`",
        inline=True,
    )
    embed.add_field(
        name="🗺️ Provinces",
        value=f"**{_fmt_num(data.get('province_count', 0))}**",
        inline=True,
    )

    embed.add_field(
        name="👥 Population",
        value=f"**{_fmt_compact(prov.get('total_population', 0))}**\n`{_fmt_num(prov.get('total_population', 0))}`",
        inline=True,
    )
    embed.add_field(
        name="🏙️ Cities",
        value=f"**{_fmt_num(prov.get('total_cities', 0))}**",
        inline=True,
    )
    embed.add_field(
        name="📐 Land",
        value=f"**{_fmt_num(prov.get('total_land', 0))}**",
        inline=True,
    )

    happiness = prov.get("avg_happiness")
    productivity = prov.get("avg_productivity")
    embed.add_field(
        name="😊 Happiness",
        value=_pct_bar(happiness),
        inline=True,
    )
    embed.add_field(
        name="⚙️ Productivity",
        value=_pct_bar(productivity),
        inline=True,
    )
    terrain = str(data.get("location") or "—")
    embed.add_field(
        name="🌍 Terrain",
        value=f"**{terrain}**",
        inline=True,
    )

    embed.add_field(
        name="🤝 Coalition",
        value=_format_coalition(data.get("coalition")),
        inline=False,
    )

    embed.add_field(
        name="⚔️ Military",
        value=_format_military(data.get("military")),
        inline=False,
    )

    embed.add_field(
        name="📦 Commodities",
        value=_format_resources_grid(data.get("resources")),
        inline=False,
    )

    wars_text = _format_wars(
        data.get("active_wars_list"),
        int(data.get("active_wars") or 0),
    )
    if wars_text:
        embed.add_field(name="⚔️ Active wars", value=wars_text, inline=False)
    else:
        embed.add_field(name="☮️ Wars", value="_No active wars._", inline=False)

    embed.set_footer(
        text=f"Affairs & Order · embed UI {EMBED_UI_VERSION} · /me · /nation · /wars · /resources",
    )
    return embed


_REENGAGE_BANNER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "static", "images", "dm_reengage_banner.jpg"
)


def build_reengagement_embed() -> Tuple[discord.Embed, Optional[discord.File]]:
    """Re-engagement DM: short nudge back to the game, banner image, one CTA button."""
    embed = discord.Embed(
        title="Remember Affairs and Order?",
        description=(
            "The game is live and worth another look — build your nation, forge "
            "alliances, wage war, and climb the leaderboard alongside a real, "
            "growing community.\n\n"
            "We're building this in the open. Come tell us what you think."
        ),
        color=ANO_BLUE,
        url=GAME_BASE_URL,
    )
    file: Optional[discord.File] = None
    if os.path.isfile(_REENGAGE_BANNER_PATH):
        file = discord.File(_REENGAGE_BANNER_PATH, filename="dm_reengage_banner.jpg")
        embed.set_image(url="attachment://dm_reengage_banner.jpg")
    embed.set_footer(text=f"Affairs & Order · {GAME_BASE_URL}")
    return embed, file


def build_reengagement_view() -> discord.ui.View:
    view = discord.ui.View()
    view.add_item(
        discord.ui.Button(
            label="Play Now",
            style=discord.ButtonStyle.link,
            url=GAME_BASE_URL,
            emoji="🕊️",
        )
    )
    return view
