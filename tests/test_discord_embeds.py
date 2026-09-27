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


def _field(embed, name):
    return next(f.value for f in embed.fields if f.name == name)


def test_public_view_hides_owner_only_sections_and_keeps_public_stats():
    embed = build_nation_embed(
        {
            "id": 27,
            "username": "Testland",
            "influence": 1000,
            "gold": 11_919_128_893,
            "province_count": 100,
            "location": "Boreal Forest",
            "provinces": {"total_population": 5_000_000, "total_cities": 6123, "total_land": 900},
            "public_view": True,
            "active_wars": 0,
            "active_wars_list": [],
        },
        "Nation lookup",
    )
    for name in ("💰 Treasury", "⚔️ Military", "📦 Commodities"):
        assert "Classified" in _field(embed, name)
    assert "11,919,128,893" not in _field(embed, "💰 Treasury")
    assert "6,123" in _field(embed, "🏙️ Cities")
    assert "900" in _field(embed, "📐 Land")


def test_owner_view_shows_treasury():
    embed = build_nation_embed(
        {"id": 27, "username": "Testland", "gold": 1_000_000, "military": {"soldiers": 5}},
        "Your nation",
    )
    assert "1,000,000" in _field(embed, "💰 Treasury")
    assert "Classified" not in _field(embed, "⚔️ Military")
