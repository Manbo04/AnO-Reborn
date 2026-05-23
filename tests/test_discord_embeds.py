"""Discord nation embed formatting."""
from discord_bot.embeds import _format_military, _format_resources, build_nation_embed


def test_format_military_includes_units():
    text = _format_military(
        {"manpower": 50000, "soldiers": 1000, "tanks": 50, "default_defense": "balanced"}
    )
    assert "Manpower" in text
    assert "Soldiers" in text
    assert "Tanks" in text
    assert "Defense mode" in text


def test_format_resources_sorted():
    text = _format_resources({"steel": 100, "gold_commodity": 1, "oil": 5000})
    assert "Oil" in text or "oil" in text.lower()


def test_build_nation_embed_has_military_and_resources_fields():
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
    assert "Military" in names
    assert "Resources (top holdings)" in names
    assert "Population" in names
