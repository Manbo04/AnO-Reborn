"""Shared guards for staff diagnostic and admin HTML routes."""
from __future__ import annotations

import hmac
import os

from flask import request

from app_core.admin.services import admin_only_guard


def admin_diag_authorized() -> bool:
    """True when X-DIAG-SECRET matches ADMIN_DIAG_SECRET."""
    secret = (os.getenv("ADMIN_DIAG_SECRET") or "").strip()
    if not secret:
        return False
    header = (request.headers.get("X-DIAG-SECRET") or "").strip()
    return bool(header) and hmac.compare_digest(header, secret)


def admin_diag_or_session(user_id) -> bool:
    """Staff HTML routes: logged-in super-admin OR valid diag secret header."""
    if admin_diag_authorized():
        return True
    if user_id and admin_only_guard(user_id) is None:
        return True
    return False


def admin_diag_denied_response():
    return "Unauthorized", 401
