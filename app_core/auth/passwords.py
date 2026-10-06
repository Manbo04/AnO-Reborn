"""Shared password hashing and verification (bcrypt primary, werkzeug legacy)."""
from __future__ import annotations

import bcrypt
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    """Create a bcrypt hash for new accounts."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def password_matches(stored_hash: str | None, password: str) -> bool:
    """Verify werkzeug (legacy) or bcrypt hashes."""
    if not stored_hash or not isinstance(stored_hash, str):
        return False
    if stored_hash.startswith(("scrypt:", "pbkdf2:sha256:")):
        return check_password_hash(stored_hash, password)
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def werkzeug_hash(password: str) -> str:
    """Legacy helper — prefer hash_password for new signups."""
    return generate_password_hash(password)


def account_has_password(stored_hash: str | None) -> bool:
    """True if the stored hash is a real password hash.

    Discord/Google-only accounts store the provider's numeric user id in the
    hash column, so they have no password a player could ever type.
    """
    return isinstance(stored_hash, str) and stored_hash.startswith(
        ("$2a$", "$2b$", "$2y$", "scrypt:", "pbkdf2:sha256:")
    )


def confirm_identity(stored_hash: str | None, username: str | None, submitted: str | None) -> bool:
    """Step-up confirmation for destructive account actions.

    Accounts with a password must enter it. Password-less (Discord/Google
    sign-in) accounts have nothing to type, so they confirm by typing their
    nation name exactly (case-insensitive) -- otherwise they could never
    delete or reset their account at all.
    """
    if not submitted:
        return False
    if account_has_password(stored_hash):
        return password_matches(stored_hash, submitted)
    return bool(username) and submitted.strip().lower() == username.strip().lower()
