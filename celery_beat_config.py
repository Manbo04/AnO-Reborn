"""
Celery Beat scheduling configuration for automatic tasks.

This sets up automatic execution of market stabilization, resource production,
and other bot nation tasks without manual intervention.
"""

# Bot task scheduling
CELERY_BEAT_SCHEDULE = {
    # Market stabilization every 30 minutes (fast response to market changes)
    "bot-market-stabilization": {
        "task": "tasks.task_bot_market_stabilization",
        "schedule": 1800.0,  # 30 minutes in seconds
    },
    # Resource production every 1 hour (daily production per hour)
    "bot-resource-production": {
        "task": "tasks.task_bot_resource_production",
        "schedule": 3600.0,  # 1 hour in seconds
    },
    # Clean up stale orders every 2 hours
    "bot-cancel-stale-orders": {
        "task": "tasks.task_bot_cancel_stale_orders",
        "schedule": 7200.0,  # 2 hours in seconds
    },
    # Monitor and log bot status every 30 minutes
    "bot-status-check": {
        "task": "tasks.task_bot_check_status",
        "schedule": 1800.0,  # 30 minutes in seconds
    },
}

# Example of how to use with Celery config:
# celery.conf.beat_schedule = CELERY_BEAT_SCHEDULE
