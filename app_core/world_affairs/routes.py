from flask import Blueprint, request, render_template

from helpers import login_required
from database import get_request_cursor, cache_response

from .services import fetch_feed_page

bp = Blueprint("world_affairs", __name__)


@bp.route("/world_affairs", methods=["GET"])
@login_required
@cache_response(ttl_seconds=20)
def view_world_affairs():
    page = request.args.get("page", default=1, type=int) or 1
    with get_request_cursor(read_only=True) as db:
        events, page, total_pages = fetch_feed_page(db, page)

    return render_template(
        "world_affairs.html", events=events, page=page, total_pages=total_pages
    )
