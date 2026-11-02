"""/provinces sort: whitelisted server-side ordering + the control renders and carries through the pager."""
import pytest

pytestmark = pytest.mark.no_server


def test_sort_keys_are_a_fixed_whitelist():
    from repositories.province_repository import ProvinceRepository as R

    assert set(R.SORT_COLUMNS) == {"number", "name", "population", "land", "cities", "happiness", "productivity"}
    for col in R.SORT_COLUMNS.values():
        assert all(ch.isalnum() or ch in "_() " for ch in col), col  # no user text ever reaches SQL


def test_template_renders_sort_control_and_pager_keeps_sort():
    import app as application_module

    app = application_module.app
    rows = [(5, 1_000_000 + i, f"P{i}", i, 20, 50, 100, 0, 1, 1, 1) for i in range(1, 4)]
    ctx = dict(provinces=rows, provinces_with_images=set(), slots_used={}, province_buildings={}, building_categories={},
               growth_rates={}, current_page=1, total_pages=3, total_count=90, total_population=3_000_000,
               view_mode="cards", search_query="", search_results=[], sort="population", sort_dir="desc")
    with app.test_request_context("/provinces"):
        from flask import session
        session["user_id"] = 16
        tpl = app.jinja_env.get_template("provinces_v2.html")
        html = "".join(tpl.blocks["body"](tpl.new_context(ctx)))
    assert 'name="sort"' in html and '<option value="population" selected>' in html
    assert 'name="dir"' in html and '<option value="desc" selected>' in html
    assert "sort=population&dir=desc" in html
