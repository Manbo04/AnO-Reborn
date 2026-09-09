#!/usr/bin/env python3
"""Hand-patch gunicorn 21.2.0 for the timeout-mid-response 500-injection bug.

Upstream: https://github.com/benoitc/gunicorn/issues/3410, fixed in 26.2.1
(commit 049bbf7a) -- not yet on PyPI as of this writing, so this patches our
pinned 21.2.0 install directly instead of depending on a git+https install.

A worker timeout raised mid-response is SystemExit (a BaseException, not an
Exception), so `except Exception:` around the "headers already sent, close
gracefully" cleanup in gthread.py/sync.py/base_async.py's handle_request()
never catches it -- execution falls through to gunicorn's generic handler,
which writes a fresh 500 response onto the same already-partially-written
socket. With keep-alive connections reused across different visitors by the
reverse proxy, this can deliver one user's (authenticated) response to a
different browser -- the suspected root cause of AnO's account
cross-contamination reports.

Matches each file's specific `except Exception:` immediately followed by
`if resp and resp.headers_sent:` on the next line -- each file has other,
unrelated `except Exception:` blocks (a future-callback cleanup, a
post_request-hook error swallower) that must NOT be touched. Run after
`pip install -r requirements.txt` in the Dockerfile. Idempotent: safe to
run twice (second run finds 0 matches and does nothing).
"""
import re
import sys

TARGET_RE = re.compile(
    r"([ \t]*)except Exception:\n([ \t]*if resp and resp\.headers_sent:)"
)
REPLACEMENT = r"\1except BaseException:\n\2"

FILES = [
    "gunicorn/workers/gthread.py",
    "gunicorn/workers/sync.py",
    "gunicorn/workers/base_async.py",
]


def _package_dir():
    import gunicorn

    return gunicorn.__path__[0]


def main() -> int:
    import os

    base = os.path.dirname(_package_dir())
    any_patched = False
    for rel in FILES:
        path = os.path.join(base, rel)
        with open(path, "r") as f:
            content = f.read()

        matches = TARGET_RE.findall(content)
        if len(matches) == 0:
            already_patched = "except BaseException:\n" in content and re.search(
                r"except BaseException:\n[ \t]*if resp and resp\.headers_sent:", content
            )
            if already_patched:
                print(f"[patch_gunicorn] {rel}: already patched, skipping")
                continue
            print(f"[patch_gunicorn] ERROR: {rel}: expected pattern not found -- "
                  f"gunicorn source may have changed, refusing to patch blindly")
            return 1
        if len(matches) > 1:
            print(f"[patch_gunicorn] ERROR: {rel}: found {len(matches)} matches, "
                  f"expected exactly 1 -- ambiguous, refusing to patch")
            return 1

        new_content, n = TARGET_RE.subn(REPLACEMENT, content)
        assert n == 1
        with open(path, "w") as f:
            f.write(new_content)
        print(f"[patch_gunicorn] {rel}: patched (except Exception -> except BaseException)")
        any_patched = True

    if any_patched:
        print("[patch_gunicorn] Done -- gunicorn timeout/500-injection bug patched "
              "(https://github.com/benoitc/gunicorn/issues/3410)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
