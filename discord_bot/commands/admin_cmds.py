"""Staff-only admin slash commands (not available to regular players)."""


import asyncio

import discord
from discord import app_commands

from discord_bot.guild_store import get_guild_settings
from discord_bot.panel_service import refresh_guild_panels
from discord_bot.permissions import require_guild_admin
from discord_bot.embeds import build_nation_embed


def register_commands(tree: app_commands.CommandTree, backend) -> None:
    admin_group = app_commands.Group(
        name="admin",
        description="Staff-only game administration via Discord",
        default_permissions=discord.Permissions(administrator=True),
    )

    @admin_group.command(
        name="broadcast",
        description="Post an alert to the realm-alerts panel channel",
    )
    @app_commands.describe(
        message="Announcement text (shown on the alerts panel and as a message)",
    )
    @require_guild_admin()
    async def broadcast(
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            return
        settings = get_guild_settings(str(interaction.guild.id))
        if not settings or not settings.panel_channels.get("alerts"):
            await interaction.followup.send(
                "Bind the alerts panel first: `/guild_bind_panel` in `#realm-alerts`.",
                ephemeral=True,
            )
            return
        ch = interaction.guild.get_channel(
            int(settings.panel_channels["alerts"])
        )
        if not isinstance(ch, discord.TextChannel):
            await interaction.followup.send("Alerts channel not found.", ephemeral=True)
            return
        from discord_bot.panels.builders import build_alerts_embed

        embed = build_alerts_embed(
            headline="📢 Staff announcement",
            body=message[:4000],
        )
        await ch.send(embed=embed)
        await refresh_guild_panels(interaction.client, interaction.guild.id)
        await interaction.followup.send("Broadcast posted and alerts panel updated.", ephemeral=True)

    @admin_group.command(
        name="nation",
        description="Full nation intel (any nation id or name)",
    )
    @app_commands.describe(identifier="Nation name or numeric id")
    @require_guild_admin()
    async def admin_nation(
        interaction: discord.Interaction,
        identifier: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            ident = identifier.strip()
            data = await asyncio.to_thread(
                lambda: backend.nation(ident, trusted=True)
            )
            embed = build_nation_embed(data, "Staff — nation intel")
            embed.color = discord.Color.gold()
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            from discord_bot.backend import BotBackendError

            if isinstance(exc, BotBackendError):
                await interaction.followup.send(str(exc), ephemeral=True)
            else:
                await interaction.followup.send(
                    "Could not load nation.", ephemeral=True
                )

    @admin_group.command(
        name="whois",
        description="See which nation a Discord user is linked to",
    )
    @require_guild_admin()
    async def whois(
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            data = await asyncio.to_thread(backend.me, str(member.id))
            embed = build_nation_embed(
                data, f"Linked nation — {member.display_name}"
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as exc:
            from discord_bot.backend import BotBackendError

            if isinstance(exc, BotBackendError):
                await interaction.followup.send(
                    f"{member.mention} is not linked. ({exc})",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send("Lookup failed.", ephemeral=True)

    @admin_group.command(
        name="refresh_all_panels",
        description="Force-refresh panels for every configured guild",
    )
    @require_guild_admin()
    async def refresh_all(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        from discord_bot.panel_service import refresh_all_guild_panels

        await refresh_all_guild_panels(interaction.client)
        await interaction.followup.send("Panel refresh job completed.", ephemeral=True)

    @admin_group.command(
        name="restore_provinces",
        description="Restore province count for a user (fixes the 182M single province bug)",
    )
    @app_commands.describe(user_id="Numeric game ID of the user")
    @require_guild_admin()
    async def restore_provinces(interaction: discord.Interaction, user_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            import os
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
            if not db_url:
                await interaction.followup.send("DB not configured.", ephemeral=True)
                return
                
            conn = psycopg2.connect(db_url)
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT id, population, provincename FROM provinces WHERE userId = %s ORDER BY population DESC LIMIT 1", (user_id,))
                    row = cur.fetchone()
                    if not row:
                        await interaction.followup.send(f"No provinces found for user {user_id}", ephemeral=True)
                        return
                    
                    pop = int(row["population"])
                    if pop <= 1000000:
                        await interaction.followup.send(f"User {user_id} only has {pop} pop in their largest province, no need to restore.", ephemeral=True)
                        return
                        
                    target_provinces = max(1, pop // 1000000)
                    to_add = target_provinces - 1
                    
                    if to_add <= 0:
                        await interaction.followup.send("Nothing to add.", ephemeral=True)
                        return
                        
                    # Reset the original province's pop to 1 million
                    cur.execute("UPDATE provinces SET population = 1000000 WHERE id = %s", (row["id"],))
                    
                    # Create the rest of the provinces
                    for i in range(to_add):
                        new_name = f"{row['provincename']} {i+2}"
                        cur.execute(
                            "INSERT INTO provinces (userId, provinceName, population, citycount, land, energy, happiness, pollution, productivity, consumer_spending) VALUES (%s, %s, 1000000, 1, 1, 0, 50, 0, 50, 50)",
                            (user_id, new_name)
                        )
            conn.close()
            await interaction.followup.send(f"Successfully restored {to_add} provinces for user {user_id} based on their {pop} population.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed to restore: {e}", ephemeral=True)

    tree.add_command(admin_group)

