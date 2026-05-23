"""Discord guild admin permission helpers."""
import asyncio
from unittest.mock import MagicMock, patch

from discord_bot.permissions import _env_admin_role_ids, is_guild_admin


def test_env_admin_role_ids_parses_csv():
    with patch.dict("os.environ", {"DISCORD_ADMIN_ROLE_IDS": "111,222"}):
        assert _env_admin_role_ids() == {111, 222}


def test_is_guild_admin_by_permission():
    import discord

    interaction = MagicMock()
    interaction.guild = MagicMock()
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = True
    member.guild_permissions.manage_guild = False
    member.roles = []
    interaction.user = member
    assert asyncio.run(is_guild_admin(interaction)) is True


def test_is_guild_admin_denied():
    import discord

    interaction = MagicMock()
    interaction.guild = MagicMock(id=999)
    member = MagicMock(spec=discord.Member)
    member.guild_permissions.administrator = False
    member.guild_permissions.manage_guild = False
    member.roles = []
    interaction.user = member
    with patch("discord_bot.permissions.get_admin_role_ids", return_value=set()):
        with patch("discord_bot.permissions._env_admin_role_ids", return_value=set()):
            assert asyncio.run(is_guild_admin(interaction)) is False
