"""Daily tick for the player-to-player Bonds market (app_core/bonds/):
garnishes each active bond's daily interest from the issuer straight to the
lender, optionally amortizes principal into escrow for auto_escrow bonds,
force-defaults a bond after too many missed interest payments instead of
waiting for a maturity cliff, resolves bonds that reach maturity, and keeps
collecting any unpaid shortfall from a defaulted issuer afterwards so that
defaulting is never free money for the borrower.

Also sends the bond notifications players asked for (Kurai, #suggestions):
one daily summary per player of interest paid/received and garnishment,
an immediate notice to the issuer, the lender AND the issuer's coalition
leadership (leader/deputies/banker) whenever an issuer misses a payment
or defaults, and -- for members their coalition has insured (see
coalition_bond_insurance, migration 0082) -- pays the lender's default
shortfall out of the coalition bank, then collects that amount back from
the defaulter into the bank.

Same standalone-tick shape as loan_interest.py / disasters.py: its own
advisory lock and task_runs row.
"""
from datetime import datetime, timezone

import variables

from app_core.game_ticks.common import should_skip_task, handle_exception, log_verbose
from app_core.game_ticks.locks import try_pg_advisory_lock, release_pg_advisory_lock

TASK_NAME = "bond_tick"
ADVISORY_LOCK_ID = 9014


def compute_daily_bond_charge(principal, daily_interest_rate, auto_escrow, term_days, available_gold):
    """Pure helper (no DB). Given a bond's terms and the issuer's currently
    available gold, returns (interest_garnished, escrow_contribution,
    missed_interest: bool).

    Interest is always prioritized over the optional principal escrow
    contribution -- a lender should never go unpaid on interest because the
    issuer chose to auto-escrow principal too.
    """
    interest_due = principal * daily_interest_rate
    principal_installment_due = (principal / term_days) if (auto_escrow and term_days > 0) else 0

    interest_garnished = min(interest_due, available_gold)
    remaining_gold = available_gold - interest_garnished
    escrow_garnished = min(principal_installment_due, remaining_gold)

    missed_interest = interest_garnished < interest_due
    return interest_garnished, escrow_garnished, missed_interest


def compute_maturity_settlement(principal, escrowed_principal, available_gold):
    """Pure helper: at maturity, the issuer owes whatever principal hasn't
    already been escrowed, as a lump sum. Returns (garnished_now, shortfall)
    -- shortfall > 0 means this bond defaults for that remaining amount."""
    remaining_due = max(0.0, principal - escrowed_principal)
    garnished = min(remaining_due, available_gold)
    shortfall = remaining_due - garnished
    return garnished, shortfall


def _money(amount):
    return f"${amount:,.0f}"


class _BondNotes:
    """Collects this tick's bond news so each player gets ONE daily summary
    line instead of a notification per bond, plus the individual
    missed-payment/default alerts. Written to the same `news` table every
    other in-game notification uses (the topbar bell + country page)."""

    def __init__(self):
        self.totals = {}   # user_id -> {"received","paid","collected","garnished"}
        self.alerts = []   # (user_id, message)
        self._names = {}

    def add(self, user_id, key, amount):
        if not user_id or amount <= 0:
            return
        t = self.totals.setdefault(user_id, {"received": 0.0, "paid": 0.0, "collected": 0.0, "garnished": 0.0})
        t[key] += amount

    def alert(self, user_ids, message):
        seen = set()
        for uid in user_ids:
            if uid and uid not in seen:
                seen.add(uid)
                self.alerts.append((uid, message))

    def name(self, db, user_id):
        if user_id not in self._names:
            db.execute("SELECT username FROM users WHERE id=%s", (user_id,))
            row = db.fetchone()
            self._names[user_id] = row[0] if row else f"Nation #{user_id}"
        return self._names[user_id]

    def flush(self, db):
        for uid, t in self.totals.items():
            parts = []
            if t["received"] > 0:
                parts.append(f"received {_money(t['received'])} in interest")
            if t["paid"] > 0:
                parts.append(f"paid {_money(t['paid'])} in interest")
            if t["collected"] > 0:
                parts.append(f"collected {_money(t['collected'])} from defaulted borrowers")
            if t["garnished"] > 0:
                parts.append(f"had {_money(t['garnished'])} garnished toward defaulted bonds")
            if parts:
                self.alerts.append((uid, "Bonds today: you " + ", ".join(parts) + "."))
        for uid, message in self.alerts:
            _insert_news(db, uid, message)


def _insert_news(db, user_id, message):
    try:
        db.execute("SAVEPOINT bond_news")
        db.execute("INSERT INTO news (destination_id, message) VALUES (%s, %s)", (user_id, message))
        db.execute("RELEASE SAVEPOINT bond_news")
    except Exception:
        db.execute("ROLLBACK TO SAVEPOINT bond_news")


def _issuer_coalition(db, user_id):
    """(coalition_id, [leader/deputy/banker user ids]) for the issuer's
    current coalition, or (None, [])."""
    from database import get_coalition_members_table

    tbl = get_coalition_members_table()
    if tbl not in ("coalitions_legacy", "coalitions"):
        return None, []
    db.execute(f"SELECT colid FROM {tbl} WHERE userid=%s", (user_id,))
    row = db.fetchone()
    if not row or not row[0]:
        return None, []
    coalition_id = row[0]
    db.execute(
        f"SELECT userid FROM {tbl} WHERE colid=%s AND role IN ('leader', 'deputy_leader', 'banker')",
        (coalition_id,),
    )
    return coalition_id, [r[0] for r in db.fetchall() if r[0] != user_id]


def _apply_coalition_insurance(db, bond_id, issuer_id, lender_id, shortfall):
    """If the issuer's coalition insures them, pay the lender as much of the
    default shortfall as the coalition bank's money covers. Returns
    (coalition_id, paid) -- paid is 0 when uninsured or the bank is empty.
    The caller records `paid` as insurer_owed so the defaulter repays the
    bank, not the lender, for the covered part."""
    coalition_id, _ = _issuer_coalition(db, issuer_id)
    if not coalition_id:
        return None, 0
    db.execute(
        "SELECT 1 FROM coalition_bond_insurance WHERE coalition_id=%s AND user_id=%s",
        (coalition_id, issuer_id),
    )
    if not db.fetchone():
        return None, 0
    db.execute("SELECT money FROM colBanks WHERE colId=%s FOR UPDATE", (coalition_id,))
    row = db.fetchone()
    bank_money = int(row[0] or 0) if row else 0
    paid = int(min(bank_money, shortfall))
    if paid <= 0:
        return coalition_id, 0
    db.execute("UPDATE colBanks SET money = money - %s WHERE colId=%s", (paid, coalition_id))
    db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (paid, lender_id))
    log_verbose(
        f"BOND_INSURANCE | bond={bond_id} coalition={coalition_id} issuer={issuer_id} "
        f"lender={lender_id} paid={paid}"
    )
    return coalition_id, paid


def run_bond_tick():
    from database import get_db_connection

    with get_db_connection() as conn:
        if not try_pg_advisory_lock(conn, ADVISORY_LOCK_ID, TASK_NAME):
            return

        try:
            db = conn.cursor()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, NULL) "
                "ON CONFLICT DO NOTHING",
                (TASK_NAME,),
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s FOR UPDATE",
                (TASK_NAME,),
            )
            row = db.fetchone()
            if should_skip_task(row, TASK_NAME):
                return

            notes = _BondNotes()
            _process_active_bonds(db, notes)
            _process_defaulted_shortfalls(db, notes)
            notes.flush(db)

            db.execute(
                "UPDATE task_runs SET last_run = now() WHERE task_name=%s",
                (TASK_NAME,),
            )
        except Exception as e:
            handle_exception(e, TASK_NAME)
            raise
        finally:
            try:
                release_pg_advisory_lock(conn, ADVISORY_LOCK_ID)
            except Exception:
                pass


def _process_active_bonds(db, notes):
    db.execute(
        """
        SELECT b.id, b.issuer_id, b.lender_id, b.principal, b.daily_interest_rate,
               b.term_days, b.auto_escrow, b.escrowed_principal, b.default_strikes,
               b.matures_at, s.gold
        FROM bonds b
        JOIN stats s ON s.id = b.issuer_id
        WHERE b.status = 'active'
        """
    )
    bonds = db.fetchall()
    now = datetime.now(timezone.utc)
    # s.gold above is read once for all bonds. An issuer with several active
    # bonds must be charged against what's LEFT after the earlier ones --
    # otherwise each bond garnishes the same gold, GREATEST(0, ...) clamps
    # the issuer at zero, and the lenders are still credited in full, which
    # created gold from nothing.
    spent = {}

    for (bond_id, issuer_id, lender_id, principal, daily_interest_rate, term_days,
         auto_escrow, escrowed_principal, default_strikes, matures_at, gold) in bonds:
        principal = float(principal)
        daily_interest_rate = float(daily_interest_rate)
        escrowed_principal = float(escrowed_principal)
        gold = max(0.0, (float(gold) if gold is not None else 0.0) - spent.get(issuer_id, 0.0))

        interest_garnished, escrow_garnished, missed_interest = compute_daily_bond_charge(
            principal, daily_interest_rate, auto_escrow, term_days, gold
        )
        total_garnished = interest_garnished + escrow_garnished
        spent[issuer_id] = spent.get(issuer_id, 0.0) + total_garnished

        if total_garnished > 0:
            db.execute(
                "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                (total_garnished, issuer_id),
            )
        if interest_garnished > 0:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (interest_garnished, lender_id),
            )
        notes.add(lender_id, "received", interest_garnished)
        notes.add(issuer_id, "paid", interest_garnished)

        new_escrowed = escrowed_principal + escrow_garnished
        new_strikes = default_strikes + 1 if missed_interest else 0

        matured = matures_at is not None and now >= matures_at
        force_defaulted = new_strikes >= variables.BOND_MAX_DEFAULT_STRIKES

        if not matured and not force_defaulted:
            db.execute(
                """
                UPDATE bonds
                SET escrowed_principal = %s, default_strikes = %s, last_tick_at = NOW()
                WHERE id = %s
                """,
                (new_escrowed, new_strikes, bond_id),
            )
            log_verbose(
                f"BOND_TICK | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"interest={interest_garnished:.2f} escrow+={escrow_garnished:.2f} "
                f"strikes={new_strikes}"
            )
            if missed_interest:
                _alert_missed_payment(
                    db, notes, bond_id, issuer_id, lender_id,
                    principal * daily_interest_rate - interest_garnished, new_strikes,
                )
            continue

        # Reload gold post-garnish for the lump-sum settlement below (the
        # interest/escrow UPDATE above already spent some of it).
        remaining_gold = max(0.0, gold - total_garnished)
        lump_garnished, shortfall = compute_maturity_settlement(principal, new_escrowed, remaining_gold)

        if lump_garnished > 0:
            db.execute(
                "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                (lump_garnished, issuer_id),
            )
            spent[issuer_id] = spent.get(issuer_id, 0.0) + lump_garnished
        payout_to_lender = new_escrowed + lump_garnished
        if payout_to_lender > 0:
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (payout_to_lender, lender_id),
            )

        if shortfall > 0:
            # Force-defaulted (too many missed interest payments) or
            # matured without enough gold to cover the remaining principal
            # -- either way, the unpaid amount becomes garnishment_owed,
            # which _process_defaulted_shortfalls keeps collecting from the
            # issuer going forward instead of forgiving it. This is what
            # makes a default cost the issuer something real rather than
            # being free money. If the issuer's coalition insures them, the
            # bank covers the lender now and the covered part is owed to the
            # bank instead (insurer_owed).
            insurer_id, insured_paid = _apply_coalition_insurance(
                db, bond_id, issuer_id, lender_id, shortfall
            )
            db.execute(
                """
                UPDATE bonds
                SET status = 'defaulted', escrowed_principal = 0, default_strikes = %s,
                    garnishment_owed = %s, insurer_coalition_id = %s, insurer_owed = %s,
                    insurance_paid = %s, resolved_at = NOW(), last_tick_at = NOW()
                WHERE id = %s
                """,
                (new_strikes, shortfall - insured_paid, insurer_id if insured_paid > 0 else None,
                 insured_paid, insured_paid, bond_id),
            )
            log_verbose(
                f"BOND_DEFAULT | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"paid_out={payout_to_lender:.2f} shortfall={shortfall:.2f} insured={insured_paid}"
            )
            _alert_default(db, notes, bond_id, issuer_id, lender_id, shortfall, insured_paid)
        else:
            db.execute(
                """
                UPDATE bonds
                SET status = 'repaid', escrowed_principal = 0, default_strikes = %s,
                    resolved_at = NOW(), last_tick_at = NOW()
                WHERE id = %s
                """,
                (new_strikes, bond_id),
            )
            log_verbose(
                f"BOND_REPAID | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"paid_out={payout_to_lender:.2f}"
            )
            notes.alert(
                [lender_id],
                f"Bond #{bond_id} from {notes.name(db, issuer_id)} matured and was repaid in full "
                f"({_money(payout_to_lender)} principal returned).",
            )
            notes.alert(
                [issuer_id],
                f"Your bond #{bond_id} to {notes.name(db, lender_id)} matured and is fully repaid.",
            )


def _alert_missed_payment(db, notes, bond_id, issuer_id, lender_id, unpaid, strikes):
    issuer = notes.name(db, issuer_id)
    lender = notes.name(db, lender_id)
    left = variables.BOND_MAX_DEFAULT_STRIKES - strikes
    warn = f"{left} more missed payment{'s' if left != 1 else ''} and it defaults"
    notes.alert(
        [issuer_id],
        f"You missed {_money(unpaid)} of today's interest on bond #{bond_id} to {lender} "
        f"(not enough gold). {warn}.",
    )
    notes.alert(
        [lender_id],
        f"{issuer} missed {_money(unpaid)} of today's interest on your bond #{bond_id}. {warn}.",
    )
    _, officers = _issuer_coalition(db, issuer_id)
    notes.alert(
        [o for o in officers if o != lender_id],
        f"Coalition member {issuer} missed {_money(unpaid)} of interest on bond #{bond_id} "
        f"to {lender}. {warn}.",
    )


def _alert_default(db, notes, bond_id, issuer_id, lender_id, shortfall, insured_paid):
    issuer = notes.name(db, issuer_id)
    lender = notes.name(db, lender_id)
    still_owed = shortfall - insured_paid
    covered = (
        f" Your coalition's bond insurance paid {lender} {_money(insured_paid)}, which you now owe "
        f"your coalition bank instead." if insured_paid > 0 else ""
    )
    notes.alert(
        [issuer_id],
        f"You defaulted on bond #{bond_id} to {lender}, owing {_money(shortfall)}.{covered} "
        f"The debt will be garnished from your gold daily until it's paid.",
    )
    lender_msg = f"{issuer} defaulted on your bond #{bond_id}, short {_money(shortfall)}."
    if insured_paid > 0:
        lender_msg += f" Their coalition's insurance paid you {_money(insured_paid)}."
    if still_owed > 0:
        lender_msg += f" The remaining {_money(still_owed)} will be garnished from them daily."
    notes.alert([lender_id], lender_msg)

    _, officers = _issuer_coalition(db, issuer_id)
    officer_msg = (
        f"Coalition member {issuer} defaulted on bond #{bond_id} to {lender}, short {_money(shortfall)}."
    )
    if insured_paid > 0:
        officer_msg += (
            f" Bond insurance paid {_money(insured_paid)} from the coalition bank; it will be "
            f"collected back from {issuer} daily."
        )
    notes.alert([o for o in officers if o != lender_id], officer_msg)


def _process_defaulted_shortfalls(db, notes):
    """Keeps garnishing a defaulted issuer's gold, daily, toward the lender
    they stiffed -- until garnishment_owed reaches zero. Without this, a
    default that happened to leave a shortfall would just write it off,
    which is exactly the "free money on default" outcome this feature
    needs to avoid. The lender is paid back first; after that, anything
    the issuer's coalition insurance covered (insurer_owed) is collected
    into that coalition's bank."""
    db.execute(
        """
        SELECT b.id, b.issuer_id, b.lender_id, b.garnishment_owed,
               b.insurer_coalition_id, b.insurer_owed, s.gold
        FROM bonds b
        JOIN stats s ON s.id = b.issuer_id
        WHERE b.status = 'defaulted' AND b.lender_id IS NOT NULL
          AND (b.garnishment_owed > 0 OR b.insurer_owed > 0)
        ORDER BY b.id
        """
    )
    rows = db.fetchall()
    # Several defaulted bonds can share an issuer -- track gold spent
    # within this tick so each later bond sees what's actually left.
    spent = {}

    for bond_id, issuer_id, lender_id, garnishment_owed, insurer_id, insurer_owed, gold in rows:
        garnishment_owed = float(garnishment_owed or 0)
        insurer_owed = float(insurer_owed or 0)
        gold = max(0.0, (float(gold) if gold is not None else 0.0) - spent.get(issuer_id, 0.0))

        to_lender = min(garnishment_owed, gold)
        if to_lender > 0:
            db.execute(
                "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                (to_lender, issuer_id),
            )
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (to_lender, lender_id),
            )
            db.execute(
                "UPDATE bonds SET garnishment_owed = garnishment_owed - %s, last_tick_at = NOW() WHERE id = %s",
                (to_lender, bond_id),
            )
            spent[issuer_id] = spent.get(issuer_id, 0.0) + to_lender
            notes.add(lender_id, "collected", to_lender)
            notes.add(issuer_id, "garnished", to_lender)
            log_verbose(
                f"BOND_GARNISHMENT | bond={bond_id} issuer={issuer_id} lender={lender_id} "
                f"collected={to_lender:.2f} remaining={garnishment_owed - to_lender:.2f}"
            )

        # colBanks.money is a whole-number column, so collect whole dollars.
        to_bank = int(min(insurer_owed, gold - to_lender))
        if insurer_id and to_bank > 0:
            db.execute(
                "UPDATE colBanks SET money = money + %s WHERE colId = %s RETURNING colId",
                (to_bank, insurer_id),
            )
            if db.fetchone():
                db.execute(
                    "UPDATE stats SET gold = GREATEST(0, gold - %s) WHERE id = %s",
                    (to_bank, issuer_id),
                )
                remaining = insurer_owed - to_bank
                db.execute(
                    "UPDATE bonds SET insurer_owed = %s, last_tick_at = NOW() WHERE id = %s",
                    (remaining if remaining >= 1 else 0, bond_id),
                )
                spent[issuer_id] = spent.get(issuer_id, 0.0) + to_bank
                notes.add(issuer_id, "garnished", to_bank)
                log_verbose(
                    f"BOND_INSURANCE_RECOVERY | bond={bond_id} issuer={issuer_id} "
                    f"coalition={insurer_id} collected={to_bank} remaining={remaining:.2f}"
                )
