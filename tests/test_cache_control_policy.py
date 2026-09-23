"""Regression tests for app.py's after_request Cache-Control policy.

Two real defects found 2026-09-23 in the fresh pass on the account
cross-contamination investigation, both in the same class (authenticated or
secret material offered to a cache that should never hold it):

1. after_request overwrote Cache-Control on EVERY non-/static/ response
   unconditionally, which silently downgraded the deliberate `no-store` set by
   app_core/auth/routes.py on /account/2fa/setup (renders the raw TOTP secret
   and its QR code) and /account/2fa/confirm (renders the one-time backup
   codes) to `private, max-age=5`. That permits the browser to write standing
   account-recovery secrets to its on-disk cache, recoverable afterwards via
   the back button or on a shared machine.

2. Error responses under /static/ -- a 404 for a missing asset, or
   before_request's per-user ban/kick 403 page, which renders for whatever
   path triggered it -- were marked `public, max-age=604800`, offering a
   transient or per-user page to shared caches for a week.

The session cookie half of this bug class (a live session cookie riding on a
publicly cacheable /static/ response) is covered separately by
tests/test_no_session_cookie_on_public_response.py.
"""

import pytest

from app import resolve_cache_control


@pytest.mark.parametrize(
    "existing",
    ["no-store", "no-store, max-age=0", "No-Store"],
)
def test_explicit_no_store_is_never_downgraded(existing):
    result = resolve_cache_control("/account/2fa/setup", 200, existing)
    assert result == existing, (
        "a view that explicitly asked for no-store had it overwritten -- the "
        "2FA secret / backup-code pages rely on this to stay out of the "
        f"browser's disk cache (got {result!r})"
    )


def test_static_success_is_publicly_cacheable():
    assert resolve_cache_control("/static/style.css", 200, None) == (
        "public, max-age=3600, must-revalidate"
    )
    assert resolve_cache_control("/static/img/flag.png", 200, None) == (
        "public, max-age=604800, must-revalidate"
    )


@pytest.mark.parametrize("status", [403, 404, 500])
def test_static_error_pages_are_not_publicly_cacheable(status):
    result = resolve_cache_control("/static/missing.png", status, None)
    assert "public" not in result, (
        f"a {status} under /static/ was offered to shared caches: {result!r}. "
        "before_request's ban/kick 403 renders for whatever path triggered it, "
        "so this could pin one player's block page in front of everyone."
    )
    assert result == "private, max-age=5, must-revalidate"


def test_ordinary_pages_stay_private():
    assert resolve_cache_control("/my_country", 200, None) == (
        "private, max-age=5, must-revalidate"
    )
