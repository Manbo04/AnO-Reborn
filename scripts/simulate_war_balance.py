"""War-balance check: master (live) vs the current battle math.

An even war is two identical Balanced armies. Both sides spend action points
as fast as the rules allow (3 AP per attack, +1 per branch per hour, start 6,
cap 12) and send every unit that domain can field. Master morale starts at
100; the new clock starts at MORALE_START (150). The war ends when either
side hits 0. Casualties stick.

Master is the live formula: score = uniform(1, 5) + count/150 + the old flat
counter bonuses, morale max(1, raw) capped at 200, loser losses up to 50%.

    python3 scripts/simulate_war_balance.py
"""

from __future__ import annotations

import random
import sys

from attack_scripts import combat_helpers as ch
from app_core.bots.profiles import army_for_strength
from units import Units

DOMAINS = ("ground", "air", "naval")
DEFEND = {
    "ground": ("soldiers", "tanks", "artillery"),
    "air": ("fighters", "bombers", "apaches"),
    "naval": ("destroyers", "cruisers", "submarines"),
}
ATTACK = {
    "ground": ("soldiers", "tanks", "artillery", "apaches"),
    "air": ("fighters", "bombers", "apaches"),
    "naval": ("destroyers", "cruisers", "submarines"),
}
# Live master counter: bonus += MULT * amount, then calculate_bonuses
# divides by 100 and by the target's share of the enemy force.
MASTER_COUNTER = {
    ("soldiers", "tanks"): 3.0,
    ("soldiers", "apaches"): 2.0,
    ("tanks", "artillery"): 6.0,
    ("artillery", "soldiers"): 2.0,
    ("bombers", "soldiers"): 2.0,
    ("bombers", "apaches"): 2.0,
    ("bombers", "destroyers"): 2.0,
    ("bombers", "submarines"): 2.0,
    ("fighters", "bombers"): 4.0,
    ("fighters", "apaches"): 3.0,
    ("apaches", "soldiers"): 1.0,
    ("apaches", "tanks"): 1.0,
    ("destroyers", "submarines"): 1.6,
    ("cruisers", "destroyers"): 0.3,
    ("cruisers", "fighters"): 0.1,
    ("cruisers", "apaches"): 0.4,
    ("submarines", "cruisers"): 0.2,
}
MASTER_LOSER_PER = 0.05
MASTER_LOSER_CAP = 0.50
MASTER_WINNER_PER = 0.04
MASTER_WINNER_CAP = 0.30


def _pick(army, names):
    return {u: int(army.get(u, 0) or 0) for u in names if int(army.get(u, 0) or 0) > 0}


def _side(units, uid=1):
    u = Units(uid, selected_units=dict(units), selected_units_list=list(units))
    u._unusable_units_cache = set()
    u.support_bombers = 0
    u.war_id = None
    return u


def master_bonus(att, den, rng):
    total = sum(den.values()) + 1
    bonus = 0.0
    for au, ac in att.items():
        for du, dc in den.items():
            if (au, du) == ("bombers", "tanks"):
                mult = rng.randint(2, 6)
            else:
                mult = MASTER_COUNTER.get((au, du), 0.0)
            if mult and ac and dc:
                bonus += (mult * ac) * (dc / total) / 100.0
    return bonus


def master_scores(att, den, rng):
    a = rng.uniform(1, 5) + sum(att.values()) / 150.0 + master_bonus(att, den, rng)
    d = rng.uniform(1, 5) + sum(den.values()) / 150.0 + master_bonus(den, att, rng)
    if sum(att.values()) == 0:
        a = 0.0
    if sum(den.values()) == 0:
        d = 0.0
    return a, d


def new_scores(att, den, rng, suppress=None, support_bombers=0, defender_fighters=0):
    a = _side(att, 1)
    d = _side(den, 2)
    aa, da, ab, db, _ = ch.compute_engagement_metrics(a, d)
    if suppress:
        pen = ch.suppression_penalty(den, suppress)
        da *= 1.0 - pen
        db *= 1.0 - pen
    if support_bombers:
        sup, _, _, _ = ch.compute_air_support(
            support_bombers, den, defender_fighters, aa + ab, rng=rng
        )
        ab += sup
    aa, ab, da, db = ch.apply_combat_modifiers(
        aa,
        ab,
        da,
        db,
        entrenchment_level=0,
        attacker_intel=0,
        is_ground=False,
        entrenchment_pierce=0.0,
    )
    ac = ch.battle_roll(aa + ab, rng)
    dc = ch.battle_roll(da + db, rng)
    ac, dc = ch.zero_out_empty_side(ac, dc, aa, da)
    return ac, dc


def _morale_master(loser, attacker, defender, winner_is_defender, win_type):
    a_s = ch.compute_strength(attacker)
    d_s = ch.compute_strength(defender)
    w_s = d_s if winner_is_defender else a_s
    adv = w_s / (a_s + d_s + 1e-9)
    base = ch.compute_strength(loser)
    delta = int(round(base * adv * win_type * 0.1))
    return max(1, min(200, delta))


def _apply_cas(units, pairs):
    for name, n in pairs:
        if name in units:
            units[name] = max(0, units[name] - int(n))


def resolve(att, den, rng, system, suppress=None):
    """Return (defender_wins, win_type, winner_cas, att_pairs, def_pairs) with att as the attacker."""
    if system == "master":
        ac, dc = master_scores(att, den, rng)
        if dc >= ac:
            win_type = 5.0 if sum(att.values()) == 0 else (dc / ac if ac else 5.0)
            w_cas = 0.0 if sum(att.values()) == 0 else ((1 + ac) / dc if dc else 0.0)
            defender_wins = True
        else:
            win_type = 5.0 if sum(den.values()) == 0 else (ac / dc if dc else 5.0)
            w_cas = 0.0 if sum(den.values()) == 0 else ((1 + dc) / ac if ac else 0.0)
            defender_wins = False

        # casualties with master caps
        def cas(sent_map, per, cap, frac_base, lo, hi, is_loser_empty_skip=False):
            out = []
            for u, n in sent_map.items():
                if n <= 0:
                    continue
                frac = min(cap, per * frac_base)
                lost = min(n, max(1, round(n * frac * rng.uniform(lo, hi))))
                out.append((u, lost))
            return out

        if defender_wins:
            # attacker is loser, defender is winner
            a_pairs = cas(att, MASTER_LOSER_PER, MASTER_LOSER_CAP, win_type, 0.8, 1.2)
            d_pairs = cas(den, MASTER_WINNER_PER, MASTER_WINNER_CAP, w_cas, 0.7, 1.3)
        else:
            a_pairs = cas(att, MASTER_WINNER_PER, MASTER_WINNER_CAP, w_cas, 0.7, 1.3)
            d_pairs = cas(den, MASTER_LOSER_PER, MASTER_LOSER_CAP, win_type, 0.8, 1.2)
        return defender_wins, win_type, a_pairs, d_pairs
    ac, dc = new_scores(att, den, rng, suppress=suppress)
    defender_wins, win_type, w_cas = ch.resolve_battle_outcome(
        ac, dc, 1.0 if sum(att.values()) else 0.0, 1.0 if sum(den.values()) else 0.0
    )
    if defender_wins:
        w_pairs, l_pairs = ch.compute_unit_casualties(
            w_cas, win_type, list(den), list(att), den, att, rng=rng
        )
        return True, win_type, l_pairs, w_pairs
    w_pairs, l_pairs = ch.compute_unit_casualties(
        w_cas, win_type, list(att), list(den), att, den, rng=rng
    )
    return False, win_type, w_pairs, l_pairs


def battle_win_rate(ratio, n, system, rng):
    base = {"soldiers": 100000, "tanks": 4000, "artillery": 2000}
    att = {u: max(1, int(c * ratio)) for u, c in base.items()}
    wins = 0
    for _ in range(n):
        defender_wins, _, _, _ = resolve(att, dict(base), rng, system)
        if not defender_wins:
            wins += 1
    return wins / n


def upset_rate(small, big, system, n, rng, domain="ground"):
    att = {domain and list(DEFEND[domain])[0]: small}
    # use the first unit of the domain
    unit = DEFEND[domain][0]
    att = {unit: small}
    den = {unit: big}
    wins = 0
    for _ in range(n):
        defender_wins, _, _, _ = resolve(att, den, rng, system)
        if not defender_wins:
            wins += 1
    return wins / n


def _median(xs):
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    mid = n // 2
    if n % 2:
        return ys[mid]
    return (ys[mid - 1] + ys[mid]) / 2


def simulate_war(system, army, rng, strikes=False, army_scale_b=1.0, trials_label=""):
    """One war. Returns (battles, hours, winner_is_a). A is the striker if strikes."""
    a = {u: int(c) for u, c in army.items()}
    b = {u: max(1, int(c * army_scale_b)) for u, c in army.items()}
    # scale_b > 1 means B is bigger. For 0.8x nation, A is the small one: pass army as the big
    # and army_scale... cleaner: caller passes both via army (A) and scale of B.
    # Master still starts at 100. New wars start at MORALE_START (150).
    start = 100 if system == "master" else ch.MORALE_START
    morale = [start, start]
    ap = [{d: 6 for d in DOMAINS}, {d: 6 for d in DOMAINS}]
    hour = 0
    battles = 0
    strikes_used_day = 0
    strike_day = 0
    prior_hits = {}  # target type -> strikes this war (does not reset each day)
    pending = {}  # unit -> (suppress, expires_hour)
    winner_a = None
    while min(morale) > 0 and battles < 4000 and hour < 2000:
        if sum(a.values()) <= 0 or sum(b.values()) <= 0:
            winner_a = sum(a.values()) > 0 and sum(b.values()) <= 0
            break
        acted = False
        order = (0, 1) if rng.random() < 0.5 else (1, 0)
        for side in order:
            for domain in DOMAINS:
                if morale[0] <= 0 or morale[1] <= 0:
                    break
                if ap[side][domain] < 3:
                    continue
                att_units = _pick(a if side == 0 else b, ATTACK[domain])
                den_units = _pick(b if side == 0 else a, DEFEND[domain])
                if not att_units:
                    continue
                # Precision strike: side 0, before a ground attack, naval AP, 3 per 24h.
                suppress = None
                if strikes and side == 0 and domain == "ground":
                    day = hour // 24
                    if day != strike_day:
                        strike_day = day
                        strikes_used_day = 0
                    pending = {
                        u: (s, exp) for u, (s, exp) in pending.items() if exp > hour
                    }
                    if (
                        strikes_used_day < ch.STRIKE_DAILY_LIMIT
                        and ap[0]["naval"] >= ch.PRECISION_AP_COST
                        and a.get("cruisers", 0) > 0
                        and den_units
                    ):
                        target = max(
                            den_units,
                            key=lambda u: ch.UNIT_POWER.get(u, 1) * den_units[u],
                        )
                        ap[0]["naval"] -= ch.PRECISION_AP_COST
                        strikes_used_day += 1
                        prior = prior_hits.get(target, 0)
                        res = ch.compute_precision_strike(
                            "cruisers",
                            a.get("cruisers", 0),
                            target,
                            b.get(target, 0),
                            b.get("destroyers", 0),
                            prior,
                            rng=rng,
                        )
                        prior_hits[target] = prior + 1
                        b[target] = max(0, b.get(target, 0) - res["killed"])
                        a["cruisers"] = max(0, a.get("cruisers", 0) - res["lost"])
                        if res["suppress"] > 0:
                            pending[target] = (
                                min(
                                    ch.SUPPRESS_MAX,
                                    pending.get(target, (0, 0))[0] + res["suppress"],
                                ),
                                hour + ch.SUPPRESS_WINDOW_HOURS,
                            )
                        den_units = _pick(b, DEFEND[domain])
                    fielded = {
                        u: f
                        for u, (f, exp) in pending.items()
                        if den_units.get(u, 0) > 0 and exp > hour
                    }
                    if fielded:
                        suppress = fielded
                        for u in fielded:
                            pending.pop(u, None)
                if not den_units and not att_units:
                    continue
                defender_wins, win_type, a_pairs, d_pairs = resolve(
                    att_units,
                    den_units or {"soldiers": 0},
                    rng,
                    system,
                    suppress=suppress,
                )
                # map pairs back. resolve returns (att_pairs, def_pairs)
                stock_att = a if side == 0 else b
                stock_def = b if side == 0 else a
                _apply_cas(stock_att, a_pairs)
                _apply_cas(stock_def, d_pairs)
                loser = 1 - side if not defender_wins else side
                # morale uses the forces that fought
                if system == "master":
                    delta = _morale_master(
                        den_units if not defender_wins else att_units,
                        att_units,
                        den_units,
                        defender_wins,
                        win_type,
                    )
                else:
                    delta = ch.compute_morale_delta(
                        den_units if not defender_wins else att_units,
                        att_units,
                        den_units,
                        defender_wins,
                        win_type,
                    )
                morale[loser] = max(0, morale[loser] - delta)
                ap[side][domain] -= 3
                battles += 1
                acted = True
        if morale[0] <= 0 or morale[1] <= 0:
            winner_a = morale[1] <= 0 and morale[0] > 0
            break
        if not acted:
            hour += 1
            for side in (0, 1):
                for d in DOMAINS:
                    ap[side][d] = min(12, ap[side][d] + 1)
    if winner_a is None:
        winner_a = morale[0] > morale[1]
    return battles, hour, winner_a


def run_wars(system, strength, n, rng, strikes=False, scale_b=1.0):
    army = army_for_strength("Balanced", strength)
    rows = [
        simulate_war(system, army, rng, strikes=strikes, army_scale_b=scale_b)
        for _ in range(n)
    ]
    battles = [r[0] for r in rows]
    hours = [r[1] for r in rows]
    a_wins = sum(1 for r in rows if r[2]) / len(rows)
    return {
        "battles": _median(battles),
        "hours": _median(hours),
        "refills": _median(hours),
        "open_end": sum(1 for h in hours if h == 0) / len(hours),
        "a_win": a_wins,
        "army": army,
    }


def main():
    from wars import nuclear as nk

    rng = random.Random(20261026)
    compact = nk.blast_profile(land=10, cities=20)
    huge = nk.blast_profile(land=750, cities=760)
    print(
        f"nuke compact death {compact['death_frac']:.3f} infra {compact['infra_frac']:.3f} "
        f"huge death {huge['death_frac']:.3f} cooldown {nk.TARGET_COOLDOWN_DAYS}d "
        f"(master blast is the same 0.60/0.70; master has no per-target cooldown)"
    )
    print(
        f"strike day-max kill {ch.max_daily_strike_kill_fraction():.1%} "
        f"suppress max {ch.SUPPRESS_MAX:.0%} "
        f"lifetime kill cap {ch.STRIKE_MAX_FRAC / (1 - ch.STRIKE_DIMINISH):.0%}"
    )
    print("battle win rates (identical mix, scaled)")
    for system in ("master", "new"):
        for ratio in (0.01, 0.5, 0.8, 1.0, 1.1, 1.25, 2.0):
            n = 2000 if ratio >= 0.5 else 500
            wr = battle_win_rate(ratio, n, system, rng)
            print(f"  {system:6} {ratio:4}x  {wr:.3f}")
    print("upset 1 vs 100 / 1 vs 60e9")
    for system in ("master", "new"):
        for domain in DOMAINS:
            u = upset_rate(1, 100, system, 400, rng, domain)
            print(f"  {system:6} {domain:6} 1v100 {u:.3f}")
        u = upset_rate(1, 60_000_000_000, system, 50, rng, "ground")
        print(f"  {system:6} ground 1v60e9 {u:.3f}")

    print("even wars")
    for strength in (5_000, 50_000, 200_000, 1_000_000):
        for system in ("master", "new"):
            r = run_wars(system, strength, 80, rng)
            print(
                f"  str {strength:8} {system:6} median battles {r['battles']}  "
                f"MAP refills {r['refills']}  ended on opening AP {r['open_end']:.2f}  "
                f"A win {r['a_win']:.2f}  soldiers {r['army']['soldiers']}"
            )
    print(
        "strike wars at 200k (A strikes, B does not); B scale 1.0 and 1.25 (A is 0.8x)"
    )
    for scale, label in ((1.0, "equal"), (1.25, "A is 0.8x of B")):
        r = run_wars("new", 200_000, 60, rng, strikes=True, scale_b=scale)
        print(
            f"  {label}: A win {r['a_win']:.2f}  median battles {r['battles']} hours {r['hours']}"
        )


if __name__ == "__main__":
    sys.exit(main())
