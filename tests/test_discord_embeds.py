"""Discord nation embed formatting."""
from discord_bot.embeds import (
    _format_military,
    _format_resources_grid,
    _fmt_compact,
    build_nation_embed,
)


def test_fmt_compact_billions():
    assert _fmt_compact(19_397_876_921) == "19.40B"


def test_format_military_includes_units():
    text = _format_military(
        {"manpower": 50000, "soldiers": 1000, "tanks": 50, "default_defense": "balanced"}
    )
    assert "Manpower" in text
    assert "Soldiers" in text
    assert "Tanks" in text
    assert "Defense" in text


def test_format_resources_grid_sorted():
    text = _format_resources_grid({"steel": 100, "gold_commodity": 1, "oil": 5000})
    assert "oil" in text.lower()
    assert "```" in text


def test_build_nation_embed_has_grouped_fields():
    embed = build_nation_embed(
        {
            "id": 27,
            "username": "Testland",
            "influence": 1000,
            "gold": 1_000_000,
            "province_count": 2,
            "location": "Tundra",
            "provinces": {
                "total_population": 2_000_000,
                "total_cities": 5,
                "total_land": 100,
                "avg_happiness": 72.5,
                "avg_productivity": 80.0,
            },
            "coalition": {"coalition_name": "Test Col", "role": "leader", "coalition_id": 1},
            "military": {"soldiers": 500},
            "resources": {"steel": 1000},
            "active_wars": 0,
            "active_wars_list": [],
        },
        "Your nation",
    )
    names = {f.name for f in embed.fields}
    assert "⚔️ Military" in names
    assert "📦 Commodities" in names
    assert "👥 Population" in names
    assert embed.title == "🏛️ Testland"
