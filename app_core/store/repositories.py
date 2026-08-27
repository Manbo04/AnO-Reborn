"""Raw SQL access for the premium-currency store (Gems + cosmetics)."""


def lock_user(db, user_id):
    """Session-scoped advisory lock, same idiom as app_core/market/repositories.py::lock_users."""
    db.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))


def get_active_gem_packages(db):
    db.execute(
        """
        SELECT id, name, gems_granted, price_cents, currency
        FROM gem_packages
        WHERE is_active = TRUE
        ORDER BY sort_order, price_cents
        """
    )
    return db.fetchall()


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


def get_active_cosmetics(db):
    db.execute(
        """
        SELECT id, slug, name, price_gems, css_class, preview_image_url
        FROM cosmetics
        WHERE is_active = TRUE AND cosmetic_type = 'background'
        ORDER BY sort_order, price_gems
        """
    )
    return db.fetchall()


def get_cosmetic(db, cosmetic_id):
    db.execute(
        """
        SELECT id, slug, name, price_gems, css_class, is_active
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


def set_equipped_cosmetic(db, user_id, cosmetic_id):
    """cosmetic_id may be None to unequip (revert to the default theme background)."""
    db.execute(
        "UPDATE stats SET equipped_background_cosmetic_id = %s WHERE id = %s",
        (cosmetic_id, user_id),
    )


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
