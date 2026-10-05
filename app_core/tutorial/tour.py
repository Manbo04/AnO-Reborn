"""Command Briefing: the hands-on, in-game guided tour for new nations.

Replaces the old read-and-quiz /tutorial course (Dede, 2026-10-05). Instead of
lessons on a separate page, a mission card follows the player around the real
game and every objective is a real action. Progress is derived from the
player's actual game state wherever possible (buildings owned, soldiers
recruited), so it can't drift out of sync with what the player did; the few
"visit this page" objectives are recorded when the page reports the visit.

Storage reuses the existing stats columns: completed step indices live in
stats.tutorial_chapters_claimed (claimed atomically, which also pays out
CHAPTER_REWARDS[idx] exactly once) and graduation in
stats.tutorial_graduated_at (pays GRADUATION_REWARD once).
"""

from __future__ import annotations

from app_core.economy.biome_buildings import BIOME_MINES

POWER_BUILDINGS = (
    "coal_burners",
    "oil_burners",
    "hydro_dams",
    "nuclear_reactors",
    "solar_fields",
    "wind_farms",
    "geothermal_plants",
)
ALL_EXTRACTORS = tuple(sorted({m for mines in BIOME_MINES.values() for m in mines}))

# kind: "visit" (page visit reported by the client) or "state" (verified from DB).
# `target` is a CSS selector the client spotlights on the matching page.
STEPS: list[dict] = [
    {
        "key": "survey",
        "kind": "visit",
        "title": "Survey your nation",
        "brief": "This is your nation's command screen: population, income and how your people feel. Check it whenever you log in.",
        "path": "/country",
        "target": "main, .templatediv",
    },
    {
        "key": "capital",
        "kind": "visit",
        "title": "Inspect your capital",
        "brief": "Provinces are where everything gets built. Open your capital to see its land, population and buildings.",
        "path": "/province/",
        "target": "main, .templatediv",
    },
    {
        "key": "power",
        "kind": "state",
        "title": "Power the grid",
        "brief": "Buildings need electricity to work. Build 1 Coal Power Plant: type 1 in the amount box and press Buy.",
        "path": "/province/",
        "target": "button[formaction^='/buy/coal_burners/']",
    },
    {
        "key": "farms",
        "kind": "state",
        "title": "Feed your people",
        "brief": "Hungry citizens stop growing. Build 1 Farm so your provinces produce rations.",
        "path": "/province/",
        "target": "button[formaction^='/buy/farms/']",
    },
    {
        "key": "stores",
        "kind": "state",
        "title": "Open for business",
        "brief": "Consumer goods keep citizens happy and taxable. Build 1 General Store.",
        "path": "/province/",
        "target": "button[formaction^='/buy/general_stores/']",
    },
    {
        "key": "extract",
        "kind": "state",
        "title": "Tap your land's wealth",
        "brief": "Your biome has its own raw resources. Build 1 mine, lumber mill or pumpjack from your province's raw resources section.",
        "path": "/province/",
        "target": "button[formaction*='_mines/'], button[formaction^='/buy/lumber_mills/'], button[formaction^='/buy/pumpjacks/']",
    },
    {
        "key": "market",
        "kind": "visit",
        "title": "Visit the market",
        "brief": "Every price here is set by real players. Sell what you produce and buy what your land lacks.",
        "path": "/market",
        "target": "main, .templatediv",
    },
    {
        "key": "army",
        "kind": "state",
        "title": "Raise an army",
        "brief": "Other nations will test you. Recruit at least 1 soldier so you aren't defenseless.",
        "path": "/military",
        "target": "button[formaction^='/military/buy/soldiers']",
    },
    {
        "key": "allies",
        "kind": "visit",
        "title": "Find allies",
        "brief": "Coalitions share banks, treaties and wars. Browse them and find one that fits your nation.",
        "path": "/coalitions",
        "target": "main, .templatediv",
    },
]
STEP_INDEX = {s["key"]: i for i, s in enumerate(STEPS)}

# The tour is only for nations founded after it launched. Older nations may have
# claimed the old quiz chapters (same stats columns) and must never get the
# tour card or its rewards (Dede, 2026-10-05).
TOUR_LAUNCH = "2026-10-04"


def is_tour_eligible(db, user_id: int) -> bool:
    """True only for nations founded on/after TOUR_LAUNCH (users.date is ISO
    YYYY-MM-DD, written by every signup path)."""
    import datetime

    db.execute("SELECT date FROM users WHERE id = %s", (user_id,))
    row = db.fetchone()
    raw = (row["date"] if isinstance(row, dict) else row[0]) if row else None
    try:
        founded = (
            raw if isinstance(raw, datetime.date) else datetime.date.fromisoformat(str(raw).strip()[:10])
        )
    except (TypeError, ValueError):
        return False
    return founded >= datetime.date.fromisoformat(TOUR_LAUNCH)


def _game_facts(db, user_id: int) -> dict:
    """One round-trip-light snapshot of everything the state steps check."""
    db.execute(
        """
        SELECT bd.name AS name, COALESCE(SUM(ub.quantity), 0) AS qty
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s
        GROUP BY bd.name
        """,
        (user_id,),
    )
    buildings = {}
    for row in db.fetchall() or []:
        name, qty = (row["name"], row["qty"]) if isinstance(row, dict) else (row[0], row[1])
        buildings[name] = int(qty or 0)

    db.execute(
        """
        SELECT COALESCE(SUM(um.quantity), 0) AS qty
        FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE um.user_id = %s AND ud.name = 'soldiers'
        """,
        (user_id,),
    )
    row = db.fetchone()
    soldiers = int((list(row.values())[0] if isinstance(row, dict) else row[0]) or 0) if row else 0

    db.execute(
        "SELECT id FROM provinces WHERE userId = %s ORDER BY is_capital DESC NULLS LAST, id LIMIT 1",
        (user_id,),
    )
    row = db.fetchone()
    capital = (row["id"] if isinstance(row, dict) else row[0]) if row else None
    return {"buildings": buildings, "soldiers": soldiers, "capital_id": capital}


def _state_step_done(key: str, facts: dict) -> bool:
    b = facts["buildings"]
    if key == "power":
        return any(b.get(n, 0) > 0 for n in POWER_BUILDINGS)
    if key == "farms":
        return b.get("farms", 0) > 0
    if key == "stores":
        return b.get("general_stores", 0) > 0
    if key == "extract":
        return any(b.get(n, 0) > 0 for n in ALL_EXTRACTORS)
    if key == "army":
        return facts["soldiers"] > 0
    return False


def compute_tour(db, user_id: int, *, visited: str | None = None) -> dict:
    """Return the tour state, completing (and rewarding) any step whose
    condition is now met. `visited` is a step key the client says the player
    just looked at; it only counts for "visit" steps."""
    from app_core.tutorial.routes import (
        _apply_rewards,
        _claim_chapter,
        _claim_graduation,
    )
    from app_core.tutorial.rewards import GRADUATION_REWARD

    if not is_tour_eligible(db, user_id):
        return {"ok": True, "eligible": False, "graduated": True, "steps": [], "current": None,
                "newly_completed": [], "graduation_reward": None}

    db.execute(
        "SELECT tutorial_chapters_claimed, tutorial_graduated_at FROM stats WHERE id = %s",
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return {"ok": False}
    claimed_raw, graduated_at = (
        (row["tutorial_chapters_claimed"], row["tutorial_graduated_at"])
        if isinstance(row, dict)
        else (row[0], row[1])
    )
    claimed = set(claimed_raw or [])
    facts = _game_facts(db, user_id)

    newly: list[dict] = []
    for i, step in enumerate(STEPS):
        if i in claimed:
            continue
        met = (
            step["kind"] == "visit" and visited == step["key"]
        ) or (step["kind"] == "state" and _state_step_done(step["key"], facts))
        if not met:
            continue
        reward = _claim_chapter(db, user_id, i)
        if reward is None:  # a concurrent request already completed it
            claimed.add(i)
            continue
        granted = _apply_rewards(db, user_id, reward) if reward else {}
        claimed.add(i)
        newly.append({"key": step["key"], "title": step["title"], "reward": granted})

    graduation = None
    if graduated_at is None and all(i in claimed for i in range(len(STEPS))):
        if _claim_graduation(db, user_id):
            graduation = _apply_rewards(db, user_id, GRADUATION_REWARD)
        graduated_at = True

    from app_core.tutorial.rewards import CHAPTER_REWARDS

    capital_href = f"/province/{facts['capital_id']}" if facts["capital_id"] else "/provinces"
    steps_out = []
    for i, step in enumerate(STEPS):
        href = capital_href if step["path"] == "/province/" else step["path"]
        steps_out.append(
            {
                "key": step["key"],
                "kind": step["kind"],
                "title": step["title"],
                "brief": step["brief"],
                "href": href,
                "match": step["path"],
                "target": step["target"],
                "reward": CHAPTER_REWARDS.get(i, {}),
                "done": i in claimed,
            }
        )
    current = next((i for i, s in enumerate(steps_out) if not s["done"]), None)
    if newly:
        try:
            from database import invalidate_user_cache

            invalidate_user_cache(user_id)
        except Exception:
            pass
    return {
        "ok": True,
        "eligible": True,
        "steps": steps_out,
        "current": current,
        "completed": len([s for s in steps_out if s["done"]]),
        "total": len(STEPS),
        "graduated": bool(graduated_at),
        "newly_completed": newly,
        "graduation_reward": graduation,
        "final_reward": GRADUATION_REWARD,
    }
