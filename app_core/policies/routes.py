from flask import request, redirect, session

from helpers import login_required
from database import get_request_cursor

from .repositories import parse_policies_from_form
from .services import save_user_policies, invalidate_policies_cache


@login_required
def policies():
    cId = session["user_id"]

    with get_request_cursor() as db:
        military = parse_policies_from_form("soldiers", 7, request.form)
        education = parse_policies_from_form("education", 6, request.form)
        save_user_policies(db, cId, military, education)

    # Invalidate cached policies for this user - after the write above has
    # committed, not before (see save_user_policies' docstring).
    invalidate_policies_cache(cId)

    return redirect("/my_country")


def register_policies_routes(app_instance):
    """Register all policies routes with the Flask app instance"""
    app_instance.add_url_rule(
        "/policies/update", "policies_update", policies, methods=["POST"]
    )
