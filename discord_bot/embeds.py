"""Discord embed builders for nation summaries (Locutus-inspired density)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import discord

from discord_bot.config import GAME_BASE_URL

# Prefer combat-relevant units first; skip meta keys on military dict.
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


def _country_url(nation_id: int) -> str:
    return f"{GAME_BASE_URL}/country/id={nation_id}"


def _fmt_num(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _truncate(text: str, limit: int = 1020) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_military(military: Optional[Dict[str, Any]]) -> str:
    if not military:
        return "No military data."
    lines: List[str] = []
    mp = military.get("manpower")
    if mp:
        lines.append(f"**Manpower:** {_fmt_num(mp)}")
    defense = military.get("default_defense")
    if defense:
        lines.append(f"**Defense mode:** {defense}")
    for key in MILITARY_UNIT_ORDER:
        qty = int(military.get(key) or 0)
        if qty > 0:
            label = key.replace("_", " ").title()
            lines.append(f"{label}: {_fmt_num(qty)}")
    for key, qty in sorted(military.items()):
        if key in MILITARY_SKIP_KEYS or key in MILITARY_UNIT_ORDER:
            continue
        qty = int(qty or 0)
        if qty > 0:
            label = str(key).replace("_", " ").title()
            lines.append(f"{label}: {_fmt_num(qty)}")
    return _truncate("\n".join(lines)) if lines else "No units on record."


def _format_resources(resources: Optional[Dict[str, Any]], limit: int = 14) -> str:
    if not resources:
        return "No commodities stored (gold shown above)."
    items = sorted(
        ((k, int(v)) for k, v in resources.items() if int(v or 0) > 0),
        key=lambda x: x[1],
        reverse=True,
    )[:limit]
    if not items:
        return "No commodities stored (gold shown above)."
    return _truncate("\n".join(f"**{name}:** {_fmt_num(qty)}" for name, qty in items))


def _format_coalition(coalition: Optional[Dict[str, Any]]) -> str:
    if not coalition or not coalition.get("coalition_name"):
        return "Independent (no coalition)"
    name = coalition["coalition_name"]
    role = coalition.get("role") or "member"
    col_id = coalition.get("coalition_id")
    tax = coalition.get("tax_rate")
    parts = [f"**{name}** (id {col_id}) — {role}"]
    if tax is not None and int(tax) > 0:
        parts.append(f"Coalition tax: **{int(tax)}%**")
    return "\n".join(parts)


def _format_wars(wars: Optional[List[Dict[str, Any]]], active_count: int) -> Optional[str]:
    if not wars and not active_count:
        return None
    if not wars:
        return f"**{active_count}** active war(s) (details unavailable)."
    lines = [
        f"#{w.get('war_id')}: vs **{w.get('opponent_name', '?')}** "
        f"(id {w.get('opponent_id')}) — **{w.get('side', '?')}**"
        for w in wars[:10]
    ]
    if active_count > len(wars):
        lines.append(f"_+ {active_count - len(wars)} more not listed_")
    return _truncate("\n".join(lines))


def build_nation_embed(data: Dict[str, Any], title: str) -> discord.Embed:
    """Rich nation card: economy, provinces, military, resources, coalition, wars."""
    nation_id = data.get("id")
    username = data.get("username") or "Unknown"
    url = _country_url(nation_id) if nation_id else None

    meta_parts: List[str] = []
    if nation_id is not None:
        meta_parts.append(f"Nation id **{nation_id}**")
    if data.get("join_number") is not None:
        meta_parts.append(f"Member **#{data['join_number']}**")
    if data.get("date_joined"):
        meta_parts.append(f"Joined **{data['date_joined']}**")
    if data.get("last_active"):
        meta_parts.append(f"Last active **{data['last_active']}**")

    description = f"[**{username}**]({url})" if url else f"**{username}**"
    if meta_parts:
        description += "\n" + " · ".join(meta_parts)

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue(),
        url=url,
    )

    embed.add_field(name="Influence (score)", value=_fmt_num(data.get("influence", 0)), inline=True)
    embed.add_field(name="Gold", value=_fmt_num(data.get("gold", 0)), inline=True)
    embed.add_field(name="Provinces", value=_fmt_num(data.get("province_count", 0)), inline=True)

    prov = data.get("provinces") or {}
    embed.add_field(name="Population", value=_fmt_num(prov.get("total_population", 0)), inline=True)
    embed.add_field(name="Cities", value=_fmt_num(prov.get("total_cities", 0)), inline=True)
    embed.add_field(name="Land", value=_fmt_num(prov.get("total_land", 0)), inline=True)

    happiness = prov.get("avg_happiness")
    productivity = prov.get("avg_productivity")
    embed.add_field(
        name="Avg happiness",
        value=f"{float(happiness or 0):.1f}%" if happiness is not None else "—",
        inline=True,
    )
    embed.add_field(
        name="Avg productivity",
        value=f"{float(productivity or 0):.1f}%" if productivity is not None else "—",
        inline=True,
    )
    embed.add_field(
        name="Terrain",
        value=str(data.get("location") or "—"),
        inline=True,
    )

    embed.add_field(
        name="Coalition",
        value=_format_coalition(data.get("coalition")),
        inline=False,
    )

    embed.add_field(
        name="Military",
        value=_format_military(data.get("military")),
        inline=False,
    )

    embed.add_field(
        name="Resources (top holdings)",
        value=_format_resources(data.get("resources")),
        inline=False,
    )

    wars_text = _format_wars(
        data.get("active_wars_list"),
        int(data.get("active_wars") or 0),
    )
    if wars_text:
        embed.add_field(name="Active wars", value=wars_text, inline=False)
    elif int(data.get("active_wars") or 0) == 0:
        embed.add_field(name="Active wars", value="None", inline=False)

    if url:
        embed.add_field(
            name="Links",
            value=f"[Country page]({url}) · [Account]({GAME_BASE_URL}/account)",
            inline=False,
        )

    embed.set_footer(text="Affairs & Order · /wars · /resources · /nation")
    return embed
