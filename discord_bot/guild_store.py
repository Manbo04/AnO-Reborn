"""Persist Discord guild panel configuration and message IDs."""


from dataclasses import dataclass, field
from typing import Dict, List, Optional

from database import QueryHelper, get_db_cursor

PANEL_KEYS = (
    "readme",
    "leaderboard",
    "war_feed",
    "inspector",
    "world_status",
    "alerts",
)

PANEL_CHANNEL_COLUMNS = {
    "readme": "panel_readme_channel_id",
    "leaderboard": "panel_leaderboard_channel_id",
    "war_feed": "panel_war_feed_channel_id",
    "inspector": "panel_inspector_channel_id",
    "world_status": "panel_world_channel_id",
    "alerts": "panel_alerts_channel_id",
}


@dataclass
class GuildSettings:
    guild_id: str
    coalition_id: Optional[int] = None
    registered_role_id: Optional[str] = None
    bank_alert_channel_id: Optional[str] = None
    war_alert_channel_id: Optional[str] = None
    panel_channels: Dict[str, str] = field(default_factory=dict)
    panels_enabled: bool = False
    panels_refresh_minutes: int = 15


def get_admin_role_ids(guild_id: str) -> set:
    rows = QueryHelper.fetch_all(
        """
        SELECT discord_role_id FROM discord_role_aliases
        WHERE guild_id = %s AND alias = 'admin'
        """,
        (guild_id,),
    )
    out: set = set()
    for row in rows or []:
        rid = row[0] if isinstance(row, (list, tuple)) else row.get("discord_role_id")
        if rid and str(rid).isdigit():
            out.add(int(rid))
    return out


def set_admin_role(guild_id: str, discord_role_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_role_aliases (guild_id, alias, discord_role_id)
            VALUES (%s, 'admin', %s)
            ON CONFLICT (guild_id, alias)
            DO UPDATE SET discord_role_id = EXCLUDED.discord_role_id
            """,
            (guild_id, str(discord_role_id)),
        )


def get_guild_settings(guild_id: str) -> Optional[GuildSettings]:
    row = QueryHelper.fetch_one(
        """
        SELECT guild_id, coalition_id, registered_role_id,
               bank_alert_channel_id, war_alert_channel_id,
               panel_readme_channel_id, panel_leaderboard_channel_id,
               panel_war_feed_channel_id, panel_inspector_channel_id,
               panel_world_channel_id, panel_alerts_channel_id,
               panels_enabled, panels_refresh_minutes
        FROM discord_guild_settings
        WHERE guild_id = %s
        """,
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return None
    panels: Dict[str, str] = {}
    for key, col in PANEL_CHANNEL_COLUMNS.items():
        val = row.get(col)
        if val:
            panels[key] = str(val)
    return GuildSettings(
        guild_id=str(row["guild_id"]),
        coalition_id=row.get("coalition_id"),
        registered_role_id=row.get("registered_role_id"),
        bank_alert_channel_id=row.get("bank_alert_channel_id"),
        war_alert_channel_id=row.get("war_alert_channel_id"),
        panel_channels=panels,
        panels_enabled=bool(row.get("panels_enabled")),
        panels_refresh_minutes=int(row.get("panels_refresh_minutes") or 15),
    )


def ensure_guild_row(guild_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_guild_settings (guild_id)
            VALUES (%s)
            ON CONFLICT (guild_id) DO NOTHING
            """,
            (guild_id,),
        )


def bind_panel_channel(guild_id: str, panel_key: str, channel_id: str) -> None:
    if panel_key not in PANEL_CHANNEL_COLUMNS:
        raise ValueError(f"Unknown panel: {panel_key}")
    ensure_guild_row(guild_id)
    col = PANEL_CHANNEL_COLUMNS[panel_key]
    with get_db_cursor() as db:
        db.execute(
            f"""
            UPDATE discord_guild_settings
            SET {col} = %s, panels_enabled = TRUE, updated_at = NOW()
            WHERE guild_id = %s
            """,
            (channel_id, guild_id),
        )


def set_panels_enabled(guild_id: str, enabled: bool) -> None:
    ensure_guild_row(guild_id)
    with get_db_cursor() as db:
        db.execute(
            """
            UPDATE discord_guild_settings
            SET panels_enabled = %s, updated_at = NOW()
            WHERE guild_id = %s
            """,
            (enabled, guild_id),
        )


def get_panel_message_id(guild_id: str, panel_key: str) -> Optional[str]:
    row = QueryHelper.fetch_one(
        """
        SELECT message_id FROM discord_panel_messages
        WHERE guild_id = %s AND panel_key = %s
        """,
        (guild_id, panel_key),
    )
    return str(row[0]) if row else None


def save_panel_message(
    guild_id: str, panel_key: str, channel_id: str, message_id: str
) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_panel_messages
                (guild_id, panel_key, channel_id, message_id, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (guild_id, panel_key)
            DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                message_id = EXCLUDED.message_id,
                updated_at = NOW()
            """,
            (guild_id, panel_key, channel_id, message_id),
        )


def list_configured_guild_ids() -> List[str]:
    rows = QueryHelper.fetch_all(
        """
        SELECT guild_id FROM discord_guild_settings
        WHERE panels_enabled = TRUE
        """
    )
    return [str(r[0]) for r in rows or []]
