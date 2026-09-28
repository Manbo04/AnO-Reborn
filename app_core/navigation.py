"""Grouped site navigation: menu sections -> hubs -> tabbed pages.

The navbar dropdowns used to list every page flat (10 under Internal Affairs,
9 under Global Affairs). Pages are now grouped into a few "hubs"; the dropdown
lists only the hubs, and each hub's pages share a tab strip rendered above the
page content (same idea as the country page's View / Revenue / News / Edit).

Single source of truth for the desktop dropdowns, the mobile hamburger menu,
the section tab strip, and the bottom-nav active state — edit here, not in
``templates/layout.html``.
"""

from __future__ import annotations

from typing import Any, Optional

# Each tab: (label, icon, href, path prefixes that make it active).
# ``href`` may contain ``{uid}`` which is replaced with the viewer's user id.
# Prefixes containing ``{uid}`` / ``{cid}`` (viewer's coalition id) are resolved
# the same way; a ``{cid}`` prefix is skipped when the viewer has no coalition.
NAV_SECTIONS: list[dict[str, Any]] = [
    {
        "label": "Internal Affairs",
        "hubs": [
            {
                "key": "nation",
                "label": "Nation",
                "icon": "language",
                "tabs": [
                    ("Overview", "flag", "/country/id={uid}", ("/country/id={uid}",)),
                    (
                        "Provinces",
                        "account_balance",
                        "/provinces",
                        ("/provinces", "/province/"),
                    ),
                    ("Projects", "engineering", "/upgrades", ("/upgrades",)),
                ],
            },
            {
                "key": "economy",
                "label": "Economy",
                "icon": "local_grocery_store",
                "tabs": [
                    ("Market", "local_grocery_store", "/market", ("/market",)),
                    (
                        "Trade Agreements",
                        "handshake",
                        "/trade-agreements",
                        ("/trade-agreements",),
                    ),
                    ("Loans", "account_balance_wallet", "/loans", ("/loans",)),
                    ("Bonds", "request_quote", "/bonds", ("/bonds",)),
                    (
                        "Currency Market",
                        "swap_horiz",
                        "/currency_market",
                        ("/currency_market",),
                    ),
                    (
                        "Currency Unions",
                        "currency_exchange",
                        "/currency_unions",
                        ("/currency_unions", "/currency/"),
                    ),
                ],
            },
            {
                "key": "military",
                "label": "Military",
                "icon": "shield",
                "tabs": [
                    ("Forces", "shield", "/military", ("/military",)),
                    (
                        "Wars",
                        "military_tech",
                        "/wars",
                        (
                            "/wars",
                            "/war/",
                            "/declare_war",
                            "/find_targets",
                            "/defense",
                            "/peace_offers",
                            "/intelligence",
                            "/spy",
                        ),
                    ),
                    ("Bounties", "gavel", "/bounties", ("/bounties",)),
                ],
            },
        ],
    },
    {
        "label": "Global Affairs",
        "hubs": [
            {
                "key": "coalitions",
                "label": "Coalitions",
                "icon": "group",
                "tabs": [
                    # /my_coalition redirects to /coalition/<id>; {cid} is the
                    # viewer's coalition so that page keeps this tab lit.
                    (
                        "My Coalition",
                        "group",
                        "/my_coalition",
                        ("/my_coalition", "/coalition/{cid}"),
                    ),
                    (
                        "All Coalitions",
                        "public",
                        "/coalitions",
                        ("/coalitions", "/coalition/"),
                    ),
                    (
                        "Establish",
                        "group_add",
                        "/establish_coalition",
                        ("/establish_coalition",),
                    ),
                ],
            },
            {
                "key": "nations",
                "label": "Nations",
                "icon": "person_pin_circle",
                "tabs": [
                    # Other players' country pages also light up this tab
                    # (own country is claimed by the Nation hub first).
                    (
                        "Countries",
                        "person_pin_circle",
                        "/countries",
                        ("/countries", "/country/"),
                    ),
                    ("Rankings", "leaderboard", "/rankings", ("/rankings",)),
                ],
            },
            {
                "key": "diplomacy",
                "label": "Diplomacy",
                "icon": "handshake",
                "tabs": [
                    ("Treaties", "handshake", "/treaties", ("/treaties",)),
                    ("Assembly", "chat", "/assembly", ("/assembly",)),
                    ("World Affairs", "public", "/world_affairs", ("/world_affairs",)),
                ],
            },
        ],
    },
]


def _fill(template: str, uid: Any, cid: Any = None) -> Optional[str]:
    if "{cid}" in template:
        if cid is None:
            return None
        template = template.replace("{cid}", str(cid))
    return template.replace("{uid}", str(uid))


def _matches(path: str, prefix: Optional[str]) -> bool:
    """Prefix match that won't let ``/country/id=1`` claim ``/country/id=16``."""
    if not prefix or not path.startswith(prefix):
        return False
    if prefix.endswith(("/", "=")) or len(path) == len(prefix):
        return True
    return not path[len(prefix)].isalnum()


def build_nav(
    path: str, user_id: Optional[int], coalition_id: Optional[int] = None
) -> dict[str, Any]:
    """Resolve the nav tree for the current request.

    Returns ``{"sections": [...], "active_hub": hub-or-None}``. Every hub and tab
    carries a resolved ``href`` and an ``active`` flag. Hubs are checked in
    declaration order and the first match wins, which is how the viewer's own
    country page lands in "Nation" while other countries land in "Nations".
    """
    uid = user_id if user_id is not None else ""
    active_hub = None
    sections = []
    for section in NAV_SECTIONS:
        hubs = []
        for hub in section["hubs"]:
            tabs = []
            hub_active = False
            for label, icon, href, prefixes in hub["tabs"]:
                is_active = (
                    active_hub is None
                    and not hub_active
                    and any(
                        _matches(path, _fill(p, uid, coalition_id)) for p in prefixes
                    )
                )
                hub_active = hub_active or is_active
                tabs.append(
                    {
                        "label": label,
                        "icon": icon,
                        "href": _fill(href, uid),
                        "active": is_active,
                    }
                )
            resolved = {
                "key": hub["key"],
                "label": hub["label"],
                "icon": hub["icon"],
                "href": tabs[0]["href"],
                "summary": " · ".join(t["label"] for t in tabs),
                "tabs": tabs,
                "active": hub_active,
            }
            if hub_active:
                active_hub = resolved
            hubs.append(resolved)
        sections.append({"label": section["label"], "hubs": hubs})
    return {"sections": sections, "active_hub": active_hub}
