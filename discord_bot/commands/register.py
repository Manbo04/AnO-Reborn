import asyncio
import logging

import discord
from discord import app_commands

from discord_bot.backend import BotBackend, BotBackendError
from discord_bot.config import GAME_BASE_URL

logger = logging.getLogger(__name__)

COALITION_REP_ROLE_FRAGMENT = "coalition representative"


def _find_coalition_rep_role(guild: discord.Guild) -> discord.Role | None:
    return discord.utils.find(
        lambda r: COALITION_REP_ROLE_FRAGMENT in r.name.lower(),
        guild.roles,
    )


async def _maybe_grant_coalition_rep_role(
    interaction: discord.Interaction, is_leader: bool
) -> str | None:
    """Grant the Coalition Representative role if the linked nation leads a coalition.

    Returns a status string when the role was assigned (for the confirmation embed),
    or None when nothing happened. Failures are logged but do not disturb registration.
    """
    if not is_leader or not interaction.guild or not isinstance(interaction.user, discord.Member):
        return None

    role = _find_coalition_rep_role(interaction.guild)
    if role is None:
        logger.info(
            "Coalition leader registered in guild %s but no 'Coalition Representative' role exists",
            interaction.guild.id,
        )
        return None
    if role in interaction.user.roles:
        return f"Already had {role.mention}"

    try:
        await interaction.user.add_roles(
            role, reason="AnO: coalition leader registered via /register"
        )
    except discord.Forbidden:
        logger.warning(
            "Cannot assign %s in guild %s — missing Manage Roles or role hierarchy",
            role.name,
            interaction.guild.id,
        )
        return None
    except Exception as exc:
        logger.warning("add_roles failed: %s", exc)
        return None
    return f"Granted {role.mention}"


def register_commands(
    tree: app_commands.CommandTree, backend: BotBackend
) -> None:
    @tree.command(
        name="register",
        description="Link your Discord account to your AnO nation using a code from the account page",
    )
    @app_commands.describe(code="8-character code from https://affairsandorder.com/account")
    async def register_cmd(interaction: discord.Interaction, code: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            data = await asyncio.to_thread(
                backend.register, str(interaction.user.id), code.strip()
            )
            user_id = data.get("user_id")
            url = f"{GAME_BASE_URL}/country/id={user_id}" if user_id else GAME_BASE_URL
            nation_name = data.get("username") or "your nation"
            embed = discord.Embed(
                title="Nation linked",
                description=(
                    f"Successfully linked! Welcome back, **{nation_name}**. "
                    "Your nation is synced with Discord. Try `/me` for stats."
                ),
                color=discord.Color.green(),
            )
            if user_id:
                embed.add_field(name="Country page", value=url, inline=False)

            rep_status = await _maybe_grant_coalition_rep_role(
                interaction, bool(data.get("is_coalition_leader"))
            )
            if rep_status:
                embed.add_field(
                    name="Coalition Representative",
                    value=rep_status,
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except BotBackendError as exc:
            await interaction.followup.send(
                f"Registration failed: {exc}",
                ephemeral=True,
            )
