import logging
import os

from flask import Blueprint, request, render_template, session, redirect, url_for

from helpers import login_required, error
from extensions import limiter
from database import get_request_cursor, invalidate_user_cache, invalidate_view_cache, rollback_db_cursor, cache_response
import game_ui

from .repositories import (
    get_active_gem_packages,
    get_active_cosmetics,
    get_user_gems,
    get_user_owned_cosmetic_ids,
    get_equipped_cosmetic,
    user_owns_cosmetic,
    set_equipped_cosmetic,
    get_gem_purchase_by_session_id,
)
from .services import StoreError, purchase_cosmetic, start_gem_purchase, handle_checkout_completed, handle_charge_refunded

store_bp = Blueprint("store_bp", __name__)
logger = logging.getLogger(__name__)


@store_bp.route("/store", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)
def store():
    if not game_ui.FEATURE_STORE:
        return error(404, "Not found")

    with get_request_cursor(read_only=True) as db:
        user_id = session["user_id"]

        gems = get_user_gems(db, user_id) or 0
        owned_ids = get_user_owned_cosmetic_ids(db, user_id)
        equipped_css_class = get_equipped_cosmetic(db, user_id)

        gem_packages = get_active_gem_packages(db)
        cosmetics = get_active_cosmetics(db)

        cosmetics_view = []
        for cosmetic_id, slug, name, price_gems, css_class, preview_image_url in cosmetics:
            cosmetics_view.append(
                {
                    "id": cosmetic_id,
                    "slug": slug,
                    "name": name,
                    "price_gems": price_gems,
                    "css_class": css_class,
                    "preview_image_url": preview_image_url,
                    "owned": cosmetic_id in owned_ids,
                    "equipped": css_class == equipped_css_class,
                }
            )

        return render_template(
            "store.html",
            gems=gems,
            gem_packages=gem_packages,
            cosmetics=cosmetics_view,
        )


@store_bp.route("/store/gems/checkout/<int:gem_package_id>", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def gems_checkout(gem_package_id):
    if not game_ui.FEATURE_STORE:
        return error(404, "Not found")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        try:
            checkout_url = start_gem_purchase(
                db,
                user_id,
                gem_package_id,
                success_url=url_for("store_bp.store", _external=True),
                cancel_url=url_for("store_bp.store", _external=True),
            )
        except StoreError as e:
            rollback_db_cursor(db)
            return error(400, str(e))
        except Exception:
            rollback_db_cursor(db)
            logger.exception("store: failed to start gem checkout for user %s", user_id)
            return error(502, "Could not start checkout. Please try again.")

        return redirect(checkout_url, code=303)


@store_bp.route("/store/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Stripe-only. No @login_required (no session cookie from Stripe) — the
    signature check below is the entire auth boundary. Kept CSRF-exempt via
    app.py (only this specific view, not the whole blueprint)."""
    if not game_ui.FEATURE_STORE:
        return error(404, "Not found")

    import stripe

    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        logger.warning("store webhook: signature verification failed")
        return error(400, "Invalid signature")

    event_type = event["type"]

    with get_request_cursor() as db:
        try:
            if event_type in ("checkout.session.completed",):
                obj = event["data"]["object"]
                # event["data"]["object"] is a stripe.StripeObject, not a plain
                # dict — it doesn't support .get(), only attribute/bracket access.
                result = handle_checkout_completed(db, obj["id"], getattr(obj, "payment_intent", None))
                if result:
                    invalidate_user_cache(result[0])
            elif event_type in ("charge.refunded", "charge.dispute.created"):
                obj = event["data"]["object"]
                payment_intent_id = getattr(obj, "payment_intent", None)
                if payment_intent_id:
                    result = handle_charge_refunded(db, payment_intent_id)
                    if result:
                        invalidate_user_cache(result[0])
            # Unhandled event types are intentionally ignored (still 200, so
            # Stripe doesn't retry them forever).
        except Exception:
            rollback_db_cursor(db)
            logger.exception("store webhook: failed to process event %s", event_type)
            return error(500, "Webhook processing failed")

    return "", 200


@store_bp.route("/store/cosmetics/buy/<int:cosmetic_id>", methods=["POST"])
@login_required
@limiter.limit("20 per minute")
def buy_cosmetic(cosmetic_id):
    if not game_ui.FEATURE_STORE:
        return error(404, "Not found")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        try:
            purchase_cosmetic(db, user_id, cosmetic_id)
        except StoreError as e:
            rollback_db_cursor(db)
            return error(400, str(e))

        # The equipped background is server-rendered into every page via
        # layout.html, but only the /store view's own cache is invalidated
        # here (matching this codebase's existing pattern of targeted
        # invalidation rather than a global sweep). Other already-cached
        # pages may show the previous background for up to their own
        # cache_response TTL (typically 15-60s) before it self-corrects,
        # the same tolerance this codebase already has for other per-user
        # layout state (e.g. gold balance) on cached pages.
        invalidate_user_cache(user_id)
        invalidate_view_cache("store", user_id=user_id)

    return redirect(url_for("store_bp.store"))


@store_bp.route("/store/cosmetics/equip/<int:cosmetic_id>", methods=["POST"])
@login_required
def equip_cosmetic(cosmetic_id):
    if not game_ui.FEATURE_STORE:
        return error(404, "Not found")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        if not user_owns_cosmetic(db, user_id, cosmetic_id):
            return error(400, "You don't own this cosmetic.")
        set_equipped_cosmetic(db, user_id, cosmetic_id)

        invalidate_user_cache(user_id)
        invalidate_view_cache("store", user_id=user_id)

    return redirect(url_for("store_bp.store"))


@store_bp.route("/store/cosmetics/unequip", methods=["POST"])
@login_required
def unequip_cosmetic():
    if not game_ui.FEATURE_STORE:
        return error(404, "Not found")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        set_equipped_cosmetic(db, user_id, None)

        invalidate_user_cache(user_id)
        invalidate_view_cache("store", user_id=user_id)

    return redirect(url_for("store_bp.store"))
