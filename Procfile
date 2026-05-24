web: bash scripts/start_production.sh
worker: celery -A tasks worker --loglevel=INFO
beat: python scripts/run_beat_if_leader.py
discord-bot: python scripts/run_discord_bot_if_leader.py
