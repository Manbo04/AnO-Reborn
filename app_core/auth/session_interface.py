"""Session interface that refuses to put a session cookie on a publicly
cacheable response.

Found 2026-09-23 during the account cross-contamination investigation
(see memory: ano-account-cross-contamination-recurrence-2026-09-22).

THE BUG
-------
Every login path in this app sets ``session.permanent = True``, and Flask's
``SESSION_REFRESH_EACH_REQUEST`` defaults to ``True`` and is never overridden
here. Flask's ``SecureCookieSessionInterface.save_session()`` therefore
re-issues a fresh ``Set-Cookie: session=<signed value>`` on **every single
response** to a logged-in player -- not just on login, and not just on HTML
pages. That includes ``/static/*`` assets and every other ordinary Flask view.

Separately, ``app.py``'s ``after_request`` marks those same responses as
*publicly* cacheable:

    /static/*.css|.js  ->  Cache-Control: public, max-age=3600, must-revalidate
    /static/*          ->  Cache-Control: public, max-age=604800, must-revalidate

(Several views -- nation flags in ``app_core/main/routes.py``, province
images in ``province.py``, ad images in ``app_core/ads/routes.py``, Discord
OG cards in ``app_core/social_cards/`` -- set a ``public`` header of their
own too, but verified live: ``after_request``'s ``else`` branch overwrites
every non-``/static/`` path with ``private, max-age=5``, so those never
actually reach the wire as public today. They are one edit to that ordering
away from doing so, which is exactly why this guard lives at the session
interface instead of being a per-route header audit.)

``after_request`` hooks run BEFORE ``save_session`` (Flask's
``process_response``: all ``after_request`` handlers, then the session
interface), so the header combination that actually goes out on the wire is:

    Cache-Control: public, max-age=3600, must-revalidate
    Set-Cookie: session=<a real, valid, signed session cookie for one player>

That is CWE-525: an authentication cookie inside a response every shared
cache in the path is explicitly told it may store and replay. Whichever
logged-in player's request happens to populate a shared cache entry donates
their live session cookie to every subsequent visitor who is served that
cached asset -- who then silently becomes that player, with zero credentials
entered. ``/static/style.css`` and ``/static/game-shell.js`` are fetched by
every browser on essentially every page view, so this is the app's highest-
volume cache-fill path, not an obscure corner.

WHY IT FITS THE REPORTS AND WHY NOTHING FOUND IT EARLIER
--------------------------------------------------------
* No credentials are involved, and the victim only has to load a page.
* It is many-victims-into-one-account by construction: everyone served the
  cached asset receives the SAME donor's cookie, matching the multi-victim
  incidents in this saga.
* It only happens when someone else is logged in and active around the same
  time, i.e. concurrency-triggered -- matching Dede's own repro conditions.
* It is invisible to the app's own identity tripwires
  (``app_core/identity_diagnostics.py``): every request the app sees is
  perfectly self-consistent. The identity swap happens in a cache the app
  never touches, on a later request from a different browser.
* It is invisible to local load testing (the 412k-request harness runs) for
  the same reason: there is no shared HTTP cache in that loop at all.
* ``Vary: Cookie`` is not a defense. Flask does add it (``session.accessed``),
  but Cloudflare documents that it ignores ``Vary`` for everything except
  ``Accept-Encoding``, and intermediate/carrier proxies routinely ignore it
  too.

THE FIX
-------
Never emit the session cookie onto a response that is marked publicly
cacheable. This is enforced at the session interface, so it covers every
current and future route regardless of which blueprint sets the header --
rather than being a per-route header audit that the next new public route
would silently miss.

The one case that still has to write a cookie is a session that was just
CLEARED (logout, ban, kick, session-epoch bump) on a request whose response
happens to be publicly cacheable: dropping that would leave a revoked
session alive in the browser. That deletion cookie carries no credentials,
but a cached ``Set-Cookie: session=; Max-Age=0`` would log out every later
visitor, so the response is forced to ``no-store`` before it is sent.
"""

from flask.sessions import SecureCookieSessionInterface


def _is_publicly_cacheable(response) -> bool:
    """True if this response invites shared caches to store and replay it."""
    return "public" in (response.headers.get("Cache-Control") or "").lower()


class PublicCacheSafeSessionInterface(SecureCookieSessionInterface):
    """Stock Flask session handling, minus cookies on public responses."""

    def save_session(self, app, session, response):
        if not _is_publicly_cacheable(response):
            return super().save_session(app, session, response)

        if session.modified and not session:
            # Session was cleared during this request (logout / ban / kick /
            # session_epoch bump). The delete-cookie must still reach the
            # browser, so this response must not be shared-cached.
            response.headers["Cache-Control"] = "no-store"
            return super().save_session(app, session, response)

        # Otherwise: drop the cookie entirely. A refresh (the
        # SESSION_REFRESH_EACH_REQUEST rolling-expiry write) is re-issued on
        # the very next non-public response, and any session mutation made
        # while serving a public asset is recomputed on the next request --
        # neither is worth putting a live credential into a shared cache.
        return None
