"""Regression test for a real IP-resolution bug found live 2026-09-23
during the account cross-contamination investigation (not confirmed as
the cross-contamination mechanism itself, but a real, separate bug).

This app is Cloudflare-fronted in front of Railway's own edge. Railway's
own internal ingress always appends one extra constant hop of its own on
top of whatever Cloudflare added, so the old ProxyFix(x_for=1) config
resolved request.remote_addr to Railway's own internal hop IP for EVERY
visitor, not the real client -- confirmed live: every visitor resolved
to the same handful of addresses, previously misread across multiple
unrelated investigations as a "shared mobile-carrier CGNAT pool".
Cloudflare's edge-to-origin routing for this app also doesn't reliably
carry the real client IP in X-Forwarded-For at all (confirmed via a real
IPv6 client whose address never appeared in that header's chain), so
bumping x_for doesn't fix it either.

helpers.client_ip_from_request() now trusts CF-Connecting-IP (which
Cloudflare sets to the true client IP specifically to sidestep
X-Forwarded-For chain ambiguity) but ONLY when the hop immediately before
Railway's own constant internal hop is verifiably one of Cloudflare's
own published IP ranges -- otherwise it falls back to the previous
(imperfect, but never worse) ProxyFix-resolved remote_addr. This closes
a real spoofing hole: Railway's own public *.up.railway.app fallback
domain bypasses Cloudflare entirely and is directly reachable, so a
naive "always trust CF-Connecting-IP" fix would let anyone hitting that
domain forge any IP they want -- confirmed live before this fix: a
forged CF-Connecting-IP sent directly to that domain was reflected back
verbatim.

All three fixture values below are real evidence captured live against
the actual production Cloudflare+Railway chain on 2026-09-23, not
synthetic guesses.
"""
from flask import Flask

import helpers


def _app():
    return Flask(__name__)


def test_trusts_cf_connecting_ip_on_genuine_cloudflare_path():
    """Real captured evidence: hitting affairsandorder.org (Cloudflare-
    fronted) from a real IPv6 client. The true client IP never appears in
    X-Forwarded-For at all here -- only CF-Connecting-IP has it -- so this
    also proves x_for tuning alone could never have fixed this case."""
    app = _app()
    with app.test_request_context(
        headers={
            "CF-Connecting-IP": "2a00:f502:27e:f890:70c8:515e:5f72:f0f6",
            "X-Forwarded-For": "172.69.52.166, 152.233.43.34",
        },
        environ_base={"REMOTE_ADDR": "152.233.43.34"},
    ):
        assert (
            helpers.client_ip_from_request()
            == "2a00:f502:27e:f890:70c8:515e:5f72:f0f6"
        )


def test_rejects_spoofed_cf_connecting_ip_via_direct_railway_domain():
    """Real captured evidence: hitting the direct Railway fallback domain
    (bypassing Cloudflare) with a forged CF-Connecting-IP header. Must NOT
    be trusted -- the hop before Railway's own internal one is the
    attacker's own real IP, not a Cloudflare range, so this must fall
    back to the ProxyFix-resolved remote_addr instead of the forged
    value."""
    app = _app()
    with app.test_request_context(
        headers={
            "CF-Connecting-IP": "6.6.6.6",
            "X-Forwarded-For": "84.15.178.235, 152.233.43.34",
        },
        environ_base={"REMOTE_ADDR": "152.233.43.34"},
    ):
        result = helpers.client_ip_from_request()
        assert result != "6.6.6.6"
        assert result == "152.233.43.34"


def test_falls_back_to_remote_addr_with_no_cloudflare_headers():
    """Local dev / any non-Cloudflare-fronted deployment: no regression
    from the previous plain-ProxyFix behavior."""
    app = _app()
    with app.test_request_context(environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        assert helpers.client_ip_from_request() == "127.0.0.1"


def test_ignores_cf_connecting_ip_when_xff_chain_too_short():
    """A CF-Connecting-IP header alone, with an X-Forwarded-For chain that
    doesn't have the expected 2+ hops, must not be blindly trusted --
    the hop-verification check has nothing to verify against."""
    app = _app()
    with app.test_request_context(
        headers={
            "CF-Connecting-IP": "6.6.6.6",
            "X-Forwarded-For": "152.233.43.34",
        },
        environ_base={"REMOTE_ADDR": "152.233.43.34"},
    ):
        assert helpers.client_ip_from_request() != "6.6.6.6"
