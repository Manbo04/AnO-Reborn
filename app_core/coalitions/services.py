from helpers import empty_state


def _no_coalition_response():
    """Shown when the player is not in any coalition (not an HTTP error)."""
    return empty_state(
        title="No coalition yet",
        message=(
            "You haven't joined a coalition. Browse existing coalitions to apply, "
            "or establish your own and invite other nations."
        ),
        icon="groups",
        actions=[
            {"href": "/coalitions", "label": "Browse coalitions", "icon": "public"},
            {
                "href": "/establish_coalition",
                "label": "Establish a coalition",
                "icon": "group_add",
            },
            {
                "href": "/recruitments",
                "label": "Recruiting coalitions",
                "icon": "person_search",
            },
        ],
    )
