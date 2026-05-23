import discord
from discord import app_commands

from discord_bot.backend import BotBackend, BotBackendError
from discord_bot.config import GAME_BASE_URL


def _country_url(nation_id: int) -> str:
    return f"{GAME_BASE_URL}/country/id={nation_id}"


def _embed_nation(data: dict, title: str) -> discord.Embed:
    nation_id = data.get("id")
    embed = discord.Embed(
        title=title,
        description=f"**{data.get('username', '?')}** (id {nation_id})",
        color=discord.Color.blue(),
        url=_country_url(nation_id) if nation_id else None,
    )
    embed.add_field(name="Gold", value=f"{data.get('gold', 0):,}", inline=True)
    embed.add_field(name="Influence", value=f"{data.get('influence', 0):,}", inline=True)
    embed.add_field(
        name="Provinces",
        value=str(data.get("province_count", 0)),
        inline=True,
    )
    col = data.get("coalition") or {}
    if col.get("coalition_name"):
        embed.add_field(
            name="Coalition",
            value=f"{col['coalition_name']} ({col.get('role') or 'member'})",
            inline=False,
        )
    embed.add_field(
        name="Active wars",
        value=str(data.get("active_wars", 0)),
        inline=True,
    )
    if data.get("location"):
        embed.add_field(name="Location", value=data["location"], inline=True)
    return embed


def register_commands(
    tree: app_commands.CommandTree, backend: BotBackend
) -> None:
    @tree.command(name="me", description="Show your linked AnO nation stats")
    async def me_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            data = backend.me(str(interaction.user.id))
            embed = _embed_nation(data, "Your nation")
            wars = data.get("active_wars_list") or []
            if wars:
                lines = [
                    f"#{w['war_id']}: vs **{w['opponent_name']}** ({w['side']})"
                    for w in wars[:10]
                ]
                embed.add_field(
                    name="War list",
                    value="\n".join(lines) or "None",
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @tree.command(
        name="nation",
        description="Look up any nation by username or id",
    )
    @app_commands.describe(identifier="Nation name or numeric id")
    async def nation_cmd(
        interaction: discord.Interaction, identifier: str
    ) -> None:
        await interaction.response.defer()
        try:
            data = backend.nation(identifier.strip())
            embed = _embed_nation(data, "Nation lookup")
            await interaction.followup.send(embed=embed)
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @tree.command(
        name="wars",
        description="List active wars for you or another nation",
    )
    @app_commands.describe(
        nation="Optional nation name or id (defaults to your linked nation)"
    )
    async def wars_cmd(
        interaction: discord.Interaction, nation: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=bool(nation is None))
        try:
            if nation:
                data = backend.wars(nation=nation.strip())
            else:
                data = backend.wars(discord_user_id=str(interaction.user.id))
            wars = data.get("wars") or []
            if not wars:
                await interaction.followup.send(
                    "No active wars.",
                    ephemeral=not nation,
                )
                return
            embed = discord.Embed(
                title=f"Active wars (nation {data.get('nation_id')})",
                color=discord.Color.orange(),
            )
            for w in wars[:15]:
                embed.add_field(
                    name=f"War #{w['war_id']}",
                    value=(
                        f"**{w['opponent_name']}** (id {w['opponent_id']})\n"
                        f"You are: {w['side']}"
                    ),
                    inline=False,
                )
            await interaction.followup.send(
                embed=embed, ephemeral=not nation
            )
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)

    @tree.command(
        name="resources",
        description="Top resources for you or another nation",
    )
    @app_commands.describe(
        nation="Optional nation name or id (defaults to your linked nation)"
    )
    async def resources_cmd(
        interaction: discord.Interaction, nation: str | None = None
    ) -> None:
        await interaction.response.defer(ephemeral=bool(nation is None))
        try:
            if nation:
                data = backend.resources(nation=nation.strip())
            else:
                data = backend.resources(discord_user_id=str(interaction.user.id))
            resources = data.get("resources") or {}
            embed = _embed_nation(
                data,
                f"Resources — {data.get('username', '?')}",
            )
            if resources:
                lines = [f"**{k}**: {v:,}" for k, v in resources.items()]
                embed.add_field(
                    name="Top resources",
                    value="\n".join(lines[:12]),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Top resources",
                    value="No stored commodities (gold shown above).",
                    inline=False,
                )
            await interaction.followup.send(
                embed=embed, ephemeral=not nation
            )
        except BotBackendError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
