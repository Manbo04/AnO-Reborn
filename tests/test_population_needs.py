from app_core.population_needs import build_population_needs, hospitals_needed


def _ds(cap, eff=100, stock=1_000_000):
    return {"rations_stockpile": stock, "distribution_cap": cap,
            "efficiency_percent": eff, "starvation_grace": True}


def test_everything_ok():
    out = build_population_needs(
        1_000_000, 20, _ds(2_000_000), {"homes": 3_000_000, "hospitals": 2,
                                        "hospital_cover_pct": 100})
    assert out["problems"] == 0
    assert all(r["ok"] for r in out["rows"])


def test_distribution_gap_reports_missing_and_buildings_with_efficiency():
    out = build_population_needs(
        100_000_000, 2000, _ds(50_000_000, eff=50), None)
    row = next(r for r in out["rows"] if r["key"] == "distribution")
    assert not row["ok"] and row["missing"] == 50_000_000
    # food bank reaches 250k * 50% = 125k -> 400 of them
    assert "400 food banks" in row["advice"]
    assert out["problems"] == 1


def test_hospitals_needed_matches_flat_cover_rule():
    assert hospitals_needed(0) == 0
    assert hospitals_needed(2_500_000) == 3
    assert hospitals_needed(666_000_001) == 667
    assert hospitals_needed(800_000_000) == 800


def _health(unpowered=0, unstable=0):
    rows = [
        {"name": "Alpha", "powered": unpowered == 0, "stability": "stable"},
        {"name": "Beta", "powered": True, "stability": "unrest" if unstable else "stable"},
    ]
    return {"rows": rows, "unpowered": unpowered, "unstable": unstable}


def test_power_and_stability_rows_flag_problem_provinces():
    out = build_population_needs(1000, 1, None, None, province_health=_health(1, 1))
    power = next(r for r in out["rows"] if r["key"] == "power")
    stab = next(r for r in out["rows"] if r["key"] == "stability")
    assert not power["ok"] and power["missing"] == 1 and "Alpha" in power["advice"]
    assert not stab["ok"] and "Beta" in stab["advice"]
    assert out["problems"] == 2


def test_negative_resource_row_lists_bleeding_resources():
    net = {"steel": -120.0, "oil": 5, "money": -9_999}
    out = build_population_needs(1000, 1, None, None, resource_net=net)
    row = next(r for r in out["rows"] if r["key"] == "resource_net")
    assert not row["ok"] and row["missing"] == 1  # money is gold, not a resource
    assert "steel" in row["advice"] and "oil" not in row["advice"]


def test_new_rows_absent_without_data_and_ok_when_healthy():
    out = build_population_needs(1000, 1, None, None)
    assert not [r for r in out["rows"] if r["key"] in ("power", "stability", "resource_net")]
    out = build_population_needs(
        1000, 1, None, None, province_health=_health(), resource_net={"steel": 3})
    assert out["problems"] == 0
