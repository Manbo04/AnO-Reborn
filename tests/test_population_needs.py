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
