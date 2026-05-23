"""Shared tab labels and helpers for Nation Academy tutorial recording."""

from __future__ import annotations

from typing import Any

# Mirrors static/script.js TAB_GROUPS — tab_id -> display label
TAB_LABELS: dict[str, str] = {
    "countryview": "View",
    "countryrevenue": "Revenue",
    "countrynews": "News",
    "countryactions": "Actions",
    "countryedit": "Edit",
    "provincecity": "City",
    "provinceland": "Land",
    "cityelectricity": "Electricity",
    "cityretail": "Retail",
    "cityworks": "Works",
    "landmilitary": "Military",
    "landindustry": "Industry",
    "landprocessing": "Processing",
    "militaryland": "Land",
    "militaryair": "Air",
    "militarywater": "Naval",
    "militaryspecial": "Special",
    "coalitiongeneral": "General",
    "coalitionjoin": "Join",
    "coalitionleader": "Leader",
    "coalitionmember": "Member",
    "upgradeseconomic": "Economic",
    "upgradesmilitary": "Military",
}

# tab_group -> ordered list of (tab_id, label) for banner chips
TAB_GROUP_CHIPS: dict[str, list[tuple[str, str]]] = {
    "country": [
        ("countryview", "View"),
        ("countryrevenue", "Revenue"),
        ("countrynews", "News"),
        ("countryactions", "Actions"),
        ("countryedit", "Edit"),
    ],
    "province": [
        ("provincecity", "City"),
        ("provinceland", "Land"),
    ],
    "province.land": [
        ("landmilitary", "Military"),
        ("landindustry", "Industry"),
        ("landprocessing", "Processing"),
    ],
    "military": [
        ("militaryland", "Land"),
        ("militaryair", "Air"),
        ("militarywater", "Naval"),
        ("militaryspecial", "Special"),
    ],
    "upgrades": [
        ("upgradeseconomic", "Economic"),
        ("upgradesmilitary", "Military"),
    ],
}

# Infer tab_group from tab id when not set in JSON
TAB_ID_TO_GROUP: dict[str, str] = {}
for group, chips in TAB_GROUP_CHIPS.items():
    for tab_id, _ in chips:
        TAB_ID_TO_GROUP[tab_id] = group


def infer_tab_group(step: dict[str, Any]) -> str | None:
    explicit = step.get("tab_group")
    if explicit and explicit != "none":
        return explicit
    tab = step.get("tab")
    if tab:
        return TAB_ID_TO_GROUP.get(tab)
    return None


def tab_label_for_step(step: dict[str, Any]) -> str | None:
    if step.get("tab_label"):
        return step["tab_label"]
    tab = step.get("tab")
    if tab:
        return TAB_LABELS.get(tab)
    return None


def chips_for_step(step: dict[str, Any]) -> list[tuple[str, str]]:
    group = infer_tab_group(step)
    if not group:
        return []
    return TAB_GROUP_CHIPS.get(group, [])


def effective_hold_sec(step: dict[str, Any], audio_duration: float | None = None) -> float:
    base = float(step.get("hold_sec", 6))
    if audio_duration is not None and audio_duration > 0:
        return max(base, audio_duration + 0.8)
    return base
