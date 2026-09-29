"""Admin analytics dashboard: traffic, conversion, channels, retention, audience."""
import logging

from flask import Blueprint, render_template, request

from app_core.admin.routes import _require_admin_diag_or_session
from database import get_db_cursor
from helpers import login_required

logger = logging.getLogger(__name__)
analytics_bp = Blueprint("analytics", __name__)

_SIGNUP_DAY = "LEFT(u.date,10)::date"
_SIGNUP_OK = "u.date ~ '^\\d{4}-\\d{2}-\\d{2}' AND LEFT(u.date,10) > '1971' AND COALESCE(u.auth_type,'') <> 'bot'"
_CHANNEL = """COALESCE(u.signup_utm_source, u.signup_referrer_host,
    'heard: ' || u.signup_heard_from,
    CASE WHEN u.referred_by_user_id IS NOT NULL THEN 'referral' END,
    CASE u.auth_type WHEN 'discord' THEN 'discord login' END, 'direct/unknown')"""


def _pct(n, d):
    return f"{100.0 * n / d:.0f}%" if d else "–"


def _section(db, title, headers, sql, params=(), fmt=None):
    try:
        db.execute("SAVEPOINT an")
        db.execute(sql, params)
        rows = db.fetchall()
        db.execute("RELEASE SAVEPOINT an")
        rows = [fmt(r) for r in rows] if fmt else [list(r) for r in rows]
    except Exception as exc:
        db.execute("ROLLBACK TO SAVEPOINT an")
        logger.warning("analytics section %s failed: %s", title, exc)
        rows, headers = [["n/a"]], ["error"]
    return {"title": title, "headers": headers, "rows": rows}


@analytics_bp.route("/admin/analytics")
@login_required
def admin_analytics():
    denied = _require_admin_diag_or_session()
    if denied:
        return denied
    try:
        days = max(7, min(730, int(request.args.get("days", 30))))
    except ValueError:
        days = 30
    sections = []
    with get_db_cursor() as db:
        sections.append(_section(
            db, "Active players", ["Daily", "Weekly", "Monthly"],
            """SELECT COUNT(DISTINCT user_id) FILTER (WHERE day = CURRENT_DATE),
                      COUNT(DISTINCT user_id) FILTER (WHERE day > CURRENT_DATE - 7),
                      COUNT(DISTINCT user_id) FROM user_active_days WHERE day > CURRENT_DATE - 30"""))
        sections.append(_section(
            db, "Traffic & conversion by week", ["Week", "Unique visitors", "Page views", "Signups", "Conversion"],
            f"""WITH v AS (SELECT date_trunc('week', day)::date wk, COUNT(DISTINCT (day, visitor_hash)) uv, COUNT(*) pv
                           FROM site_visits WHERE day > CURRENT_DATE - %s GROUP BY 1),
                     s AS (SELECT date_trunc('week', {_SIGNUP_DAY})::date wk, COUNT(*) n FROM users u
                           WHERE {_SIGNUP_OK} AND {_SIGNUP_DAY} > CURRENT_DATE - %s GROUP BY 1)
                SELECT COALESCE(v.wk, s.wk), COALESCE(uv,0), COALESCE(pv,0), COALESCE(n,0)
                FROM v FULL JOIN s ON s.wk = v.wk ORDER BY 1 DESC""",
            (days, days), fmt=lambda r: [r[0], r[1], r[2], r[3], _pct(r[3], r[1])]))
        sections.append(_section(
            db, f"Signups by channel (last {days} days)", ["Channel", "Signups"],
            f"""SELECT {_CHANNEL}, COUNT(*) FROM users u WHERE {_SIGNUP_OK} AND {_SIGNUP_DAY} > CURRENT_DATE - %s
                GROUP BY 1 ORDER BY 2 DESC""", (days,)))
        sections.append(_section(
            db, f"Visits by referring site (last {days} days)", ["Site / utm_source", "Unique visitors"],
            """SELECT COALESCE(utm_source, referrer_host, 'direct'), COUNT(DISTINCT (day, visitor_hash))
               FROM site_visits WHERE day > CURRENT_DATE - %s GROUP BY 1 ORDER BY 2 DESC LIMIT 20""", (days,)))
        sections.append(_section(
            db, "\"How did you hear about us\"", ["Answer", "Signups"],
            """SELECT signup_heard_from, COUNT(*) FROM users WHERE signup_heard_from IS NOT NULL
               GROUP BY 1 ORDER BY 2 DESC"""))
        sections.append(_section(
            db, "Retention by signup month", ["Cohort", "Signups", "Day 1", "Day 7", "Day 30"],
            f"""WITH u AS (SELECT u.id, {_SIGNUP_DAY} sd FROM users u WHERE {_SIGNUP_OK} AND {_SIGNUP_DAY} >= '2026-01-01')
                SELECT to_char(sd,'YYYY-MM'), COUNT(*),
                  COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_active_days a WHERE a.user_id=u.id AND a.day >= sd+1)),
                  COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_active_days a WHERE a.user_id=u.id AND a.day >= sd+7)),
                  COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM user_active_days a WHERE a.user_id=u.id AND a.day >= sd+30)),
                  MAX(sd) FROM u GROUP BY 1 ORDER BY 1 DESC""",
            fmt=lambda r: [r[0], r[1], _pct(r[2], r[1]), _pct(r[3], r[1]), _pct(r[4], r[1])]))
        sections.append(_section(
            db, f"Visitor countries (last {days} days)", ["Country", "Unique visitors"],
            """SELECT COALESCE(country,'?'), COUNT(DISTINCT (day, visitor_hash)) FROM site_visits
               WHERE day > CURRENT_DATE - %s GROUP BY 1 ORDER BY 2 DESC LIMIT 15""", (days,)))
        sections.append(_section(
            db, "Player countries (all known)", ["Country", "Players"],
            "SELECT signup_country, COUNT(*) FROM users WHERE signup_country IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 15"))
        sections.append(_section(
            db, f"Devices (last {days} days)", ["Device", "Unique visitors"],
            """SELECT COALESCE(device,'?'), COUNT(DISTINCT (day, visitor_hash)) FROM site_visits
               WHERE day > CURRENT_DATE - %s GROUP BY 1 ORDER BY 2 DESC""", (days,)))
    return render_template("admin_analytics.html", sections=sections, days=days)
