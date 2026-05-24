"""Province route includes a fallback when demographics columns are absent."""


def test_province_sql_includes_demographics_fallback_branch():
    import province as prov_mod

    source = open(prov_mod.__file__).read()
    assert "provinces_has_demographics()" in source
    assert "0 AS pop_children, 0 AS pop_working, 0 AS pop_elderly" in source
