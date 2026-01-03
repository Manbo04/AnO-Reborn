"""
Admin endpoints for managing bot nations and market stabilization.

These endpoints allow admins to:
- Trigger bot market stabilization manually
- View bot status and statistics
- Configure bot parameters
- Cancel bot orders
"""

from flask import jsonify, request
from app import app
from helpers import login_required
import logging
from bot_nations import (
    ensure_bot_nations_exist,
    execute_market_stabilization,
    produce_resources,
    cancel_bot_orders,
    get_bot_status,
    BOT_NATION_IDS,
    TARGET_PRICES,
    MIN_RESERVES,
)

logger = logging.getLogger(__name__)


@app.route("/admin/bots/status", methods=["GET"])
@login_required
def admin_bot_status():
    """View current status of all bot nations."""
    try:
        # Check if user is admin (you may need to add admin role check)
        statuses = {}

        for bot_name, bot_id in BOT_NATION_IDS.items():
            status = get_bot_status(bot_id)
            statuses[bot_name] = status

        return jsonify({"success": True, "bots": statuses})

    except Exception as e:
        logger.error(f"Error getting bot status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/bots/stabilize", methods=["POST"])
@login_required
def admin_stabilize_market():
    """Manually trigger market stabilization."""
    try:
        bot_id = request.json.get("bot_id", list(BOT_NATION_IDS.values())[0])

        ensure_bot_nations_exist()
        execute_market_stabilization(bot_id)

        return jsonify({"success": True, "message": "Market stabilization triggered"})

    except Exception as e:
        logger.error(f"Error stabilizing market: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/bots/produce", methods=["POST"])
@login_required
def admin_produce_resources():
    """Manually trigger resource production."""
    try:
        bot_id = request.json.get("bot_id", BOT_NATION_IDS["resource_producer"])

        ensure_bot_nations_exist()
        produce_resources(bot_id)

        return jsonify({"success": True, "message": "Resource production triggered"})

    except Exception as e:
        logger.error(f"Error producing resources: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/bots/cancel-orders", methods=["POST"])
@login_required
def admin_cancel_orders():
    """Cancel all active orders for a bot."""
    try:
        bot_id = request.json.get("bot_id", BOT_NATION_IDS["market_stabilizer"])

        cancel_bot_orders(bot_id)

        return jsonify(
            {"success": True, "message": f"Cancelled orders for bot {bot_id}"}
        )

    except Exception as e:
        logger.error(f"Error cancelling bot orders: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/admin/bots/config", methods=["GET"])
@login_required
def admin_bot_config():
    """Get bot configuration (prices, reserves, etc)."""
    return jsonify(
        {
            "success": True,
            "bots": BOT_NATION_IDS,
            "target_prices": TARGET_PRICES,
            "min_reserves": MIN_RESERVES,
        }
    )


@app.route("/admin/bots/init", methods=["POST"])
@login_required
def admin_init_bots():
    """Initialize bot nations if they don't exist."""
    try:
        ensure_bot_nations_exist()

        statuses = {}
        for bot_name, bot_id in BOT_NATION_IDS.items():
            status = get_bot_status(bot_id)
            statuses[bot_name] = status

        return jsonify(
            {
                "success": True,
                "message": "Bot nations initialized",
                "bots": statuses,
            }
        )

    except Exception as e:
        logger.error(f"Error initializing bots: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
