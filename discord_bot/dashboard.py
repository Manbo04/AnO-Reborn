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

# Discord returns the full union of scopes it's already granted this
# user for our client_id (the game's own "identify email" login flow
# shares the same Discord app), not just what this request asked for —
# requests_oauthlib hard-fails on any scope mismatch by default.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from flask import Flask, redirect, render_template, request, session
from requests_oauthlib import OAuth2Session
from werkzeug.middleware.proxy_fix import ProxyFix

from discord_bot import customcommands_store
from discord_bot import engagement_store as store
from discord_bot import logging_store
from discord_bot import moderation_store
from discord_bot import starboard_store
from discord_bot import suggestions_store
from discord_bot import tickets_store

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


def _fetch_guilds() -> list:
    """Fetch the caller's guild list live from Discord using the stored token.

    Not cached in the session cookie: a user's full guild list (every field
    Discord returns, for every server) easily blows past browsers' ~4KB
    cookie limit, which gets silently dropped — logging the user right back
    out. The OAuth token itself is small, so we keep only that and re-fetch.
    """
    token = session.get("oauth2_token")
    if not token:
        return []
    discord = _make_session(token=token)
    resp = discord.get(API_BASE_URL + "/users/@me/guilds")
    return resp.json() if resp.status_code == 200 else []


def _manageable_guild_or_none(guild_id: str):
    for guild in _fetch_guilds():
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
    session["discord_user"] = {"id": me.get("id"), "username": me.get("username")}
    return redirect("/dashboard")


@app.route("/dashboard")
def dashboard_home():
    if "discord_user" not in session:
        return render_template("connect.html")
    manageable = [g for g in _fetch_guilds() if _guild_is_manageable(g)]
    return render_template("guilds.html", guilds=manageable, user=session["discord_user"])


@app.route("/dashboard/<guild_id>")
def dashboard_guild(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("connect.html"), 403

    return render_template(
        "guild.html",
        guild=guild,
        active_tab="engagement",
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


@app.route("/dashboard/<guild_id>/logging")
def dashboard_logging(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("connect.html"), 403
    return render_template(
        "guild_logging.html",
        guild=guild,
        active_tab="logging",
        logging_config=logging_store.get_logging_config(guild_id),
    )


@app.route("/dashboard/<guild_id>/logging/config", methods=["POST"])
def dashboard_update_logging(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403

    config = logging_store.get_logging_config(guild_id)
    config.log_channel_id = request.form.get("log_channel_id") or None
    config.log_message_edit = request.form.get("log_message_edit") == "on"
    config.log_message_delete = request.form.get("log_message_delete") == "on"
    config.log_member_join = request.form.get("log_member_join") == "on"
    config.log_member_leave = request.form.get("log_member_leave") == "on"
    config.log_member_ban = request.form.get("log_member_ban") == "on"
    config.log_member_timeout = request.form.get("log_member_timeout") == "on"
    config.log_role_changes = request.form.get("log_role_changes") == "on"
    config.log_channel_changes = request.form.get("log_channel_changes") == "on"
    logging_store.set_logging_config(config)

    return redirect(f"/dashboard/{guild_id}/logging")


@app.route("/dashboard/<guild_id>/moderation")
def dashboard_moderation(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("connect.html"), 403
    return render_template(
        "guild_moderation.html",
        guild=guild,
        active_tab="moderation",
        mod_config=moderation_store.get_moderation_config(guild_id),
        bad_words=moderation_store.list_bad_words(guild_id),
        cases=moderation_store.list_cases(guild_id, limit=20),
    )


@app.route("/dashboard/<guild_id>/moderation/config", methods=["POST"])
def dashboard_update_moderation(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403

    config = moderation_store.get_moderation_config(guild_id)
    config.log_channel_id = request.form.get("log_channel_id") or None
    config.filter_spam_enabled = request.form.get("filter_spam_enabled") == "on"
    config.filter_spam_message_limit = int(
        request.form.get("filter_spam_message_limit") or config.filter_spam_message_limit
    )
    config.filter_spam_interval_seconds = int(
        request.form.get("filter_spam_interval_seconds") or config.filter_spam_interval_seconds
    )
    config.filter_invites_enabled = request.form.get("filter_invites_enabled") == "on"
    config.filter_mass_mentions_enabled = request.form.get("filter_mass_mentions_enabled") == "on"
    config.filter_mass_mentions_limit = int(
        request.form.get("filter_mass_mentions_limit") or config.filter_mass_mentions_limit
    )
    config.filter_bad_words_enabled = request.form.get("filter_bad_words_enabled") == "on"
    config.filter_action = request.form.get("filter_action") or config.filter_action
    config.filter_timeout_minutes = int(
        request.form.get("filter_timeout_minutes") or config.filter_timeout_minutes
    )
    moderation_store.set_moderation_config(config)

    return redirect(f"/dashboard/{guild_id}/moderation")


@app.route("/dashboard/<guild_id>/moderation/badwords/add", methods=["POST"])
def dashboard_add_bad_word(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    word = (request.form.get("word") or "").strip()
    if word:
        moderation_store.add_bad_word(guild_id, word)
    return redirect(f"/dashboard/{guild_id}/moderation")


@app.route("/dashboard/<guild_id>/moderation/badwords/<word>/delete", methods=["POST"])
def dashboard_delete_bad_word(guild_id, word):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    moderation_store.remove_bad_word(guild_id, word)
    return redirect(f"/dashboard/{guild_id}/moderation")


@app.route("/dashboard/<guild_id>/customcommands")
def dashboard_customcommands(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("connect.html"), 403
    return render_template(
        "guild_customcommands.html",
        guild=guild,
        active_tab="customcommands",
        custom_commands=customcommands_store.list_custom_commands(guild_id),
    )


@app.route("/dashboard/<guild_id>/customcommands/save", methods=["POST"])
def dashboard_save_customcommand(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403

    trigger = (request.form.get("trigger") or "").strip()
    if trigger:
        command_id = request.form.get("id")
        customcommands_store.save_custom_command(
            guild_id=guild_id,
            trigger=trigger,
            response_type=request.form.get("response_type") or "text",
            response_text=request.form.get("response_text") or None,
            embed_title=request.form.get("embed_title") or None,
            embed_color=request.form.get("embed_color") or None,
            command_id=int(command_id) if command_id else None,
        )
    return redirect(f"/dashboard/{guild_id}/customcommands")


@app.route("/dashboard/<guild_id>/customcommands/<int:command_id>/delete", methods=["POST"])
def dashboard_delete_customcommand(guild_id, command_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    customcommands_store.delete_custom_command(guild_id, command_id)
    return redirect(f"/dashboard/{guild_id}/customcommands")


@app.route("/dashboard/<guild_id>/community")
def dashboard_community(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("connect.html"), 403
    return render_template(
        "guild_community.html",
        guild=guild,
        active_tab="community",
        starboard_config=starboard_store.get_starboard_config(guild_id),
        ticket_config=tickets_store.get_ticket_config(guild_id),
        open_tickets=tickets_store.list_open_tickets(guild_id),
        suggestions_config=suggestions_store.get_suggestions_config(guild_id),
        suggestions=suggestions_store.list_suggestions(guild_id, limit=20),
    )


@app.route("/dashboard/<guild_id>/community/starboard", methods=["POST"])
def dashboard_update_starboard(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    config = starboard_store.get_starboard_config(guild_id)
    config.enabled = request.form.get("enabled") == "on"
    config.channel_id = request.form.get("channel_id") or None
    config.emoji = request.form.get("emoji") or config.emoji
    config.threshold = int(request.form.get("threshold") or config.threshold)
    starboard_store.set_starboard_config(config)
    return redirect(f"/dashboard/{guild_id}/community")


@app.route("/dashboard/<guild_id>/community/tickets", methods=["POST"])
def dashboard_update_tickets(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    config = tickets_store.get_ticket_config(guild_id)
    config.enabled = request.form.get("enabled") == "on"
    config.ticket_channel_id = request.form.get("ticket_channel_id") or None
    tickets_store.set_ticket_config(config)
    return redirect(f"/dashboard/{guild_id}/community")


@app.route("/dashboard/<guild_id>/community/suggestions", methods=["POST"])
def dashboard_update_suggestions(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("connect.html"), 403
    config = suggestions_store.get_suggestions_config(guild_id)
    config.enabled = request.form.get("enabled") == "on"
    config.channel_id = request.form.get("channel_id") or None
    suggestions_store.set_suggestions_config(config)
    return redirect(f"/dashboard/{guild_id}/community")


def run() -> None:
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)
