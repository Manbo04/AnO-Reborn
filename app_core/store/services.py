"""Business logic for the premium-currency store (Gems + cosmetics)."""
import logging
import os

from .repositories import (
    lock_user,
    get_cosmetic,
    get_gem_package,
    get_user_gems_for_update,
    decrement_gems,
    increment_gems,
    user_owns_cosmetic,
    grant_cosmetic_ownership,
    insert_pending_gem_purchase,
    mark_gem_purchase_credited,
    mark_gem_purchase_refunded,
)

logger = logging.getLogger(__name__)


class StoreError(Exception):
    """Business-rule failure in the store (bad request, not a server error)."""


def purchase_cosmetic(db, user_id, cosmetic_id):
    """Buy `cosmetic_id` with Gems. Uses caller's db cursor (no commit).

    Mirrors app_core/economy/building_purchase.py::purchase_building's
    lock -> validate -> conditional-debit -> grant shape.
    """
    lock_user(db, user_id)

    cosmetic = get_cosmetic(db, cosmetic_id)
    if not cosmetic:
        raise StoreError("No such cosmetic exists.")
    _id, slug, name, price_gems, css_class, cosmetic_type, is_active = cosmetic
    if not is_active:
        raise StoreError("This cosmetic is no longer available.")

    if user_owns_cosmetic(db, user_id, cosmetic_id):
        raise StoreError("You already own this cosmetic.")

    gems_before = get_user_gems_for_update(db, user_id)
    if gems_before is None:
        raise StoreError("Nation data could not be found.")

    if price_gems > gems_before:
        shortfall = price_gems - gems_before
        raise StoreError(
            f"Not enough Gems: need {price_gems:,}, you have {gems_before:,} "
            f"(missing {shortfall:,})."
        )

    if not decrement_gems(db, user_id, price_gems):
        # Someone else spent this user's Gems in a concurrent request.
        raise StoreError("Not enough Gems.")

    # ON CONFLICT DO NOTHING guards a race where the same cosmetic is bought
    # twice concurrently; the Gems debit above already went through in that
    # case, which is an acceptable, rare edge (matches purchase_building's
    # posture of trusting the row lock rather than adding a second guard).
    grant_cosmetic_ownership(db, user_id, cosmetic_id, price_gems)

    return {
        "cosmetic_id": cosmetic_id,
        "cosmetic_type": cosmetic_type,
        "name": name,
        "gems_spent": price_gems,
        "gems_before": gems_before,
        "gems_after": gems_before - price_gems,
    }


def _stripe():
    import stripe

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    return stripe


def create_checkout_session(user_id, gem_package, success_url, cancel_url):
    """gem_package: (id, name, gems_granted, price_cents, currency) from get_gem_package()."""
    package_id, name, gems_granted, price_cents, currency = gem_package
    stripe = _stripe()
    return stripe.checkout.Session.create(
        mode="payment",
        client_reference_id=str(user_id),
        metadata={"user_id": str(user_id), "gem_package_id": str(package_id)},
        line_items=[
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": price_cents,
                    "product_data": {
                        "name": name,
                        # Required by Stripe Managed Payments (chosen for this
                        # account so Stripe is liable for sales tax/VAT — see
                        # plan). Closest fit for a one-time in-game-currency
                        # purchase on a browser game with no permanent
                        # download. Not a final compliance decision — review
                        # before going live for real money.
                        "tax_code": "txcd_10201001",
                    },
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
    )


def start_gem_purchase(db, user_id, gem_package_id, success_url, cancel_url):
    gem_package = get_gem_package(db, gem_package_id)
    if not gem_package:
        raise StoreError("No such Gem package exists.")
    _id, name, gems_granted, price_cents, currency = gem_package

    session = create_checkout_session(user_id, gem_package, success_url, cancel_url)
    insert_pending_gem_purchase(
        db, user_id, gem_package_id, session.id, price_cents, currency, gems_granted
    )
    return session.url


def handle_checkout_completed(db, checkout_session_id, payment_intent_id):
    """Idempotent: a duplicate delivery for an already-credited session is a no-op."""
    credited = mark_gem_purchase_credited(db, checkout_session_id, payment_intent_id)
    if not credited:
        logger.info(
            "store webhook: checkout session %s already credited or unknown, skipping",
            checkout_session_id,
        )
        return None
    _id, user_id, gems_granted = credited
    increment_gems(db, user_id, gems_granted)
    logger.info("store webhook: credited %s gems to user %s", gems_granted, user_id)
    return user_id, gems_granted


def handle_charge_refunded(db, payment_intent_id):
    """Marks the ledger row refunded. Does NOT claw back Gems/cosmetics —
    that policy is an open decision, not implemented here (see plan)."""
    refunded = mark_gem_purchase_refunded(db, payment_intent_id)
    if not refunded:
        logger.info(
            "store webhook: refund for payment_intent %s has no matching credited purchase",
            payment_intent_id,
        )
        return None
    _id, user_id, gems_granted = refunded
    logger.warning(
        "store webhook: purchase for payment_intent %s (user %s, %s gems) marked refunded; "
        "no automatic clawback is implemented",
        payment_intent_id, user_id, gems_granted,
    )
    return user_id, gems_granted
