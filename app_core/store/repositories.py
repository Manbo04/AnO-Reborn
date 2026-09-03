"""Raw SQL access for the premium-currency store (Gems + cosmetics)."""

# One equip slot (a nullable FK column on `stats`) per cosmetic_type.
COSMETIC_TYPE_TO_EQUIP_COLUMN = {
    "background": "equipped_background_cosmetic_id",
    "name_color": "equipped_name_color_cosmetic_id",
    "badge": "equipped_badge_cosmetic_id",
    "title": "equipped_title_cosmetic_id",
    "country_border": "equipped_country_border_cosmetic_id",
}


def lock_user(db, user_id):
    """Session-scoped advisory lock, same idiom as app_core/market/repositories.py::lock_users."""
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))


def get_gem_package(db, gem_package_id):
    db.execute(
        """
        SELECT id, name, gems_granted, price_cents, currency
        FROM gem_packages
        WHERE id = %s AND is_active = TRUE
        """,
        (gem_package_id,),
    )
    return db.fetchone()


def get_active_cosmetics(db, cosmetic_type):
    db.execute(
        """
        SELECT id, slug, name, price_gems, css_class, value, preview_image_url
        FROM cosmetics
        WHERE is_active = TRUE AND cosmetic_type = %s
        ORDER BY sort_order, price_gems
        """,
        (cosmetic_type,),
    )
    return db.fetchall()


def get_cosmetic(db, cosmetic_id):
    db.execute(
        """
        SELECT id, slug, name, price_gems, css_class, cosmetic_type, is_active
        FROM cosmetics
        WHERE id = %s
        """,
        (cosmetic_id,),
    )
    return db.fetchone()


def get_user_gems(db, user_id):
    db.execute("SELECT gems FROM stats WHERE id=%s", (user_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else None


def get_user_gems_for_update(db, user_id):
    db.execute("SELECT gems FROM stats WHERE id=%s FOR UPDATE", (user_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else None


def decrement_gems(db, user_id, amount):
    db.execute(
        "UPDATE stats SET gems = gems - %s WHERE id = %s AND gems >= %s RETURNING gems",
        (amount, user_id, amount),
    )
    row = db.fetchone()
    return row is not None


def increment_gems(db, user_id, amount):
    db.execute(
        "UPDATE stats SET gems = gems + %s WHERE id = %s RETURNING gems",
        (amount, user_id),
    )
    return db.fetchone() is not None


def get_user_owned_cosmetic_ids(db, user_id):
    db.execute(
        "SELECT cosmetic_id FROM user_cosmetics WHERE user_id = %s",
        (user_id,),
    )
    return {row[0] for row in db.fetchall()}


def user_owns_cosmetic(db, user_id, cosmetic_id):
    db.execute(
        "SELECT 1 FROM user_cosmetics WHERE user_id = %s AND cosmetic_id = %s",
        (user_id, cosmetic_id),
    )
    return db.fetchone() is not None


def get_owned_cosmetic(db, user_id, cosmetic_id):
    """Returns the cosmetic's `cosmetic_type` if the user owns it, else None.

    Combines the ownership check with the "which equip column to write"
    lookup the equip route needs, in one query.
    """
    db.execute(
        """
        SELECT c.cosmetic_type
        FROM user_cosmetics uc
        JOIN cosmetics c ON c.id = uc.cosmetic_id
        WHERE uc.user_id = %s AND uc.cosmetic_id = %s
        """,
        (user_id, cosmetic_id),
    )
    row = db.fetchone()
    return row[0] if row else None


def grant_cosmetic_ownership(db, user_id, cosmetic_id, gems_spent):
    db.execute(
        """
        INSERT INTO user_cosmetics (user_id, cosmetic_id, gems_spent)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, cosmetic_id) DO NOTHING
        RETURNING id
        """,
        (user_id, cosmetic_id, gems_spent),
    )
    return db.fetchone() is not None


def get_equipped_cosmetic(db, user_id):
    """Returns the css_class of the user's equipped background cosmetic, or None."""
    db.execute(
        """
        SELECT c.css_class
        FROM stats s
        JOIN cosmetics c ON c.id = s.equipped_background_cosmetic_id
        WHERE s.id = %s AND c.is_active = TRUE
        """,
        (user_id,),
    )
    row = db.fetchone()
    return row[0] if row else None


def set_equipped_cosmetic(db, user_id, cosmetic_id, cosmetic_type):
    """cosmetic_id may be None to unequip that slot.

    cosmetic_type selects which equip-slot column on `stats` to write
    (see COSMETIC_TYPE_TO_EQUIP_COLUMN) -- each type has its own slot, so
    e.g. equipping a badge never touches the equipped background.
    """
    column = COSMETIC_TYPE_TO_EQUIP_COLUMN[cosmetic_type]
    db.execute(
        f"UPDATE stats SET {column} = %s WHERE id = %s",  # noqa: S608 -- column is from the fixed whitelist above, never user input
        (cosmetic_id, user_id),
    )


def get_equipped_cosmetic_ids(db, user_id):
    """Returns {cosmetic_type: equipped_cosmetic_id_or_None} for all 5 slots.

    Used by the store page to compute each card's `equipped` state by ID
    (not by css_class, which two catalog items could in principle share).
    """
    db.execute(
        """
        SELECT equipped_background_cosmetic_id, equipped_name_color_cosmetic_id,
               equipped_badge_cosmetic_id, equipped_title_cosmetic_id,
               equipped_country_border_cosmetic_id
        FROM stats WHERE id = %s
        """,
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return {t: None for t in COSMETIC_TYPE_TO_EQUIP_COLUMN}
    return {
        "background": row[0],
        "name_color": row[1],
        "badge": row[2],
        "title": row[3],
        "country_border": row[4],
    }


def get_equipped_flair(db, user_ids):
    """Batch lookup of equipped name_color/badge/title for several users.

    Returns {user_id: {"name_color":..., "badge_icon":..., "badge_name":...,
    "title":...}}. Values are None where nothing is equipped or the
    equipped item was deactivated. Chat surfaces inline this same 3-join
    directly into their own message queries instead of calling this (avoids
    an N+1 per page load) -- this is for single/batch call sites like the
    Country page.
    """
    ids = list(user_ids)
    if not ids:
        return {}
    db.execute(
        """
        SELECT s.id,
               nc.value AS name_color,
               b.value AS badge_icon, b.name AS badge_name,
               t.name AS title
        FROM stats s
        LEFT JOIN cosmetics nc ON nc.id = s.equipped_name_color_cosmetic_id AND nc.is_active = TRUE
        LEFT JOIN cosmetics b  ON b.id  = s.equipped_badge_cosmetic_id      AND b.is_active = TRUE
        LEFT JOIN cosmetics t  ON t.id  = s.equipped_title_cosmetic_id      AND t.is_active = TRUE
        WHERE s.id = ANY(%s)
        """,
        (ids,),
    )
    return {
        r[0]: {"name_color": r[1], "badge_icon": r[2], "badge_name": r[3], "title": r[4]}
        for r in db.fetchall()
    }


def get_equipped_country_border_css_class(db, user_id):
    """Returns the css_class of the user's equipped country-border cosmetic, or None."""
    db.execute(
        """
        SELECT c.css_class
        FROM stats s
        JOIN cosmetics c ON c.id = s.equipped_country_border_cosmetic_id
        WHERE s.id = %s AND c.is_active = TRUE
        """,
        (user_id,),
    )
    row = db.fetchone()
    return row[0] if row else None


def insert_pending_gem_purchase(
    db, user_id, gem_package_id, checkout_session_id, amount_cents, currency, gems_granted
):
    db.execute(
        """
        INSERT INTO gem_purchases
            (user_id, gem_package_id, stripe_checkout_session_id, amount_cents, currency, gems_granted, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        RETURNING id
        """,
        (user_id, gem_package_id, checkout_session_id, amount_cents, currency, gems_granted),
    )
    return db.fetchone()[0]


def get_gem_purchase_by_session_id(db, checkout_session_id):
    db.execute(
        """
        SELECT id, user_id, gems_granted, status
        FROM gem_purchases
        WHERE stripe_checkout_session_id = %s
        """,
        (checkout_session_id,),
    )
    return db.fetchone()


def mark_gem_purchase_credited(db, checkout_session_id, payment_intent_id):
    """Idempotency guard: only transitions rows still in pending/paid state.

    A duplicate webhook delivery for an already-credited purchase updates
    zero rows here, so the caller must treat "no row returned" as a safe
    no-op rather than an error.
    """
    db.execute(
        """
        UPDATE gem_purchases
        SET status = 'credited', stripe_payment_intent_id = %s,
            credited_at = now(), updated_at = now()
        WHERE stripe_checkout_session_id = %s AND status IN ('pending', 'paid')
        RETURNING id, user_id, gems_granted
        """,
        (payment_intent_id, checkout_session_id),
    )
    return db.fetchone()


def mark_gem_purchase_refunded(db, payment_intent_id):
    db.execute(
        """
        UPDATE gem_purchases
        SET status = 'refunded', refunded_at = now(), updated_at = now()
        WHERE stripe_payment_intent_id = %s AND status = 'credited'
        RETURNING id, user_id, gems_granted
        """,
        (payment_intent_id,),
    )
    return db.fetchone()
