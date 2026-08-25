"""Persist ticket config and individual tickets (private-thread based support).

Mirrors the style of engagement_store.py — shared by the bot process and the
Flask dashboard so both read/write the same tables with the same shapes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from database import QueryHelper, get_db_cursor


@dataclass
class TicketConfig:
    guild_id: str
    enabled: bool = False
    ticket_channel_id: Optional[str] = None


@dataclass
class Ticket:
    id: int
    guild_id: str
    opener_user_id: str
    thread_id: str
    status: str  # open | closed
    opened_at: datetime
    closed_at: Optional[datetime]
    closed_by_user_id: Optional[str]


def get_ticket_config(guild_id: str) -> TicketConfig:
    row = QueryHelper.fetch_one(
        "SELECT guild_id, enabled, ticket_channel_id FROM discord_ticket_config WHERE guild_id = %s",
        (guild_id,),
        dict_cursor=True,
    )
    if not row:
        return TicketConfig(guild_id=guild_id)
    return TicketConfig(
        guild_id=str(row["guild_id"]),
        enabled=bool(row["enabled"]),
        ticket_channel_id=row.get("ticket_channel_id"),
    )


def set_ticket_config(config: TicketConfig) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO discord_ticket_config (guild_id, enabled, ticket_channel_id, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                ticket_channel_id = EXCLUDED.ticket_channel_id,
                updated_at = NOW()
            """,
            (config.guild_id, config.enabled, config.ticket_channel_id),
        )


def _row_to_ticket(row) -> Ticket:
    return Ticket(
        id=int(row["id"]),
        guild_id=str(row["guild_id"]),
        opener_user_id=str(row["opener_user_id"]),
        thread_id=str(row["thread_id"]),
        status=str(row["status"]),
        opened_at=row["opened_at"],
        closed_at=row.get("closed_at"),
        closed_by_user_id=row.get("closed_by_user_id"),
    )


def create_ticket(guild_id: str, opener_user_id: str, thread_id: str) -> int:
    row = QueryHelper.execute_returning(
        """
        INSERT INTO discord_tickets (guild_id, opener_user_id, thread_id)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (guild_id, opener_user_id, thread_id),
    )
    return int(row[0])


def close_ticket(ticket_id: int, closed_by_user_id: str) -> None:
    with get_db_cursor() as db:
        db.execute(
            """
            UPDATE discord_tickets
            SET status = 'closed', closed_at = NOW(), closed_by_user_id = %s
            WHERE id = %s
            """,
            (closed_by_user_id, ticket_id),
        )


def get_ticket_by_thread(guild_id: str, thread_id: str) -> Optional[Ticket]:
    row = QueryHelper.fetch_one(
        """
        SELECT id, guild_id, opener_user_id, thread_id, status, opened_at,
               closed_at, closed_by_user_id
        FROM discord_tickets WHERE guild_id = %s AND thread_id = %s
        """,
        (guild_id, thread_id),
        dict_cursor=True,
    )
    return _row_to_ticket(row) if row else None


def get_open_ticket_for_user(guild_id: str, user_id: str) -> Optional[Ticket]:
    row = QueryHelper.fetch_one(
        """
        SELECT id, guild_id, opener_user_id, thread_id, status, opened_at,
               closed_at, closed_by_user_id
        FROM discord_tickets WHERE guild_id = %s AND opener_user_id = %s AND status = 'open'
        """,
        (guild_id, user_id),
        dict_cursor=True,
    )
    return _row_to_ticket(row) if row else None


def list_open_tickets(guild_id: str) -> List[Ticket]:
    rows = QueryHelper.fetch_all(
        """
        SELECT id, guild_id, opener_user_id, thread_id, status, opened_at,
               closed_at, closed_by_user_id
        FROM discord_tickets WHERE guild_id = %s AND status = 'open'
        ORDER BY opened_at DESC
        """,
        (guild_id,),
        dict_cursor=True,
    )
    return [_row_to_ticket(r) for r in rows or []]
