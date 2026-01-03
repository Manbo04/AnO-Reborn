"""
Bot Nations System for Automatic Resource Trading and Market Stabilization

This module provides autonomous trading bots that:
- Monitor market prices for resources
- Buy resources when prices are low (below target)
- Sell resources when prices are high (above target)
- Help stabilize the game economy

Bot nations are special accounts managed by the system, not players.
"""

from datetime import datetime
import logging
from database import get_db_cursor, fetchone_first

logger = logging.getLogger(__name__)

# Bot nation IDs - reserved for bot accounts
BOT_NATION_IDS = {
    "market_stabilizer": 9999,  # Primary market stabilization bot
    "resource_producer": 9998,  # Secondary bot for resource production
}

# Target prices for each resource (in gold per unit)
# Bots will try to keep prices within these ranges
TARGET_PRICES = {
    "rations": {"min": 100, "max": 150, "target": 125},
    "lumber": {"min": 80, "max": 120, "target": 100},
    "steel": {"min": 200, "max": 300, "target": 250},
    "aluminium": {"min": 150, "max": 250, "target": 200},
}

# Minimum reserves each bot should keep
MIN_RESERVES = {
    "rations": 100000,
    "lumber": 100000,
    "steel": 50000,
    "aluminium": 50000,
}


def ensure_bot_nations_exist():
    """Create bot nation accounts if they don't exist."""
    try:
        with get_db_cursor() as db:
            for bot_name, bot_id in BOT_NATION_IDS.items():
                # Check if bot nation exists
                db.execute("SELECT id FROM users WHERE id = %s", (bot_id,))
                if db.fetchone():
                    logger.debug(f"Bot nation {bot_name} already exists")
                    continue

                # Create bot nation user
                db.execute(
                    """
                    INSERT INTO users (id, username, email, date, hash, auth_type)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        bot_id,
                        f"BOT_{bot_name.upper()}",
                        f"bot.{bot_name}@ano-system.local",
                        datetime.now().strftime("%Y-%m-%d"),
                        "bot_account",  # Special hash for bot accounts
                        "bot",  # Special auth type
                    ),
                )

                # Create stats entry for bot
                db.execute(
                    """
                    INSERT INTO stats (id, gold, location)
                    VALUES (%s, %s, %s)
                    """,
                    (bot_id, 10000000, "Bot Nation"),  # 10M starting gold
                )

                # Create resources entry for bot with large reserves
                db.execute(
                    """
                    INSERT INTO resources
                    (id, rations, lumber, steel, aluminium)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        bot_id,
                        1000000,  # 1M of each resource
                        1000000,
                        500000,
                        500000,
                    ),
                )

                logger.info(f"Created bot nation: {bot_name} (ID: {bot_id})")

    except Exception as e:
        logger.error(f"Error ensuring bot nations exist: {e}")
        raise


def get_market_prices():
    """
    Get current average prices for each resource from the market.

    Returns:
        dict: Resource -> average price mapping
    """
    prices = {}
    try:
        with get_db_cursor() as db:
            for resource in TARGET_PRICES.keys():
                db.execute(
                    """
                    SELECT AVG(price) FROM offers
                    WHERE resource = %s AND type = %s
                    """,
                    (resource, "sell"),
                )
                result = fetchone_first(db, 0)
                prices[resource] = (
                    int(result) if result else TARGET_PRICES[resource]["target"]
                )

    except Exception as e:
        logger.error(f"Error getting market prices: {e}")

    return prices


def get_bot_resources(bot_id):
    """Get current resource amounts for a bot nation."""
    try:
        with get_db_cursor() as db:
            db.execute(
                """
                SELECT rations, lumber, steel, aluminium
                FROM resources WHERE id = %s
                """,
                (bot_id,),
            )
            result = db.fetchone()
            if result:
                return {
                    "rations": result[0],
                    "lumber": result[1],
                    "steel": result[2],
                    "aluminium": result[3],
                }
    except Exception as e:
        logger.error(f"Error getting bot resources: {e}")

    return {r: 0 for r in TARGET_PRICES.keys()}


def get_bot_gold(bot_id):
    """Get current gold for a bot nation."""
    try:
        with get_db_cursor() as db:
            db.execute("SELECT gold FROM stats WHERE id = %s", (bot_id,))
            result = fetchone_first(db, 0)
            return int(result) if result else 0
    except Exception as e:
        logger.error(f"Error getting bot gold: {e}")
        return 0


def place_buy_order(bot_id, resource, amount, price_per_unit):
    """
    Place a buy order on the market.

    Args:
        bot_id: ID of the bot nation
        resource: Resource to buy
        amount: Amount to buy
        price_per_unit: Price per unit
    """
    try:
        with get_db_cursor() as db:
            db.execute(
                """
                INSERT INTO offers (type, user_id, resource, amount, price)
                VALUES ('buy', %s, %s, %s, %s)
                """,
                (bot_id, resource, amount, price_per_unit),
            )
            logger.info(
                f"Bot {bot_id} placed buy order: {amount} {resource} "
                f"@ {price_per_unit}g each"
            )
    except Exception as e:
        logger.error(f"Error placing buy order: {e}")


def place_sell_order(bot_id, resource, amount, price_per_unit):
    """
    Place a sell order on the market.

    Args:
        bot_id: ID of the bot nation
        resource: Resource to sell
        amount: Amount to sell
        price_per_unit: Price per unit
    """
    try:
        with get_db_cursor() as db:
            db.execute(
                """
                INSERT INTO offers (type, user_id, resource, amount, price)
                VALUES ('sell', %s, %s, %s, %s)
                """,
                (bot_id, resource, amount, price_per_unit),
            )
            logger.info(
                f"Bot {bot_id} placed sell order: {amount} {resource} "
                f"@ {price_per_unit}g each"
            )
    except Exception as e:
        logger.error(f"Error placing sell order: {e}")


def execute_market_stabilization(bot_id=None):
    """
    Execute market stabilization logic for a bot nation.

    The bot will:
    1. Check current market prices
    2. Place buy orders when prices are below target range
    3. Place sell orders when prices are above target range
    4. Always maintain orders at target prices to guide market

    Args:
        bot_id: ID of bot to execute (defaults to primary market stabilizer)
    """
    if bot_id is None:
        bot_id = BOT_NATION_IDS["market_stabilizer"]

    try:
        prices = get_market_prices()
        resources = get_bot_resources(bot_id)
        gold = get_bot_gold(bot_id)

        logger.info(f"Market Stabilization for Bot {bot_id}")
        logger.info(f"Current prices: {prices}")
        logger.info(f"Bot resources: {resources}")
        logger.info(f"Bot gold: {gold}")

        # Clear old orders first to prevent accumulation
        cancel_bot_orders(bot_id)

        remaining_gold = gold

        # Strategy: Provide liquidity at target price extremes
        # Buy orders at MIN price (sets price floor)
        # Sell orders at MAX price (sets price ceiling)

        # First pass: Place BUY orders at minimum prices to set floor
        # Only buy if we're below our target reserve level
        for resource, price_info in TARGET_PRICES.items():
            min_price = price_info["min"]
            target_reserve = MIN_RESERVES[resource] * 3  # 3x minimum is target
            reserve = resources.get(resource, 0)

            # If below target, allocate gold to buy more
            if reserve < target_reserve and remaining_gold > min_price * 10000:
                # Calculate how much to buy to reach target
                buy_amount = min(
                    50000, target_reserve - reserve, remaining_gold // min_price
                )
                if buy_amount > 100:
                    buy_cost = buy_amount * min_price
                    place_buy_order(bot_id, resource, buy_amount, min_price)
                    remaining_gold -= buy_cost

        # Second pass: Place SELL orders at maximum prices to set ceiling
        # Only if we have excess above our target level
        for resource, price_info in TARGET_PRICES.items():
            max_price = price_info["max"]
            target_reserve = MIN_RESERVES[resource] * 3
            reserve = resources.get(resource, 0)

            if reserve > target_reserve:
                # Sell excess above target
                sell_amount = min(50000, reserve - target_reserve)
                if sell_amount > 100:
                    place_sell_order(bot_id, resource, sell_amount, max_price)

        logger.info(f"Market stabilization complete for Bot {bot_id}")

    except Exception as e:
        logger.error(f"Error in market stabilization: {e}")


def produce_resources(bot_id=None):
    """
    Generate resources for a bot nation (simulating production).

    This adds resources to the bot's inventory to maintain supply.

    Args:
        bot_id: ID of bot to execute (defaults to resource producer)
    """
    if bot_id is None:
        bot_id = BOT_NATION_IDS["resource_producer"]

    try:
        with get_db_cursor() as db:
            # Add daily production (adjust amounts as needed for balance)
            production = {
                "rations": 50000,
                "lumber": 40000,
                "steel": 20000,
                "aluminium": 15000,
            }

            for resource, amount in production.items():
                db.execute(
                    f"""
                    UPDATE resources
                    SET {resource} = {resource} + %s
                    WHERE id = %s
                    """,
                    (amount, bot_id),
                )

            logger.info(f"Resource production for Bot {bot_id}: {production}")

    except Exception as e:
        logger.error(f"Error in resource production: {e}")


def get_bot_status(bot_id=None):
    """
    Get current status of a bot nation.

    Args:
        bot_id: ID of bot to check (defaults to primary stabilizer)

    Returns:
        dict: Bot status information
    """
    if bot_id is None:
        bot_id = BOT_NATION_IDS["market_stabilizer"]

    try:
        resources = get_bot_resources(bot_id)
        gold = get_bot_gold(bot_id)
        prices = get_market_prices()

        status = {
            "bot_id": bot_id,
            "gold": gold,
            "resources": resources,
            "current_prices": prices,
            "active_offers": get_bot_active_offers(bot_id),
        }

        return status

    except Exception as e:
        logger.error(f"Error getting bot status: {e}")
        return {}


def get_bot_active_offers(bot_id):
    """Get active market offers from a bot nation."""
    try:
        with get_db_cursor() as db:
            db.execute(
                """
                SELECT offer_id, type, resource, amount, price
                FROM offers WHERE user_id = %s
                ORDER BY offer_id DESC LIMIT 20
                """,
                (bot_id,),
            )
            offers = []
            for row in db.fetchall():
                offers.append(
                    {
                        "offer_id": row[0],
                        "type": row[1],
                        "resource": row[2],
                        "amount": row[3],
                        "price": row[4],
                    }
                )
            return offers

    except Exception as e:
        logger.error(f"Error getting bot active offers: {e}")
        return []


def cancel_bot_orders(bot_id=None):
    """
    Cancel all active orders for a bot nation.

    Args:
        bot_id: ID of bot (defaults to primary stabilizer)
    """
    if bot_id is None:
        bot_id = BOT_NATION_IDS["market_stabilizer"]

    try:
        with get_db_cursor() as db:
            db.execute("DELETE FROM offers WHERE user_id = %s", (bot_id,))
            logger.info(f"Cancelled all orders for Bot {bot_id}")

    except Exception as e:
        logger.error(f"Error cancelling bot orders: {e}")
