# Contributing

Thank you for helping. Fixes, docs and ideas are all welcome, and merged fixes earn a [bounty](BOUNTIES.md).

## Quick path

1. Pick a bug (yours, or an open issue).
2. Fork the repo and create a branch: `fix/short-description`.
3. Make the change and add a test if you can (extra bounty).
4. Open a pull request that says **what was wrong, why, and how you checked**.
5. CI runs on every PR. When it is green and a maintainer approves, it merges.

`master` is protected. You cannot push to it directly.

## Run it locally

You need Python 3.10, PostgreSQL and Redis.

```bash
git clone https://github.com/Manbo04/AnO-Reborn.git
cd AnO-Reborn
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then fill in your Postgres and Redis details
```

Create the database, then start the app:

```bash
python affo/create_db.py         # first run only
flask run                        # http://127.0.0.1:5000
```

The hourly game clock needs Redis plus Celery. You can skip it for most front-end and page fixes:

```bash
celery -A app.celery beat --loglevel=INFO
celery -A app.celery worker --loglevel=INFO
```

Run tests with `python -m pytest tests/ -q`. Some tests need a database (`DATABASE_URL`).

> Never point a local run at the production database.

## Before you change game logic

Read [`docs/GAME_RULES.md`](docs/GAME_RULES.md). It lists what each mechanic must do and which test enforces it. If you change a mechanic, update that section in the same PR.

Two rules save the most trouble:

- **One formula, two consumers.** A number shown on a page and the same number used by the hourly tick must come from the same function.
- **Move money through the shared helpers** and protect anything that can be double-clicked against races.

## Good pull requests

- One problem per PR.
- Say how you verified it (test, screenshot, steps).
- Match the style of the surrounding code.
- Do not commit secrets, `.env` files or database dumps.

## Other ways to help

Answer questions, write guides, improve text and tooltips. See the [README](README.md#you-are-welcome-here).
