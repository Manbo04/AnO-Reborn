"""Guild admin checks for staff-only slash commands."""


import os
from typing import Optional, Set

import discord
from discord import app_commands

from discord_bot.guild_store import get_admin_role_ids


def _env_admin_role_ids() -> Set[int]:
    raw = (os.getenv("DISCORD_ADMIN_ROLE_IDS") or "").strip()
    if not raw:
        return set()
    out: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


async def is_guild_admin(
    interaction: discord.Interaction,
    *,
    guild_id: Optional[int] = None,
) -> bool:
    """True if member may run staff /admin and /guild configuration commands."""
    if not interaction.guild or not interaction.user:
        return False
    member = interaction.user
    if isinstance(member, discord.Member):
        if member.guild_permissions.administrator:
            return True
        if member.guild_permissions.manage_guild:
            return True
    gid = str(guild_id or interaction.guild.id)
    admin_roles = get_admin_role_ids(gid) | _env_admin_role_ids()
    if isinstance(member, discord.Member) and admin_roles:
        return any(r.id in admin_roles for r in member.roles)
    return False


def require_guild_admin():
    """App command check: reject non-admins with a clear message."""

    async def predicate(interaction: discord.Interaction) -> bool:
        if await is_guild_admin(interaction):
            return True
        raise app_commands.CheckFailure(
            "This command is restricted to server administrators and configured staff roles."
        )

    return app_commands.check(predicate)
