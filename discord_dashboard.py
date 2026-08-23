"""Web dashboard for configuring the Discord bot's engagement features.

Auth: reuses the existing Discord OAuth2 flow (signup.py) with a dedicated
'dashboard' intent that stores the caller's guild list (with resolved
permission bitfield) in session. Access to a given guild's controls is
gated on ADMINISTRATOR / MANAGE_GUILD / ownership in that bitfield — the
same bar discord_bot/permissions.py::is_guild_admin() uses inside Discord.
"""

from flask import Blueprint, redirect, render_template, request, session

from helpers import login_required
from discord_bot import engagement_store as store

discord_dashboard_bp = Blueprint("discord_dashboard", __name__)

_PERM_ADMINISTRATOR = 0x8
_PERM_MANAGE_GUILD = 0x20


def _guild_is_manageable(guild: dict) -> bool:
    if guild.get("owner") is True:
        return True
    try:
        perms = int(guild.get("permissions", 0))
    except (TypeError, ValueError):
        return False
    return bool(perms & _PERM_ADMINISTRATOR) or bool(perms & _PERM_MANAGE_GUILD)


def _manageable_guild_or_none(guild_id: str):
    for guild in session.get("discord_dashboard_guilds") or []:
        if str(guild.get("id")) == str(guild_id) and _guild_is_manageable(guild):
            return guild
    return None


@discord_dashboard_bp.route("/discord/dashboard")
@login_required
def dashboard_home():
    guilds = session.get("discord_dashboard_guilds")
    if guilds is None:
        return render_template("discord_dashboard_connect.html")
    manageable = [g for g in guilds if _guild_is_manageable(g)]
    return render_template("discord_dashboard_guilds.html", guilds=manageable)


@discord_dashboard_bp.route("/discord/dashboard/<guild_id>")
@login_required
def dashboard_guild(guild_id):
    guild = _manageable_guild_or_none(guild_id)
    if not guild:
        return render_template("discord_dashboard_connect.html"), 403

    level_config = store.get_level_config(guild_id)
    level_roles = store.list_level_roles(guild_id)
    welcome_config = store.get_welcome_config(guild_id)
    reaction_roles = store.list_reaction_roles(guild_id)
    giveaways = store.list_active_giveaways(guild_id)
    leaderboard = store.get_leaderboard(guild_id, limit=10)

    return render_template(
        "discord_dashboard_guild.html",
        guild=guild,
        level_config=level_config,
        level_roles=level_roles,
        welcome_config=welcome_config,
        reaction_roles=reaction_roles,
        giveaways=giveaways,
        leaderboard=leaderboard,
    )


@discord_dashboard_bp.route("/discord/dashboard/<guild_id>/levels", methods=["POST"])
@login_required
def dashboard_update_levels(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("discord_dashboard_connect.html"), 403

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

    return redirect(f"/discord/dashboard/{guild_id}")


@discord_dashboard_bp.route("/discord/dashboard/<guild_id>/welcome", methods=["POST"])
@login_required
def dashboard_update_welcome(guild_id):
    if not _manageable_guild_or_none(guild_id):
        return render_template("discord_dashboard_connect.html"), 403

    cfg = store.get_welcome_config(guild_id)
    cfg.enabled = request.form.get("enabled") == "on"
    cfg.channel_id = request.form.get("channel_id") or None
    cfg.message_template = request.form.get("message_template") or None
    cfg.dm_enabled = request.form.get("dm_enabled") == "on"
    cfg.dm_template = request.form.get("dm_template") or None
    auto_roles_raw = request.form.get("auto_role_ids") or ""
    cfg.auto_role_ids = [r.strip() for r in auto_roles_raw.split(",") if r.strip()]
    store.set_welcome_config(cfg)

    return redirect(f"/discord/dashboard/{guild_id}")


@discord_dashboard_bp.route(
    "/discord/dashboard/<guild_id>/reactionrole/<message_id>/<path:emoji>/delete", methods=["POST"]
)
@login_required
def dashboard_delete_reaction_role(guild_id, message_id, emoji):
    if not _manageable_guild_or_none(guild_id):
        return render_template("discord_dashboard_connect.html"), 403
    store.remove_reaction_role(guild_id, message_id, emoji)
    return redirect(f"/discord/dashboard/{guild_id}")
