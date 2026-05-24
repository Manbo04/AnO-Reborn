"""Load live game data for Discord information panels."""

from __future__ import annotations

from typing import Any, Dict, List

from database import QueryHelper, get_coalition_members_table


def fetch_leaderboard(limit: int = 10) -> List[Dict[str, Any]]:
    rows = QueryHelper.fetch_all(
        """
        SELECT u.id, u.username, s.influence, s.location
        FROM users u
        INNER JOIN stats s ON s.id = u.id
        WHERE COALESCE(u.auth_type, 'normal') = 'normal'
        ORDER BY s.influence DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
        dict_cursor=True,
    )
    return [dict(r) for r in rows or []]


def fetch_active_wars(limit: int = 12) -> List[Dict[str, Any]]:
    """Active wars; supports normalized or legacy wars schema."""
    from bot_api import _wars_schema

    schema = _wars_schema()
    war_pk = schema.get("war_pk")
    atk = schema.get("attacker")
    dfn = schema.get("defender")
    if not war_pk or not atk or not dfn:
        return []
    rows = QueryHelper.fetch_all(
        f"""
        SELECT w.{war_pk} AS war_id,
               ua.username AS attacker_name,
               ud.username AS defender_name,
               w.war_type
        FROM wars w
        JOIN users ua ON ua.id = w.{atk}
        JOIN users ud ON ud.id = w.{dfn}
        WHERE w.peace_date IS NULL
        ORDER BY w.{war_pk} DESC
        LIMIT %s
        """,
        (limit,),
        dict_cursor=True,
    )
    return [dict(r) for r in rows or []]


def fetch_realm_inspector() -> Dict[str, Any]:
    nations = QueryHelper.fetch_one(
        "SELECT COUNT(*) FROM users WHERE COALESCE(auth_type, 'normal') = 'normal'"
    )
    provinces = QueryHelper.fetch_one("SELECT COUNT(*) FROM provinces")
    active_wars = 0
    try:
        from bot_api import _wars_schema

        schema = _wars_schema()
        atk, dfn = schema.get("attacker"), schema.get("defender")
        if atk and dfn:
            row = QueryHelper.fetch_one(
                "SELECT COUNT(*) FROM wars WHERE peace_date IS NULL"
            )
            active_wars = int(row[0]) if row else 0
    except Exception:
        pass
    coalitions = QueryHelper.fetch_one("SELECT COUNT(*) FROM colNames")
    members_tbl = get_coalition_members_table()
    coalition_members = 0
    if members_tbl:
        row = QueryHelper.fetch_one(f"SELECT COUNT(*) FROM {members_tbl}")
        coalition_members = int(row[0]) if row else 0
    linked_discord = QueryHelper.fetch_one(
        """
        SELECT COUNT(*) FROM users
        WHERE discord_id IS NOT NULL AND discord_id <> ''
        """
    )
    last_revenue = QueryHelper.fetch_one(
        """
        SELECT last_run FROM task_runs
        WHERE task_name = 'generate_province_revenue'
        """
    )
    return {
        "nations": int(nations[0]) if nations else 0,
        "provinces": int(provinces[0]) if provinces else 0,
        "active_wars": int(active_wars[0]) if active_wars else 0,
        "coalitions": int(coalitions[0]) if coalitions else 0,
        "coalition_members": coalition_members,
        "discord_linked": int(linked_discord[0]) if linked_discord else 0,
        "last_revenue_tick": last_revenue[0] if last_revenue else None,
    }


def fetch_world_snapshot() -> Dict[str, Any]:
    terrain = QueryHelper.fetch_all(
        """
        SELECT s.location, COUNT(*) AS cnt
        FROM stats s
        INNER JOIN users u ON u.id = s.id
        WHERE s.location IS NOT NULL AND s.location <> ''
        GROUP BY s.location
        ORDER BY cnt DESC
        LIMIT 6
        """
    )
    top_gold = QueryHelper.fetch_one(
        """
        SELECT u.username, s.gold
        FROM users u
        JOIN stats s ON s.id = u.id
        ORDER BY s.gold DESC NULLS LAST
        LIMIT 1
        """
    )
    return {
        "terrain_rows": terrain or [],
        "richest": top_gold,
    }
