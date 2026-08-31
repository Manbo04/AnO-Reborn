"""Routes + Socket.IO handlers for coalition group chat and nation DMs."""

import time

from flask import Blueprint, render_template, session, redirect, jsonify
from flask_socketio import join_room, emit, disconnect

from helpers import login_required, error, is_theme_v2_enabled
from database import get_request_cursor

from . import repositories as repo

bp = Blueprint("chat", __name__)

# Minimal per-user flood guard. In-memory / per-worker-process only -- good
# enough to stop accidental key-mashing, not a security boundary.
_MIN_SECONDS_BETWEEN_MESSAGES = 0.5
_last_message_at = {}


def _throttled(user_id):
    now = time.monotonic()
    last = _last_message_at.get(user_id, 0)
    if now - last < _MIN_SECONDS_BETWEEN_MESSAGES:
        return True
    _last_message_at[user_id] = now
    return False


def _clean_content(raw):
    if not isinstance(raw, str):
        return None
    content = raw.strip()
    if not content or len(content) > repo.MAX_MESSAGE_LENGTH:
        return None
    return content


@bp.route("/coalition/<int:coalition_id>/chat/messages", methods=["GET"])
@login_required
def coalition_chat_history(coalition_id):
    user_id = session["user_id"]
    if not repo.is_coalition_member(user_id, coalition_id):
        return error(403, "You are not in this coalition")
    return jsonify({"messages": repo.list_coalition_messages(coalition_id)})


@bp.route("/messages", methods=["GET"])
@login_required
def messages_inbox():
    user_id = session["user_id"]
    conversations = repo.list_conversations_for_user(user_id)
    template = "messages_inbox_v2.html" if is_theme_v2_enabled("messages") else "messages_inbox.html"
    return render_template(template, conversations=conversations)


@bp.route("/messages/<int:other_user_id>", methods=["GET"])
@login_required
def messages_thread(other_user_id):
    user_id = session["user_id"]
    if other_user_id == user_id:
        return redirect("/messages")

    with get_request_cursor() as db:
        db.execute("SELECT username FROM users WHERE id=%s", (other_user_id,))
        row = db.fetchone()
    if not row:
        return error(404, "Nation not found")
    other_username = row[0]

    history = repo.list_conversation_messages(user_id, other_user_id)
    repo.mark_conversation_read(user_id, other_user_id)
    template = "messages_thread_v2.html" if is_theme_v2_enabled("messages") else "messages_thread.html"
    return render_template(
        template,
        other_user_id=other_user_id,
        other_username=other_username,
        history=history,
    )


def register_chat_routes(app):
    app.register_blueprint(bp)


def register_chat_socketio_handlers(socketio):
    @socketio.on("connect")
    def handle_connect():
        user_id = session.get("user_id")
        if not user_id:
            return False
        # Personal room so a DM notification can reach the recipient even when
        # they aren't currently on the /messages/<other_id> thread page.
        join_room(f"user_{user_id}")
        return True

    @socketio.on("join_coalition_chat")
    def handle_join_coalition_chat(data):
        user_id = session.get("user_id")
        if not user_id:
            return disconnect()
        try:
            coalition_id = int((data or {}).get("coalition_id"))
        except (TypeError, ValueError):
            return
        if not repo.is_coalition_member(user_id, coalition_id):
            return
        join_room(f"coalition_{coalition_id}")

    @socketio.on("coalition_chat_message")
    def handle_coalition_chat_message(data):
        user_id = session.get("user_id")
        if not user_id:
            return disconnect()
        try:
            coalition_id = int((data or {}).get("coalition_id"))
        except (TypeError, ValueError):
            return
        content = _clean_content((data or {}).get("content"))
        if not content or _throttled(user_id):
            return
        if not repo.is_coalition_member(user_id, coalition_id):
            return
        message = repo.create_coalition_message(coalition_id, user_id, content)
        emit("coalition_chat_message", message, room=f"coalition_{coalition_id}")

    @socketio.on("join_dm")
    def handle_join_dm(data):
        user_id = session.get("user_id")
        if not user_id:
            return disconnect()
        try:
            other_user_id = int((data or {}).get("other_user_id"))
        except (TypeError, ValueError):
            return
        if other_user_id == user_id:
            return
        room = f"dm_{min(user_id, other_user_id)}_{max(user_id, other_user_id)}"
        join_room(room)

    @socketio.on("dm_message")
    def handle_dm_message(data):
        user_id = session.get("user_id")
        if not user_id:
            return disconnect()
        try:
            other_user_id = int((data or {}).get("other_user_id"))
        except (TypeError, ValueError):
            return
        if other_user_id == user_id:
            return
        content = _clean_content((data or {}).get("content"))
        if not content or _throttled(user_id):
            return
        try:
            message = repo.create_direct_message(user_id, other_user_id, content)
        except Exception:
            # Most likely an FK violation (recipient doesn't exist) -- drop silently,
            # nothing useful to tell an attacker probing user ids over a socket event.
            return
        room = f"dm_{min(user_id, other_user_id)}_{max(user_id, other_user_id)}"
        emit("dm_message", message, room=room)
        # Lets the recipient's inbox/badge update live even if they're not on
        # this specific conversation's thread page right now.
        emit(
            "dm_notification",
            {
                "from_user_id": user_id,
                "from_username": message["sender_username"],
                "preview": content[:120],
            },
            room=f"user_{other_user_id}",
        )
