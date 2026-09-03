"""Raw SQL access for the Patreon monthly Gems bonus."""


def get_active_tiers(db):
    db.execute(
        "SELECT title, gems_per_month FROM patreon_tiers WHERE is_active = TRUE ORDER BY gems_per_month"
    )
    return db.fetchall()


def get_user_id_by_discord_id(db, discord_id):
    db.execute("SELECT id FROM users WHERE discord_id = %s", (discord_id,))
    row = db.fetchone()
    return row[0] if row else None


def grant_monthly_gems(db, user_id, patreon_member_id, tier_title, period, gems):
    """Idempotently credit `gems` to `user_id` for `period` ('YYYY-MM').

    Returns True if this call actually credited Gems, False if a grant for
    this user/period already exists (safe to call repeatedly / retry --
    the UNIQUE(user_id, period) constraint on patreon_gem_grants is the
    idempotency boundary, same idiom as gem_purchases in app_core/store).
    """
    db.execute(
        """
        INSERT INTO patreon_gem_grants
            (user_id, patreon_member_id, tier_title, period, gems_granted)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, period) DO NOTHING
        RETURNING id
        """,
        (user_id, patreon_member_id, tier_title, period, gems),
    )
    if db.fetchone() is None:
        return False
    db.execute(
        "UPDATE stats SET gems = gems + %s WHERE id = %s",
        (gems, user_id),
    )
    return True
