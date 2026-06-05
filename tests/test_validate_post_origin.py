"""Origin validation helper (no DB)."""


from helpers import validate_post_origin


def test_validate_post_origin_skipped_outside_prod(client, monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    with client.application.test_request_context(
        "/build_structure",
        method="POST",
        headers={"Origin": "https://evil.example"},
    ):
        assert validate_post_origin() is None


def test_validate_post_origin_blocks_foreign_host_in_prod(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "PROD")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with client.application.test_request_context(
        "/build_structure",
        method="POST",
        base_url="https://affairsandorder.com",
        headers={"Origin": "https://evil.example"},
    ):
        resp = validate_post_origin()
        assert resp is not None
        assert resp[1] == 403
