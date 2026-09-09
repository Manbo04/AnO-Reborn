from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# async_mode="threading": runs on gunicorn's existing gthread/sync workers with
# real OS threads, no process-wide monkey-patching of psycopg2/socket/ssl.
# A true websocket upgrade needs a cooperative (gevent/eventlet) worker, which
# was tried and reverted -- psycogreen's wait-callback silently dropped
# committed writes under this app's real concurrency (verified via direct
# repro: commit() and conn.info.transaction_status both reported success, but
# a completely independent connection in the same process still read the old
# value). Both eventlet and gevent variants showed the identical bug, so this
# isn't a worker-class choice, it's psycogreen itself being unsafe here.
# Socket.IO's client automatically falls back to its long-polling transport
# under "threading" mode -- ordinary HTTP request/response, no raw socket
# hijacking -- which still delivers near-real-time chat without touching the
# DB layer's concurrency model at all.
# No cross-origin clients needed -- the chat UI is only ever served from this
# same app, so CORS is left at its default (disabled).
# manage_session=False: don't let Flask-SocketIO fork/copy flask.session per
# connection (its default). None of our socketio.on handlers ever write to
# session (app_core/chat/routes.py only reads session["user_id"]), so this is
# a functional no-op for us -- it just removes a whole class of custom
# session-handling machinery that runs outside Flask's own request-context
# push/pop lifecycle, while we investigate a live account cross-contamination
# bug (see memory: ano-session-cross-contamination-investigation-2026-09-08).
socketio = SocketIO(async_mode="threading", manage_session=False)
