from database import get_db_cursor


def test_components_show_in_market_stats(client):
    """Insert a components offer and verify it shows up on /statistics"""
    # Use the designated test account (user id 16) per CLAUDE.md
    offer_id = None
    try:
        with get_db_cursor() as db:
            db.execute(
                "INSERT INTO offers (user_id, type, resource, amount, price) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING offer_id",
                (
                    16,
                    "sell",
                    "components",
                    50,
                    123,
                ),
            )
            offer_id = db.fetchone()[0]

        # Ensure we're logged in as the designated test account
        with client.session_transaction() as sess:
            sess["user_id"] = 16

        r = client.get("/statistics")
        assert r.status_code == 200
        body = r.data.decode("utf-8")
        # Ensure the Components row is present and the price appears
        assert "Components:" in body
        assert "123" in body

    finally:
        # Clean up test offer
        if offer_id:
            with get_db_cursor() as db:
                db.execute("DELETE FROM offers WHERE offer_id=%s", (offer_id,))
