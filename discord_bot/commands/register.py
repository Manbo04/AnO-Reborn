import discord
from discord import app_commands

from discord_bot.backend import BotBackend, BotBackendError
from discord_bot.config import GAME_BASE_URL


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
            data = backend.register(str(interaction.user.id), code.strip())
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
            await interaction.followup.send(embed=embed, ephemeral=True)
        except BotBackendError as exc:
            await interaction.followup.send(
                f"Registration failed: {exc}",
                ephemeral=True,
            )
