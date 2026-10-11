"""Bot nations: sizing, war-range coverage and war-AI decisions (no DB needed)."""

import random

import pytest

from app_core.bots import profiles, service, war_ai
from wars.war_range import war_strength

pytestmark = pytest.mark.no_server

RES = ["rations", "oil", "steel", "ammunition", "gasoline", "iron"]


def _size(prov=3, strength=60_000, share=0.4, tier="even", arch="Balanced"):
    return profiles.size_bot(
        provinces=prov,
        target_strength=strength,
        army_share=share,
        archetype=arch,
        tier=tier,
        resource_names=RES,
    )


def _strength(s):
    return war_strength(s["population_per_province"] * s["provinces"], s["units"])


def test_bot_strength_lands_near_target():
    for target in (5_000, 60_000, 800_000):
        s = _size(strength=target)
        assert abs(_strength(s) - target) / target < 0.05, target
        assert s["target_strength"] == int(_strength(s))


def test_army_share_splits_strength_between_population_and_units():
    low, high = _size(share=0.2), _size(share=0.6)
    assert high["units"]["tanks"] > low["units"]["tanks"]
    assert high["population_per_province"] < low["population_per_province"]


def test_army_share_is_clamped():
    assert profiles.army_share_of(1000, 0) == profiles.MIN_ARMY_SHARE
    assert profiles.army_share_of(1000, 1000) == profiles.MAX_ARMY_SHARE
    assert profiles.army_share_of(0, 0) == profiles.MIN_ARMY_SHARE


def test_every_archetype_can_defend_every_domain():
    from attack_scripts.Nations import Military

    for arch in profiles.ARCHETYPES:
        units = _size(arch=arch, strength=120_000)["units"]
        for domain, names in Military.UNIT_DOMAINS.items():
            assert all(units[n] > 0 for n in names), (arch, domain)


def test_archetype_shares_sum_to_one():
    for arch, mix in profiles.ARCHETYPES.items():
        assert abs(sum(mix.values()) - 1.0) < 1e-9, arch


def test_tiers_sit_inside_the_declare_window_with_margin():
    from wars.war_range import WAR_RANGE_HIGH, WAR_RANGE_LOW

    for t in profiles.TIERS.values():
        assert WAR_RANGE_LOW + 0.1 <= t["ratio"] <= WAR_RANGE_HIGH - 0.1


def test_every_tier_of_a_bot_is_declarable_by_its_player():
    for tier, t in profiles.TIERS.items():
        s = _size(strength=50_000 * t["ratio"], tier=tier)
        assert profiles.in_war_range(50_000, _strength(s)), tier


def test_small_target_still_gets_every_unit_type():
    units = _size(strength=300)["units"]
    assert all(q >= 1 for q in units.values())


def test_in_war_range_is_the_games_own_rule():
    assert profiles.in_war_range(1000, 1000)
    assert profiles.in_war_range(1000, 750)
    assert profiles.in_war_range(1000, 1330)
    assert not profiles.in_war_range(1000, 749)
    assert not profiles.in_war_range(1000, 1331)


def test_missing_tiers_gives_a_spread():
    assert profiles.missing_tiers([]) == ["weak", "even", "strong"]
    assert profiles.missing_tiers([(1000, 1000)]) == ["weak", "strong"]
    assert profiles.missing_tiers([(880, 1000), (1000, 1000), (1180, 1000)]) == []
    assert profiles.missing_tiers([(1000, 1000)] * 2) == ["weak"]


def test_stronger_tiers_hold_more_loot():
    assert (
        profiles.gold_target(3, "weak")
        < profiles.gold_target(3, "even")
        < profiles.gold_target(3, "strong")
    )
    assert profiles.resource_target("iron", 3, "weak") < profiles.resource_target(
        "iron", 3, "strong"
    )


def test_regen_closes_gap_gradually_without_overshoot():
    assert profiles.regen_toward(0, 1000) == 150
    assert profiles.regen_toward(990, 1000) == 991
    assert profiles.regen_toward(2000, 1000) == 2000  # never reduces here
    assert profiles.regen_toward(999, 1000) <= 1000


def test_upkeep_resources_have_a_floor():
    assert profiles.upkeep_floor("ammunition", 1000) == 300
    assert profiles.upkeep_floor("iron", 1000) == 0


def test_names_unique_and_labelled():
    names = []
    for i in range(400):
        names.append(profiles.pick_name(i, names))
    assert len(set(n.lower() for n in names)) == 400
    assert all(n.endswith(profiles.BOT_SUFFIX) for n in names)


def test_war_ai_peace_rules():
    assert war_ai.should_accept_peace(
        war_age=13 * 3600, bot_morale=90, has_demands=False
    )
    assert war_ai.should_accept_peace(war_age=60, bot_morale=40, has_demands=False)
    assert not war_ai.should_accept_peace(war_age=60, bot_morale=90, has_demands=False)
    assert not war_ai.should_accept_peace(
        war_age=99 * 3600, bot_morale=10, has_demands=True
    )


def test_war_ai_counterattack_rules():
    base = dict(
        now=1_000_000.0,
        last_attack_at=0.0,
        last_human_action=1_000_000.0 - 600,
        started=0.0,
        bot_morale=80,
        roll=0.1,
    )
    assert war_ai.should_counterattack(**base)
    assert not war_ai.should_counterattack(
        **{**base, "last_attack_at": base["now"] - 60}
    )  # cooldown
    assert not war_ai.should_counterattack(**{**base, "bot_morale": 0})
    assert not war_ai.should_counterattack(**{**base, "roll": 0.99})
    # human went quiet for >36h and the war isn't new -> bot stays put
    assert not war_ai.should_counterattack(
        **{**base, "last_human_action": base["now"] - 40 * 3600}
    )
    # fresh declaration counts as live even before the human fights
    assert war_ai.should_counterattack(
        **{**base, "last_human_action": 0.0, "started": base["now"] - 600}
    )


ALL_AP = {"ground": 6, "air": 6, "naval": 6}


def test_pick_domain_follows_owned_units_and_ap():
    rng = random.Random(1)
    assert war_ai.pick_domain({"submarines": 50}, ALL_AP, rng) == "naval"
    assert war_ai.pick_domain({}, ALL_AP, rng) is None
    owned = {"soldiers": 1000, "fighters": 100, "cruisers": 100}
    seen = {war_ai.pick_domain(owned, ALL_AP, random.Random(i)) for i in range(60)}
    assert seen == {"ground", "air", "naval"}
    # a branch without the 3 AP an attack costs is never picked
    no_air = {"ground": 6, "air": 2, "naval": 6}
    assert "air" not in {
        war_ai.pick_domain(owned, no_air, random.Random(i)) for i in range(60)
    }
    assert war_ai.pick_domain({"fighters": 100}, no_air, rng) is None


def test_dig_in_only_with_spare_ap_and_room_to_grow():
    assert war_ai.should_dig_in(ground_ap=5, entrench=0)
    assert not war_ai.should_dig_in(ground_ap=4, entrench=0)  # keep an attack's worth
    assert not war_ai.should_dig_in(ground_ap=12, entrench=3)


def test_ensure_coverage_spawns_missing_bots_per_player(monkeypatch):
    humans = [
        {"id": 1, "provinces": 3, "strength": 5_000.0, "army_share": 0.3},
        {"id": 2, "provinces": 3, "strength": 5_200.0, "army_share": 0.3},
        {"id": 3, "provinces": 9, "strength": 90_000.0, "army_share": 0.5},
    ]
    existing = [{"id": 100, "provinces": 3, "strength": 5_100.0}]
    created = []

    class Cur:
        def execute(self, *a, **k):
            pass

    class Conn:
        def commit(self):
            pass

        def rollback(self):
            pass

    monkeypatch.setattr(service, "fetch_humans", lambda cur: humans)
    monkeypatch.setattr(service, "fetch_bots", lambda cur: list(existing))
    all_bots = list(existing)

    def fake_create(conn, cur, *, human, tier, archetype=None):
        created.append((human["id"], tier))
        bot = {
            "id": 200 + len(created),
            "provinces": human["provinces"],
            "strength": human["strength"] * profiles.TIERS[tier]["ratio"],
        }
        all_bots.append(bot)
        return bot["id"]

    monkeypatch.setattr(service, "create_bot", fake_create)
    out = service.ensure_coverage(Conn(), Cur())
    assert out["created"] == len(created) <= service.MAX_SPAWN_PER_RUN
    # player 3 (far stronger than everyone) gets a full difficulty spread
    assert [t for h, t in created if h == 3] == ["weak", "even", "strong"]
    # every player ends up with >=3 bots in their declare range (neighbours share bots)
    for h in humans:
        in_range = [
            b for b in all_bots if profiles.in_war_range(h["strength"], b["strength"])
        ]
        assert len(in_range) >= profiles.BOTS_PER_PLAYER, h["id"]


class _FakeCur:
    def __init__(self, guard_ok=True):
        self.sql, self.guard_ok = [], guard_ok

    def execute(self, sql, params=None):
        self.sql.append((sql, params))

    def fetchone(self):
        last = self.sql[-1][0]
        if "RETURNING id" in last:
            return (1,) if self.guard_ok else None
        return None


class _FakeConn:
    commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _patch_engine(
    monkeypatch, *, owned, attach_error=None, winner_is_bot=True, ap_ok=True
):
    import attack_scripts.Nations as nations
    import attack_scripts.war_orchestrator as orch
    import units as units_mod
    from wars import action_points as ap_mod

    fights, ap_spent, bookkeeping = [], [], []

    class FakeUnits:
        def __init__(
            self,
            user_id,
            selected_units=None,
            selected_units_list=None,
            war_id=None,
            **kw,
        ):
            self.user_id, self.selected_units = user_id, selected_units
            self.selected_units_list, self.war_id = selected_units_list, war_id
            self._fight_losses = {"soldiers": 3}

        def attach_units(self, sel, n):
            if attach_error:
                return attach_error
            self.selected_units = dict(sel)

        def save(self, db_cursor=None):
            pass

    def fake_fight(
        attacker,
        defender,
        citizen_army_pct=None,
        entrenchment_level=0,
        attacker_intel=0,
        domain=None,
    ):
        fights.append(
            dict(
                attacker=attacker,
                defender=defender,
                citizen=citizen_army_pct,
                entrench=entrenchment_level,
                intel=attacker_intel,
                domain=domain,
            )
        )
        return (
            (attacker.user_id if winner_is_bot else defender.user_id),
            "decisive",
            (10, 0),
        )

    monkeypatch.setattr(units_mod, "Units", FakeUnits)
    monkeypatch.setattr(
        nations.Military, "get_military", staticmethod(lambda uid: dict(owned))
    )
    monkeypatch.setattr(nations.Military, "fight", staticmethod(fake_fight))
    monkeypatch.setattr(
        orch,
        "resolve_defender_composition",
        lambda uid, dom: (
            list(nations.Military.UNIT_DOMAINS[dom]),
            {u: 100 for u in nations.Military.UNIT_DOMAINS[dom]},
        ),
    )
    monkeypatch.setattr(
        ap_mod,
        "spend_action_points",
        lambda db, war_id, uid, branch, cost: (
            ap_spent.append((branch, cost)) or (ap_ok, None if ap_ok else "no AP")
        ),
    )
    monkeypatch.setattr(
        ap_mod,
        "reset_entrenchment_on_ground_attack",
        lambda *a: bookkeeping.append("reset"),
    )
    monkeypatch.setattr(
        ap_mod, "consume_intel_on_attack", lambda *a: bookkeeping.append("intel")
    )
    return fights, ap_spent, bookkeeping


STATUS = {
    "ground_ap": 6,
    "air_ap": 6,
    "naval_ap": 6,
    "enemy_entrench": 2,
    "my_intel": 40,
}


def test_counterattack_spends_ap_uses_engine_modifiers_and_reports(monkeypatch):
    fights, ap_spent, bookkeeping = _patch_engine(
        monkeypatch,
        owned={"tanks": 100, "soldiers": 1000, "artillery": 50, "apaches": 20},
    )
    cur, conn = _FakeCur(), _FakeConn()
    ok = war_ai._counterattack(
        cur, conn, {"id": 7}, 11, 22, "Valdoria [AI]", STATUS, random.Random(3)
    )
    assert ok and len(fights) == 1
    f = fights[0]
    assert f["attacker"].user_id == 11 and f["defender"].user_id == 22
    assert f["domain"] == "ground" and f["entrench"] == 2 and f["intel"] == 40
    assert ap_spent == [("ground", 3)]
    assert bookkeeping == [
        "reset",
        "intel",
    ]  # ground attack drops own entrenchment, spends intel
    assert set(f["attacker"].selected_units) == {
        "soldiers",
        "tanks",
        "artillery",
        "apaches",
    }
    news = [p for s, p in cur.sql if s.startswith("INSERT INTO news")]
    assert (
        news
        and news[0][0] == 22
        and "BATTLE REPORT" in news[0][1]
        and "Defeat" in news[0][1]
    )


def test_non_ground_attack_keeps_entrenchment(monkeypatch):
    fights, ap_spent, bookkeeping = _patch_engine(monkeypatch, owned={"submarines": 50})
    assert war_ai._counterattack(
        _FakeCur(), _FakeConn(), {"id": 7}, 11, 22, "B", STATUS, random.Random(3)
    )
    assert fights[0]["domain"] == "naval" and ap_spent == [("naval", 3)]
    assert bookkeeping == ["intel"]


def test_counterattack_skips_when_units_cannot_be_attached(monkeypatch):
    fights, ap_spent, _ = _patch_engine(
        monkeypatch, owned={"tanks": 100}, attach_error="Invalid amount selected!"
    )
    assert (
        war_ai._counterattack(
            _FakeCur(), _FakeConn(), {"id": 7}, 11, 22, "B", STATUS, random.Random(1)
        )
        is False
    )
    assert not fights and not ap_spent


def test_counterattack_needs_action_points(monkeypatch):
    fights, _, _ = _patch_engine(monkeypatch, owned={"tanks": 100}, ap_ok=False)
    assert (
        war_ai._counterattack(
            _FakeCur(), _FakeConn(), {"id": 7}, 11, 22, "B", STATUS, random.Random(1)
        )
        is False
    )
    assert not fights
    broke = {**STATUS, "ground_ap": 2, "air_ap": 0, "naval_ap": 1}
    fights, ap_spent, _ = _patch_engine(monkeypatch, owned={"tanks": 100})
    assert (
        war_ai._counterattack(
            _FakeCur(), _FakeConn(), {"id": 7}, 11, 22, "B", broke, random.Random(1)
        )
        is False
    )
    assert not fights and not ap_spent


def test_counterattack_respects_replay_guard(monkeypatch):
    fights, _, _ = _patch_engine(monkeypatch, owned={"tanks": 100})
    assert (
        war_ai._counterattack(
            _FakeCur(guard_ok=False),
            _FakeConn(),
            {"id": 7},
            11,
            22,
            "B",
            STATUS,
            random.Random(1),
        )
        is False
    )
    assert not fights


def test_counterattack_player_win_is_reported_as_victory(monkeypatch):
    _patch_engine(monkeypatch, owned={"tanks": 100}, winner_is_bot=False)
    cur = _FakeCur()
    assert war_ai._counterattack(
        cur, _FakeConn(), {"id": 7}, 11, 22, "B", STATUS, random.Random(1)
    )
    news = [p for s, p in cur.sql if s.startswith("INSERT INTO news")]
    assert "Victory" in news[0][1]
