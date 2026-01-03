#!/usr/bin/env python3
"""
CLI tool for managing bot nations and market stabilization.

Usage:
  python bot_cli.py init                          # Initialize bot nations
  python bot_cli.py status [bot_name]             # Check bot status
  python bot_cli.py stabilize [bot_name]          # Run market stabilization
  python bot_cli.py produce [bot_name]            # Run resource production
  python bot_cli.py cancel-orders [bot_name]      # Cancel all bot orders
  python bot_cli.py config                        # Show bot configuration
"""

import sys
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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cmd_init():
    """Initialize bot nations."""
    try:
        logger.info("Initializing bot nations...")
        ensure_bot_nations_exist()
        logger.info("✓ Bot nations initialized successfully")

        for bot_name, bot_id in BOT_NATION_IDS.items():
            status = get_bot_status(bot_id)
            print(f"\n{bot_name} (ID: {bot_id}):")
            print(f"  Gold: {status.get('gold', 0):,}")
            resources = status.get("resources", {})
            for resource, amount in resources.items():
                print(f"  {resource.capitalize()}: {amount:,}")

    except Exception as e:
        logger.error(f"✗ Error initializing bots: {e}")
        sys.exit(1)


def cmd_status(bot_name=None):
    """Check bot status."""
    try:
        if bot_name and bot_name not in BOT_NATION_IDS:
            logger.error(f"Unknown bot: {bot_name}")
            logger.info(f"Available bots: {', '.join(BOT_NATION_IDS.keys())}")
            sys.exit(1)

        bots_to_check = (
            {bot_name: BOT_NATION_IDS[bot_name]} if bot_name else BOT_NATION_IDS
        )

        for name, bot_id in bots_to_check.items():
            status = get_bot_status(bot_id)
            print(f"\n{'=' * 50}")
            print(f"Bot: {name.upper()} (ID: {bot_id})")
            print(f"{'=' * 50}")
            print(f"Gold: {status.get('gold', 0):,}")

            print("\nResources:")
            resources = status.get("resources", {})
            for resource, amount in sorted(resources.items()):
                min_reserve = MIN_RESERVES.get(resource, 0)
                status_mark = "✓" if amount >= min_reserve else "⚠"
                res_str = (
                    f"{resource.capitalize()}: {amount:,} " f"(min: {min_reserve:,})"
                )
                print(f"  {status_mark} {res_str}")

            print("\nMarket Prices:")
            prices = status.get("current_prices", {})
            for resource, price in sorted(prices.items()):
                target = TARGET_PRICES.get(resource, {})
                min_p = target.get("min", 0)
                max_p = target.get("max", 0)
                mark = "↓" if price < min_p else ("↑" if price > max_p else "→")
                price_str = (
                    f"{resource.capitalize()}: {price}g (target: {min_p}-{max_p})"
                )
                print(f"  {mark} {price_str}")

            print("\nActive Offers:")
            offers = status.get("active_offers", [])
            if offers:
                for offer in offers[:5]:  # Show last 5 offers
                    offer_str = (
                        f"{offer['offer_id']}: {offer['type'].upper()} "
                        f"{offer['amount']} {offer['resource']} "
                        f"@ {offer['price']}g"
                    )
                    print(f"  {offer_str}")
                if len(offers) > 5:
                    print(f"  ... and {len(offers) - 5} more")
            else:
                print("  No active offers")

    except Exception as e:
        logger.error(f"✗ Error checking bot status: {e}")
        sys.exit(1)


def cmd_stabilize(bot_name=None):
    """Run market stabilization."""
    try:
        ensure_bot_nations_exist()
        bot_id = BOT_NATION_IDS.get(bot_name or "market_stabilizer")

        if not bot_id:
            logger.error(f"Unknown bot: {bot_name}")
            logger.info(f"Available bots: {', '.join(BOT_NATION_IDS.keys())}")
            sys.exit(1)

        bot_name_str = bot_name or "market_stabilizer"
        logger.info(f"Running market stabilization for bot {bot_name_str}...")
        execute_market_stabilization(bot_id)
        logger.info("✓ Market stabilization completed")

        print("\nBot status after stabilization:")
        status = get_bot_status(bot_id)
        print(f"Gold: {status.get('gold', 0):,}")
        print(f"Active offers: {len(status.get('active_offers', []))}")

    except Exception as e:
        logger.error(f"✗ Error in market stabilization: {e}")
        sys.exit(1)


def cmd_produce(bot_name=None):
    """Run resource production."""
    try:
        ensure_bot_nations_exist()
        bot_id = BOT_NATION_IDS.get(bot_name or "resource_producer")

        if not bot_id:
            logger.error(f"Unknown bot: {bot_name}")
            logger.info(f"Available bots: {', '.join(BOT_NATION_IDS.keys())}")
            sys.exit(1)

        bot_name_str = bot_name or "resource_producer"
        logger.info(f"Running resource production for bot {bot_name_str}...")
        produce_resources(bot_id)
        logger.info("✓ Resource production completed")

        print("\nBot resources after production:")
        status = get_bot_status(bot_id)
        resources = status.get("resources", {})
        for resource, amount in sorted(resources.items()):
            print(f"  {resource.capitalize()}: {amount:,}")

    except Exception as e:
        logger.error(f"✗ Error in resource production: {e}")
        sys.exit(1)


def cmd_cancel_orders(bot_name=None):
    """Cancel all bot orders."""
    try:
        bot_id = BOT_NATION_IDS.get(bot_name or "market_stabilizer")

        if not bot_id:
            logger.error(f"Unknown bot: {bot_name}")
            logger.info(f"Available bots: {', '.join(BOT_NATION_IDS.keys())}")
            sys.exit(1)

        bot_name_str = bot_name or "market_stabilizer"
        logger.info(f"Cancelling orders for bot {bot_name_str}...")
        cancel_bot_orders(bot_id)
        logger.info("✓ Orders cancelled")

    except Exception as e:
        logger.error(f"✗ Error cancelling orders: {e}")
        sys.exit(1)


def cmd_config():
    """Show bot configuration."""
    print("\n" + "=" * 50)
    print("BOT NATIONS CONFIGURATION")
    print("=" * 50)

    print("\nBot IDs:")
    for name, bot_id in BOT_NATION_IDS.items():
        print(f"  {name}: {bot_id}")

    print("\nTarget Prices (gold per unit):")
    for resource, prices in sorted(TARGET_PRICES.items()):
        price_range = (
            f"{resource.capitalize()}: {prices['min']}-{prices['max']}g "
            f"(target: {prices['target']}g)"
        )
        print(f"  {price_range}")

    print("\nMinimum Reserves:")
    for resource, amount in sorted(MIN_RESERVES.items()):
        print(f"  {resource.capitalize()}: {amount:,} units")


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None

    if command == "init":
        cmd_init()
    elif command == "status":
        cmd_status(arg)
    elif command == "stabilize":
        cmd_stabilize(arg)
    elif command == "produce":
        cmd_produce(arg)
    elif command == "cancel-orders":
        cmd_cancel_orders(arg)
    elif command == "config":
        cmd_config()
    else:
        logger.error(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
