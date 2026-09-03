"""Provinces list page: 'Est. tax revenue' must use demographic-weighted
population like calc_ti() (app_core/game_ticks/taxes.py), not raw population.

Regression: counting children (who pay 0% tax) and elderly (45%) at the
full 100% working-age rate inflated the estimate above what generate_province
revenue could ever actually produce -- reported live as tax-revenue estimates
exceeding the nation's actual hourly monetary gross (Discord, 2026-09-03).
"""
import re
from pathlib import Path

import pytest

import variables

pytestmark = pytest.mark.no_server


def _render_card_chunk(provinces, provinces_with_images=None):
    from jinja2 import Environment

    html = Path("templates/provinces_v2.html").read_text(encoding="utf-8")
    m = re.search(
        r"(\{% for province in provinces %\}.*?)<a href=\"/province/",
        html,
        re.DOTALL,
    )
    assert m, "Could not locate the province-card for-loop in provinces_v2.html"
    chunk = m.group(1) + "{{ est_daily_tax }}|{{ taxable_population }}{% endfor %}"

    env = Environment()
    tpl = env.from_string(chunk)
    return tpl.render(
        provinces=provinces,
        provinces_with_images=provinces_with_images or set(),
    )


def _province_row(population, pid, land, pop_children=0, pop_working=0, pop_elderly=0):
    # Matches ProvinceService row order: citycount, population, name, id,
    # land, happiness, productivity, energy, pop_children, pop_working, pop_elderly
    return (10, population, "Test Province", pid, land, 100, 100, 100,
            pop_children, pop_working, pop_elderly)


def test_est_tax_uses_demographic_weighted_population_not_raw():
    # 1M population entirely made of children: real tax income should be
    # ~0 (DEMO_TAX_MULTIPLIER["pop_children"] == 0.0), not the same as if
    # they were all working adults.
    row = _province_row(population=1_000_000, pid=1, land=1, pop_children=1_000_000)
    out = _render_card_chunk([row])
    est_daily_tax, taxable_population = out.split("|")
    assert float(taxable_population) == 0.0
    assert float(est_daily_tax) == 0.0


def test_est_tax_matches_calc_ti_weighting_for_mixed_demographics():
    pop_working, pop_children, pop_elderly = 500_000, 300_000, 200_000
    row = _province_row(
        population=pop_working + pop_children + pop_elderly,
        pid=2,
        land=1,
        pop_children=pop_children,
        pop_working=pop_working,
        pop_elderly=pop_elderly,
    )
    out = _render_card_chunk([row])
    est_daily_tax, taxable_population = out.split("|")

    expected_taxable = (
        pop_working * variables.DEMO_TAX_MULTIPLIER["pop_working"]
        + pop_children * variables.DEMO_TAX_MULTIPLIER["pop_children"]
        + pop_elderly * variables.DEMO_TAX_MULTIPLIER["pop_elderly"]
    )
    assert float(taxable_population) == expected_taxable

    land_multiplier = min((1 - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER, 1)
    expected_daily = (
        variables.DEFAULT_TAX_INCOME * (1 + land_multiplier) * expected_taxable * 24
    )
    assert float(est_daily_tax) == expected_daily


def test_est_tax_falls_back_to_raw_population_without_demographic_data():
    # No demographics available (all three columns 0/absent) -- must not
    # collapse the estimate to 0; fall back to the pre-fix raw-population math.
    row = _province_row(population=1_000_000, pid=3, land=1)
    out = _render_card_chunk([row])
    est_daily_tax, taxable_population = out.split("|")
    assert float(taxable_population) == 1_000_000

    land_multiplier = min((1 - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER, 1)
    expected_daily = (
        variables.DEFAULT_TAX_INCOME * (1 + land_multiplier) * 1_000_000 * 24
    )
    assert float(est_daily_tax) == expected_daily
