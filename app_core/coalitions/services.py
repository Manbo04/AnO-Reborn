from flask import (
    request,
    render_template,
    session,
    redirect,
    flash,
    current_app,
)
from helpers import login_required, error, empty_state, require_post_origin, get_influence
import os
from dotenv import load_dotenv

load_dotenv()
import variables  # noqa: E402
import datetime  # noqa: E402
from database import cache_response, rollback_db_cursor, get_request_cursor  # noqa: E402
from database import get_coalition_members_table  # noqa: E402
from typing import Optional  # noqa: E402


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
