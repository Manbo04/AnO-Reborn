"""Standalone web dashboard for the Discord bot's engagement features.

Runs as its own Flask app inside the bot's Railway service (started on a
background thread by discord_bot.main), on the bot's own free Railway
domain — fully independent from the main game's Flask app/domain/session.

Auth: self-contained Discord OAuth2 (identify + guilds scope). Access to a
guild's controls is gated on ADMINISTRATOR / MANAGE_GUILD / ownership in the
permission bitfield Discord returns for that guild — the same bar
discord_bot/permissions.py::is_guild_admin() uses inside Discord itself.
"""

import os

from flask import Flask, redirect, render_template, request, session
from requests_oauthlib import OAuth2Session
from werkzeug.middleware.proxy_fix import ProxyFix

from discord_bot import engagement_store as store

app = Flask(__name__, template_folder="dashboard_templates")
app.secret_key = os.getenv("SECRET_KEY", "")
# Railway terminates TLS at its edge and forwards over plain HTTP — without
# this, Flask sees request.url as http:// and oauthlib refuses the token
# exchange ("OAuth 2 MUST utilize https").
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

API_BASE_URL = "https://discord.com/api"
AUTHORIZATION_BASE_URL = API_BASE_URL + "/oauth2/authorize"
TOKEN_URL = API_BASE_URL + "/oauth2/token"

_PERM_ADMINISTRATOR = 0x8
_PERM_MANAGE_GUILD = 0x20


def _redirect_uri() -> str:
    explicit = os.getenv("DASHBOARD_REDIRECT_URI")
    if explicit:
        return explicit
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if domain:
        return f"https://{domain}/callback"
    return "http://127.0.0.1:8080/callback"


def _client_id() -> str:
    return (os.getenv("DISCORD_CLIENT_ID") or "").strip()


def _client_secret() -> str:
    return (os.getenv("DISCORD_CLIENT_SECRET") or "").strip()


def _make_session(token=None, state=None) -> OAuth2Session:
    return OAuth2Session(
        client_id=_client_id(),
        token=token,
        state=state,
        scope=["identify", "guilds"],
        redirect_uri=_redirect_uri(),
    )


def _guild_is_manageable(guild: dict) -> bool:
    if guild.get("owner") is True:
        return True
    try:
        perms = int(guild.get("permissions", 0))
    except (TypeError, ValueError):
        return False
    return bool(perms & _PERM_ADMINISTRATOR) or bool(perms & _PERM_MANAGE_GUILD)


def _manageable_guild_or_none(guild_id: str):
    for guild in session.get("guilds") or []:
        if str(guild.get("id")) == str(guild_id) and _guild_is_manageable(guild):
            return guild
    return None


@app.route("/health")
def health():
    return "ok"


@app.route("/")
def index():
    return redirect("/dashboard")


@app.route("/login")
def login():
    if not _client_id() or not _client_secret():
        return "Dashboard is misconfigured: DISCORD_CLIENT_ID/DISCORD_CLIENT_SECRET not set.", 500
    discord = _make_session()
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)
    session["oauth2_state"] = state
    return redirect(authorization_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/dashboard")


@app.route("/callback")
def callback():
    if request.values.get("error"):
        return request.values["error"], 400
    discord = _make_session(state=session.get("oauth2_state"))
    try:
        token = discord.fetch_token(
            TOKEN_URL,
            client_secret=_client_secret(),
            authorization_response=request.url,
        )
    except Exception as exc:
        return f"Discord login failed: {exc}", 400

    session["oauth2_token"] = token
    discord = _make_session(token=token)
    me = discord.get(API_BASE_URL + "/users/@me").json()
    guilds_resp = discord.get(API_BASE_URL + "/users/@me/guilds")
    session["discord_user"] = {"id": me.get("id"), "username": me.get("username")}
    session["guilds"] = guilds_resp.json() if guilds_resp.status_code == 200 else []
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard_home():
    if "discord_user" not in session:
        return render_template("connect.html")
    manageable = [g for g in session.get("guilds") or [] if _guild_is_manageable(g)]
    return render_template("guilds.html", guilds=manageable, user=session["discord_user"])


@app.route("/dashboard/<guild_id>")
def dashboard_guild(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("connect.html"), 403

    return render_template(
        "guild.html",
        guild=guild,
        level_config=store.get_level_config(guild_id),
        level_roles=store.list_level_roles(guild_id),
        welcome_config=store.get_welcome_config(guild_id),
        reaction_roles=store.list_reaction_roles(guild_id),
        giveaways=store.list_active_giveaways(guild_id),
        leaderboard=store.get_leaderboard(guild_id, limit=10),
    )


@app.route("/dashboard/<guild_id>/levels", methods=["POST"])
def dashboard_update_levels(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403

    config = store.get_level_config(guild_id)
    config.xp_per_message = int(request.form.get("xp_per_message") or config.xp_per_message)
    config.xp_cooldown_seconds = int(
        request.form.get("xp_cooldown_seconds") or config.xp_cooldown_seconds
    )
    config.xp_per_voice_minute = int(
        request.form.get("xp_per_voice_minute") or config.xp_per_voice_minute
    )
    config.level_up_channel_id = request.form.get("level_up_channel_id") or None
    config.level_up_enabled = request.form.get("level_up_enabled") == "on"
    store.set_level_config(config)

    reward_level = request.form.get("reward_level")
    reward_role_id = request.form.get("reward_role_id")
    if reward_level and reward_role_id:
        store.set_level_role(guild_id, int(reward_level), reward_role_id)

    return redirect(f"/dashboard/{guild_id}")


@app.route("/dashboard/<guild_id>/welcome", methods=["POST"])
def dashboard_update_welcome(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403

    cfg = store.get_welcome_config(guild_id)
    cfg.enabled = request.form.get("enabled") == "on"
    cfg.channel_id = request.form.get("channel_id") or None
    cfg.message_template = request.form.get("message_template") or None
    cfg.dm_enabled = request.form.get("dm_enabled") == "on"
    cfg.dm_template = request.form.get("dm_template") or None
    auto_roles_raw = request.form.get("auto_role_ids") or ""
    cfg.auto_role_ids = [r.strip() for r in auto_roles_raw.split(",") if r.strip()]
    store.set_welcome_config(cfg)

    return redirect(f"/dashboard/{guild_id}")


@app.route(
    "/dashboard/<guild_id>/reactionrole/<message_id>/<path:emoji>/delete", methods=["POST"]
)
def dashboard_delete_reaction_role(guild_id, message_id, emoji):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    store.remove_reaction_role(guild_id, message_id, emoji)
    return redirect(f"/dashboard/{guild_id}")


def run() -> None:
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, use_reloader=False)
