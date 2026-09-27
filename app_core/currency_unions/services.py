"""Currency unions: nations sharing one currency.

Player suggestion 2026-09-25 (luciuskonst, "Economy tweaks/ideas laundry
list" #6). A founder creates a union with a name and a currency name; other
nations apply and the founder approves them. A nation can be in at most one
union. While a union has at least ``variables.CURRENCY_UNION_MIN_MEMBERS``
members, its members get:

* the reduced union trade fee on trades with each other
  (``app_core.market.fees``), and
* a larger bond issuance cap (``app_core.bonds.services.compute_bond_cap``).

The union page shows the members' combined and average public stats.
Service functions return ``(ok, message, flash_category)`` like
``app_core.currency.services``.
"""

from __future__ import annotations

import re

import variables

from . import repositories as repo

# Serialises every membership change of one union (join/leave/approve/kick),
# two-key advisory lock so it can't collide with the per-user single-key
# locks used elsewhere.
_LOCK_NS = 8200
_NAME_RE = re.compile(r"^[\w .,'&()\-]+$", re.UNICODE)


def _lock_union(db, union_id):
    db.execute("SELECT pg_advisory_xact_lock(%s, %s)", (_LOCK_NS, int(union_id)))


def _lock_user(db, user_id):
    db.execute("SELECT pg_advisory_xact_lock(%s)", (int(user_id),))


def _clean(text, max_len):
    text = " ".join((text or "").split())
    if not text or len(text) > max_len or not _NAME_RE.match(text):
        return None
    return text


def _username(db, user_id):
    db.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    row = db.fetchone()
    return row[0] if row else "A nation"


def is_active(member_count):
    return (member_count or 0) >= variables.CURRENCY_UNION_MIN_MEMBERS


def _safe(db, fn, default):
    """Run a read inside a savepoint so a missing table (migration not yet
    applied) can't abort the caller's whole transaction."""
    try:
        db.execute("SAVEPOINT currency_union_read")
        result = fn()
        db.execute("RELEASE SAVEPOINT currency_union_read")
        return result
    except Exception:
        try:
            db.execute("ROLLBACK TO SAVEPOINT currency_union_read")
        except Exception:
            pass
        return default


def share_active_union(db, user_a, user_b):
    """True if both nations are members of the same active union."""
    if not user_a or not user_b or user_a == user_b:
        return False
    return _safe(
        db,
        lambda: repo.same_active_union(
            db, user_a, user_b, variables.CURRENCY_UNION_MIN_MEMBERS
        ),
        False,
    )


def bond_cap_multiplier(db, user_id):
    membership = _safe(db, lambda: repo.get_membership(db, user_id), None)
    if membership and is_active(membership[4]):
        return variables.CURRENCY_UNION_BOND_CAP_MULTIPLIER
    return 1.0


def get_page_status(db, user_id):
    """Everything the /currency_unions page needs."""
    membership = repo.get_membership(db, user_id)
    unions = []
    for row in repo.list_unions(db):
        union_id, name, currency, founder_id, founder_name, members, pop, provs = row
        members = int(members or 0)
        unions.append(
            {
                "id": union_id,
                "name": name,
                "currency_name": currency,
                "founder_id": founder_id,
                "founder_name": founder_name,
                "members": members,
                "population": int(pop or 0),
                "avg_population": int(pop or 0) // members if members else 0,
                "provinces": int(provs or 0),
                "active": is_active(members),
            }
        )

    mine = None
    if membership:
        union_id, name, currency, founder_id, count = membership
        members = [
            {
                "id": r[0],
                "username": r[1],
                "population": int(r[2] or 0),
                "provinces": int(r[3] or 0),
                "joined_at": r[4],
            }
            for r in repo.get_members(db, union_id)
        ]
        total_pop = sum(m["population"] for m in members)
        total_provs = sum(m["provinces"] for m in members)
        n = len(members) or 1
        mine = {
            "id": union_id,
            "name": name,
            "currency_name": currency,
            "founder_id": founder_id,
            "is_founder": founder_id == user_id,
            "members": members,
            "member_count": len(members),
            "active": is_active(len(members)),
            "total_population": total_pop,
            "avg_population": total_pop // n,
            "total_provinces": total_provs,
            "avg_provinces": round(total_provs / n, 1),
            "applications": (
                [
                    {"id": r[0], "username": r[1], "created_at": r[2]}
                    for r in repo.get_applications(db, union_id)
                ]
                if founder_id == user_id
                else []
            ),
        }

    return {
        "mine": mine,
        "unions": unions,
        "my_applications": repo.get_my_applications(db, user_id),
        "min_members": variables.CURRENCY_UNION_MIN_MEMBERS,
        "fee": variables.TRADE_FEE_PERCENT,
        "union_fee": variables.UNION_TRADE_FEE_PERCENT,
        "bond_bonus_percent": int(
            round((variables.CURRENCY_UNION_BOND_CAP_MULTIPLIER - 1) * 100)
        ),
        "name_max": variables.CURRENCY_UNION_NAME_MAX,
        "currency_max": variables.CURRENCY_UNION_CURRENCY_MAX,
    }


def create_union(db, user_id, name_raw, currency_raw):
    _lock_user(db, user_id)
    name = _clean(name_raw, variables.CURRENCY_UNION_NAME_MAX)
    currency = _clean(currency_raw, variables.CURRENCY_UNION_CURRENCY_MAX)
    if not name:
        return (
            False,
            "Enter a union name (letters, numbers and basic punctuation).",
            "danger",
        )
    if not currency:
        return (
            False,
            "Enter a currency name (letters, numbers and basic punctuation).",
            "danger",
        )
    if repo.get_membership(db, user_id):
        return False, "You're already in a currency union. Leave it first.", "danger"
    if repo.union_name_taken(db, name):
        return False, "A currency union with that name already exists.", "danger"
    union_id = repo.insert_union(db, name, currency, user_id)
    repo.add_member(db, union_id, user_id)
    return (
        True,
        f"You founded the {name}. Other nations can now apply to join.",
        "success",
    )


def apply_to_union(db, user_id, union_id):
    _lock_user(db, user_id)
    union = repo.get_union(db, union_id)
    if not union:
        return False, "That currency union doesn't exist.", "danger"
    if repo.get_membership(db, user_id):
        return False, "You're already in a currency union. Leave it first.", "danger"
    repo.add_application(db, union_id, user_id)
    repo.insert_news(
        db,
        union[3],
        f"{_username(db, user_id)} applied to join your currency union "
        f"{union[1]}. Review it on the Currency Unions page.",
    )
    return True, f"Application sent to the {union[1]}.", "success"


def withdraw_application(db, user_id, union_id):
    if repo.delete_application(db, union_id, user_id):
        return True, "Application withdrawn.", "success"
    return False, "No application to withdraw.", "danger"


def decide_application(db, founder_id, union_id, applicant_id, approve):
    _lock_union(db, union_id)
    union = repo.get_union(db, union_id)
    if not union or union[3] != founder_id:
        return False, "Only the union's founder can review applications.", "danger"
    if not repo.delete_application(db, union_id, applicant_id):
        return False, "That application no longer exists.", "danger"
    if not approve:
        repo.insert_news(
            db, applicant_id, f"Your application to the {union[1]} was declined."
        )
        return True, "Application declined.", "success"
    _lock_user(db, applicant_id)
    if repo.get_membership(db, applicant_id):
        return False, "That nation has already joined another currency union.", "danger"
    repo.add_member(db, union_id, applicant_id)
    repo.insert_news(
        db,
        applicant_id,
        f"You joined the {union[1]} currency union. Your nation now uses the "
        f"{union[2]}.",
    )
    return True, "Member admitted.", "success"


def leave_union(db, user_id):
    membership = repo.get_membership(db, user_id)
    if not membership:
        return False, "You're not in a currency union.", "danger"
    union_id, name, _currency, founder_id, _count = membership
    _lock_union(db, union_id)
    repo.remove_member(db, user_id)
    if founder_id == user_id:
        successor = repo.oldest_other_member(db, union_id, user_id)
        if successor is None:
            repo.delete_union(db, union_id)
            return True, f"You left and the {name} was dissolved.", "success"
        repo.set_founder(db, union_id, successor)
        repo.insert_news(
            db,
            successor,
            f"{_username(db, user_id)} left the {name}. You are now its founder.",
        )
    return True, f"You left the {name}.", "success"


def kick_member(db, founder_id, union_id, member_id):
    _lock_union(db, union_id)
    union = repo.get_union(db, union_id)
    if not union or union[3] != founder_id:
        return False, "Only the union's founder can remove members.", "danger"
    if member_id == founder_id:
        return False, "Use Leave to leave your own union.", "danger"
    if not repo.is_member_of(db, union_id, member_id):
        return False, "That nation isn't in your union.", "danger"
    repo.remove_member(db, member_id)
    repo.insert_news(
        db, member_id, f"You were removed from the {union[1]} currency union."
    )
    return True, "Member removed.", "success"
