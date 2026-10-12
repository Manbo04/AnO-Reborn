"""World Assembly effect helpers shared by influence, market and the assembly tick.

Sanction severity (kept deliberately mild; nation-to-nation trade agreements are
never blocked by sanctions):
  minor   -10% influence
  regular -25% influence, no public market trading
  major   -40% influence, no public market trading
A commend resolution gives +5% influence (several commends do not stack).
Legacy sanctions (NULL severity) behave as 'regular'.
"""

SANCTION_INFLUENCE = {"minor": 0.90, "regular": 0.75, "major": 0.60}
COMMEND_INFLUENCE = 1.05
SEVERITIES = ("minor", "regular", "major")
DURATIONS = {"7": 7, "14": 14, "30": 30, "90": 90, "indefinite": 0}
DEFAULT_DURATION_DAYS = 14

# SQL predicate (on assembly_effects) for effects that block the public market.
MARKET_BLOCK_SQL = (
    " effect_type = 'sanction' AND COALESCE(severity, 'regular') IN ('regular', 'major')"
    " AND active = TRUE AND (expires_at IS NULL OR expires_at > NOW())"
)


def influence_multipliers(db, user_ids):
    """Return {user_id: multiplier} for nations with an active sanction/commend."""
    ids = [int(u) for u in user_ids]
    if not ids:
        return {}
    db.execute(
        "SELECT target_nation_id, effect_type, COALESCE(severity, 'regular') FROM assembly_effects"
        " WHERE target_nation_id = ANY(%s) AND effect_type IN ('sanction', 'commend')"
        " AND active = TRUE AND (expires_at IS NULL OR expires_at > NOW())",
        (ids,),
    )
    worst, commended = {}, set()
    for row in db.fetchall():
        nid, etype, sev = (row[0], row[1], row[2]) if not isinstance(row, dict) else (
            row["target_nation_id"], row["effect_type"], row["coalesce"])
        if etype == "commend":
            commended.add(nid)
        else:
            m = SANCTION_INFLUENCE.get(sev, SANCTION_INFLUENCE["regular"])
            worst[nid] = min(m, worst.get(nid, 1.0))
    out = {}
    for nid in set(worst) | commended:
        out[nid] = worst.get(nid, 1.0) * (COMMEND_INFLUENCE if nid in commended else 1.0)
    return out
