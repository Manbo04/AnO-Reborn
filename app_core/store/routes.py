import logging
import os

from flask import Blueprint, request, render_template, session, redirect, url_for

from helpers import login_required, error, is_theme_v2_enabled
from extensions import limiter
from database import get_request_cursor, invalidate_user_cache, invalidate_view_cache, rollback_db_cursor, cache_response
import game_ui

from .repositories import (
    COSMETIC_TYPE_TO_EQUIP_COLUMN,
    get_active_gem_packages,
    get_active_cosmetics,
    get_user_gems,
    get_user_owned_cosmetic_ids,
    get_equipped_cosmetic_ids,
    get_owned_cosmetic,
    set_equipped_cosmetic,
    get_gem_purchase_by_session_id,
)
from .services import StoreError, purchase_cosmetic, start_gem_purchase, handle_checkout_completed, handle_charge_refunded

store_bp = Blueprint("store_bp", __name__)
logger = logging.getLogger(__name__)

# Anchor each cosmetic_type's Store section scrolls to after buy/equip/
# unequip, so a successful purchase lands back where the player clicked
# instead of the top of the page (player-reported 2026-09-03).
ANCHOR_FOR_TYPE = {
    "background": "cosmetics",
    "name_color": "name-colors",
    "badge": "badges",
    "title": "titles",
    "country_border": "country-borders",
}


def _store_accessible():
    """FEATURE_STORE gates the store for everyone once real Stripe keys and
    the reviewed catalog are ready. Until then, staff can still preview the
    real, live page (not a local demo) without exposing it to players."""
    if game_ui.FEATURE_STORE:
        return True
    from app_core.admin.services import SUPER_ADMIN_USER_IDS

    return session.get("user_id") in SUPER_ADMIN_USER_IDS


@store_bp.route("/store", methods=["GET"])
@login_required
@cache_response(ttl_seconds=30)
def store():
    if not _store_accessible():
        return error(404, "Not found")

    with get_request_cursor(read_only=True) as db:
        user_id = session["user_id"]

        gems = get_user_gems(db, user_id) or 0
        owned_ids = get_user_owned_cosmetic_ids(db, user_id)
        equipped_ids = get_equipped_cosmetic_ids(db, user_id)

        gem_packages = get_active_gem_packages(db)

        def _build_view(cosmetic_type):
            view = []
            for cosmetic_id, slug, name, price_gems, css_class, value, preview_image_url in get_active_cosmetics(
                db, cosmetic_type
            ):
                view.append(
                    {
                        "id": cosmetic_id,
                        "slug": slug,
                        "name": name,
                        "price_gems": price_gems,
                        "css_class": css_class,
                        "value": value,
                        "preview_image_url": preview_image_url,
                        "cosmetic_type": cosmetic_type,
                        "owned": cosmetic_id in owned_ids,
                        "equipped": cosmetic_id == equipped_ids.get(cosmetic_type),
                    }
                )
            return view

        template = "store_v2.html" if is_theme_v2_enabled("store") else "store.html"
        return render_template(
            template,
            gems=gems,
            gem_packages=gem_packages,
            cosmetics=_build_view("background"),
            name_color_cosmetics=_build_view("name_color"),
            badge_cosmetics=_build_view("badge"),
            title_cosmetics=_build_view("title"),
            country_border_cosmetics=_build_view("country_border"),
        )


@store_bp.route("/store/gems/checkout/<int:gem_package_id>", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def gems_checkout(gem_package_id):
    if not _store_accessible():
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
    if not _store_accessible():
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
    if not _store_accessible():
        return error(404, "Not found")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        try:
            result = purchase_cosmetic(db, user_id, cosmetic_id)
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

    # Buying happens well below the fold; a plain redirect to the top of
    # /store made a successful purchase look like it did nothing
    # (player-reported 2026-09-03). Land back on the section it came from.
    anchor = ANCHOR_FOR_TYPE.get(result["cosmetic_type"], "cosmetics")
    return redirect(url_for("store_bp.store") + f"#{anchor}")


@store_bp.route("/store/cosmetics/equip/<int:cosmetic_id>", methods=["POST"])
@login_required
def equip_cosmetic(cosmetic_id):
    if not _store_accessible():
        return error(404, "Not found")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        cosmetic_type = get_owned_cosmetic(db, user_id, cosmetic_id)
        if not cosmetic_type:
            return error(400, "You don't own this cosmetic.")
        set_equipped_cosmetic(db, user_id, cosmetic_id, cosmetic_type)

        invalidate_user_cache(user_id)
        invalidate_view_cache("store", user_id=user_id)

    return redirect(url_for("store_bp.store") + f"#{ANCHOR_FOR_TYPE.get(cosmetic_type, 'cosmetics')}")


@store_bp.route("/store/cosmetics/unequip/<cosmetic_type>", methods=["POST"])
@login_required
def unequip_cosmetic(cosmetic_type):
    if not _store_accessible():
        return error(404, "Not found")

    if cosmetic_type not in COSMETIC_TYPE_TO_EQUIP_COLUMN:
        return error(400, "Unknown cosmetic type.")

    with get_request_cursor() as db:
        user_id = session["user_id"]
        set_equipped_cosmetic(db, user_id, None, cosmetic_type)

        invalidate_user_cache(user_id)
        invalidate_view_cache("store", user_id=user_id)

    return redirect(url_for("store_bp.store") + f"#{ANCHOR_FOR_TYPE.get(cosmetic_type, 'cosmetics')}")
