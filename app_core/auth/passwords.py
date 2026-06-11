"""Shared password hashing and verification (bcrypt primary, werkzeug legacy)."""
from __future__ import annotations

import bcrypt
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    """Create a bcrypt hash for new accounts."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(14)).decode("utf-8")


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
