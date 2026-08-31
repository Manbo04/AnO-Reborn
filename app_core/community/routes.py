"""Routes for the homepage hub's Devlog (admin changelog) and Discussions
(public forum) sections.
"""

from flask import Blueprint, render_template, request, session, redirect, flash

from helpers import login_required, error
from app_core.admin.services import SUPER_ADMIN_USER_IDS

from . import repositories as repo

bp = Blueprint("community", __name__)


def _is_admin():
    return session.get("user_id") in SUPER_ADMIN_USER_IDS


def _clean(raw, max_length):
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or len(value) > max_length:
        return None
    return value


@bp.route("/devlog", methods=["GET", "POST"])
@login_required
def devlog():
    if request.method == "POST":
        if not _is_admin():
            return error(403, "Only the AnO team can post devlog entries.")
        title = _clean(request.form.get("title"), repo.TITLE_MAX_LENGTH)
        body = _clean(request.form.get("body"), repo.DEVLOG_BODY_MAX_LENGTH)
        if not title or not body:
            flash("Title and body are required.")
            return redirect("/devlog")
        repo.create_devlog_entry(session["user_id"], title, body)
        return redirect("/devlog")

    return render_template(
        "devlog.html",
        entries=repo.list_devlog_entries(limit=50),
        is_admin=_is_admin(),
    )


@bp.route("/discussions", methods=["GET", "POST"])
@login_required
def discussions():
    if request.method == "POST":
        title = _clean(request.form.get("title"), repo.TITLE_MAX_LENGTH)
        body = _clean(request.form.get("body"), repo.THREAD_BODY_MAX_LENGTH)
        if not title or not body:
            flash("Title and body are required.")
            return redirect("/discussions")
        thread = repo.create_thread(session["user_id"], title, body)
        return redirect(f"/discussions/{thread['id']}")

    return render_template(
        "discussions.html",
        threads=repo.list_threads(limit=50),
    )


@bp.route("/discussions/<int:thread_id>", methods=["GET", "POST"])
@login_required
def thread_detail(thread_id):
    if request.method == "POST":
        content = _clean(request.form.get("content"), repo.REPLY_MAX_LENGTH)
        if not content:
            flash("Reply cannot be empty.")
            return redirect(f"/discussions/{thread_id}")
        result = repo.create_reply(thread_id, session["user_id"], content)
        if not result:
            return error(404, "This thread doesn't exist")
        return redirect(f"/discussions/{thread_id}")

    thread = repo.get_thread(thread_id)
    if not thread:
        return error(404, "This thread doesn't exist")
    return render_template(
        "discussion_thread.html",
        thread=thread,
        is_admin=_is_admin(),
    )


@bp.route("/discussions/<int:thread_id>/delete", methods=["POST"])
@login_required
def delete_thread(thread_id):
    if repo.delete_thread(thread_id, session["user_id"], _is_admin()):
        return redirect("/discussions")
    return error(403, "You can't delete this thread")


@bp.route("/discussions/reply/<int:reply_id>/delete", methods=["POST"])
@login_required
def delete_reply(reply_id):
    with_thread = request.form.get("thread_id")
    if repo.delete_reply(reply_id, session["user_id"], _is_admin()):
        return redirect(f"/discussions/{with_thread}" if with_thread else "/discussions")
    return error(403, "You can't delete this reply")


def register_community_routes(app):
    app.register_blueprint(bp)
