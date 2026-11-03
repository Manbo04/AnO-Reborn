"""Building descriptions are generated from the values the tick really uses.

Discord "I Am Confusion" (Andy, 2026-10-27): the Farms panel said "cost 2,400
... +150 rations" (hand-written, upgrade-adjusted), "cost $1.50M, 30 t lumber"
(build price) and "upkeep $3,000/h ... makes 100 rations" (base) -- three
"costs" for one building, and no hint which education the workers need.
"""

import re

import pytest

import variables
from app_core.economy.building_costs import (
    EDUCATION_LABELS,
    building_description,
    education_requirement,
    format_money,
    format_weight,
    get_build_cost,
)

pytestmark = pytest.mark.no_server

BUILDINGS = sorted(variables.NEW_INFRA)


def _amount(res, value):
    return format_weight(value) if res in variables.RESOURCES else f"{value:,}"


@pytest.mark.parametrize("name", BUILDINGS)
def test_description_matches_tick_config(name):
    infra = variables.NEW_INFRA[name]  # the table revenue.py reads
    text = building_description(name)
    assert text, name

    # Build price (province purchase) and upkeep (hourly tick).
    cost = get_build_cost(name)
    assert f"Build cost ${format_money(cost['gold'])}" in text
    for res, amt in cost["resources"].items():
        assert f"{format_weight(amt)} {res.replace('_', ' ')}" in text
    if infra.get("money"):
        assert f"Upkeep ${infra['money']:,}/h" in text

    # Output / inputs.
    for res, amt in (infra.get("plus") or {}).items():
        assert f"{_amount(res, amt)} {res.replace('_', ' ')}" in text
    for res, amt in (infra.get("minus") or {}).items():
        assert f"{_amount(res, amt)} {res.replace('_', ' ')}" in text

    # Side effects, pollution included.
    for stat, val in (infra.get("eff") or {}).items():
        assert re.search(rf"\+{val:g}%? {stat.replace('_', ' ')}", text), (name, stat)

    # Workers and the education they need (jobs matrix used by the workforce tick).
    matrix = variables.BUILDING_EMPLOYMENT_MATRICES.get(name) or {}
    if matrix.get("worker_count"):
        assert f"Employs {int(matrix['worker_count']):,} workers" in text
        edu = education_requirement(name)
        assert edu and f"({edu})" in text
        for key, share in matrix["education"].items():
            if share:
                assert EDUCATION_LABELS[key] in text


def test_every_matrix_education_key_has_a_label():
    keys = {
        k
        for m in variables.BUILDING_EMPLOYMENT_MATRICES.values()
        for k in (m.get("education") or {})
    }
    assert keys <= set(EDUCATION_LABELS)


def test_andys_farms_panel_is_unambiguous():
    text = building_description("farms")
    assert "Build cost $1.50M + 30 t lumber" in text
    assert "Upkeep $3,000/h" in text
    assert "Employs 50,000 workers (No schooling)" in text
    assert "Base output 100 kg rations/h" in text
    assert "+1% pollution" in text

    with_upgrades = building_description(
        "farms", {"cheapermaterials": True, "advancedmachinery": True}
    )
    # The 2,400 Andy saw is the Cheaper Materials price -- now labelled as such.
    assert "Upkeep $3,000/h ($2,400/h with Cheaper Materials)" in with_upgrades
    assert "+50% from your national project" in with_upgrades


def test_university_education_mix_is_shown():
    assert "(80% High school, 20% College)" in building_description("universities")


def test_legacy_infra_display_table_matches_engine_table():
    """variables.INFRA (display copy) must never drift from NEW_INFRA again."""
    for name, engine in variables.NEW_INFRA.items():
        assert variables.INFRA.get(f"{name}_money") == engine.get("money"), name
        assert (variables.INFRA.get(f"{name}_plus") or {}) == (engine.get("plus") or {}), name


def test_tick_reads_the_tables_the_descriptions_use():
    src = open("app_core/game_ticks/revenue.py", encoding="utf-8").read()
    assert "infra = variables.NEW_INFRA" in src
    assert 'operating_costs = infra[unit]["money"] * unit_amount' in src
    # Jobs / required education: the workforce calculation reads the same matrix.
    for path in ("countries.py", "services/country_service.py"):
        assert "variables.BUILDING_EMPLOYMENT_MATRICES" in open(path, encoding="utf-8").read()


@pytest.mark.parametrize("path", ["templates/province_v2.html", "templates/province.html"])
def test_province_templates_have_no_hand_written_cost_sentences(path):
    src = open(path, encoding="utf-8").read()
    assert not re.search(r"(?:cost|produce)[^<\n]*\{\{[^}\n]*\binfra\[", src), path
    assert "| prores }}</ul><ul class=\"building-info\">" not in src
    # every building card with a description uses the generated one
    assert src.count("| building_info(upgrades) }}") >= 50


def test_jinja_filter_renders_generated_description():
    from app import app

    flt = app.jinja_env.filters["building_info"]
    assert "No schooling" in flt("farms")
    assert "Fulfillment Centers" not in flt("Fulfillment Centers") and flt("Fulfillment Centers")
