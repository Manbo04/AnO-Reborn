"""Real TOTP (RFC 6238) two-factor authentication.

Following the 2026-09 account-takeover incident (session-invalidation bugs, a
cache leak that bled session identity across visitors, and a `reset_account`
endpoint that could wipe an account with no re-confirmation), this module
adds an actual second factor -- opt-in per account -- that gates all three
login paths (password, Discord OAuth, Google OAuth). A compromised password
or a compromised Discord/Google session alone is no longer enough to fully
control an account once this is enabled.

Single place for all TOTP crypto/DB logic. Used by `login.py`,
`app_core/auth/google_auth.py`, and `app_core/auth/routes.py`.

**Secret storage**: `totp_secret_encrypted` is Fernet-encrypted, not
bcrypt-hashed -- unlike a password, the server must recover the raw secret
every request to recompute the expected code. Backup codes ARE
bcrypt-hashed (compare-once-and-discard, like a password).

**Encryption key**: the Fernet key is HKDF-derived from the existing
Flask `SECRET_KEY` -- no new env var to provision (this incident's own
regressions, e.g. `THEME_V2_PAGES` and `RECAPTCHA_SECRET_KEY`, were exactly
this class of "forgot to set an env var" mistake). Fails closed: if
`SECRET_KEY` is somehow unavailable at call time, `_fernet_key()` raises
rather than ever storing a secret in plaintext. Callers (routes) should
catch this and flash "Two-factor authentication is temporarily unavailable"
rather than letting it 500.
"""

import base64
import logging
import secrets
from io import BytesIO

import bcrypt
import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app

from database import bump_session_epoch, get_request_cursor, users_table_has_column

logger = logging.getLogger(__name__)

BACKUP_CODE_COUNT = 10

# Fixed, non-secret HKDF parameters. SECRET_KEY itself is the actual secret
# input -- the salt/info here just domain-separate this derived key from any
# other value ever derived from SECRET_KEY (e.g. the Flask session-signing
# key), they don't need to be secret themselves.
_HKDF_SALT = b"ano-totp-hkdf-salt-v1"
_HKDF_INFO = b"ano-totp-secret-v1"


class TwoFactorUnavailableError(RuntimeError):
    """Raised when the TOTP encryption key can't be derived (SECRET_KEY
    missing). Callers must flash a friendly message, never store a secret
    in plaintext as a fallback."""


def _fernet_key() -> bytes:
    try:
        secret = current_app.config.get("SECRET_KEY")
    except RuntimeError:
        secret = None
    if not secret:
        raise TwoFactorUnavailableError(
            "SECRET_KEY unavailable; cannot derive TOTP encryption key"
        )
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT, info=_HKDF_INFO)
    return base64.urlsafe_b64encode(hkdf.derive(secret))


def _fernet() -> Fernet:
    return Fernet(_fernet_key())


def _encrypt_secret(raw_secret: str) -> str:
    return _fernet().encrypt(raw_secret.encode("utf-8")).decode("utf-8")


def _decrypt_secret(encrypted: str) -> str:
    return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")


def has_2fa_enabled(user_id: int) -> bool:
    """True if this account has TOTP 2FA turned on. Fails closed to False
    (no gate) on any error -- an outage here must never lock every player
    out of login, same philosophy as ip_is_known_for_user."""
    if not users_table_has_column("totp_enabled"):
        return False
    try:
        with get_request_cursor() as db:
            db.execute("SELECT totp_enabled FROM users WHERE id=%s", (user_id,))
            row = db.fetchone()
        return bool(row and row[0])
    except Exception:
        logger.exception("has_2fa_enabled check failed for user_id=%s", user_id)
        return False


def start_or_resume_enrollment(db, user_id: int) -> str:
    """Return the raw (never-persisted-in-plaintext) secret to enroll with.

    Reuses an existing unconfirmed secret if one exists, so a mistyped
    confirmation code doesn't force the player to re-scan a brand new QR.
    """
    db.execute(
        "SELECT totp_secret_encrypted, totp_enabled FROM users WHERE id=%s",
        (user_id,),
    )
    row = db.fetchone()
    if row and row[0] and not row[1]:
        try:
            return _decrypt_secret(row[0])
        except InvalidToken:
            logger.warning(
                "start_or_resume_enrollment: undecryptable existing secret "
                "for user_id=%s, generating a fresh one",
                user_id,
            )

    raw_secret = pyotp.random_base32()
    encrypted = _encrypt_secret(raw_secret)
    db.execute(
        "UPDATE users SET totp_secret_encrypted=%s, totp_enabled=FALSE WHERE id=%s",
        (encrypted, user_id),
    )
    return raw_secret


def build_qr_data_uri(secret: str, account_label: str) -> str:
    """Render the enrollment QR as a `data:` URI. No dedicated
    image-serving route -- that would leak the secret into a URL/logs and
    need a second decrypt round-trip."""
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=account_label, issuer_name="Affairs and Order"
    )
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _generate_backup_codes(db, user_id: int) -> list:
    """Replace any existing backup codes with a fresh set of 10, returning
    the plaintext codes (shown once, never persisted in plaintext)."""
    db.execute("DELETE FROM totp_backup_codes WHERE user_id=%s", (user_id,))
    plaintext_codes = []
    for _ in range(BACKUP_CODE_COUNT):
        raw = secrets.token_hex(4)
        code = f"{raw[:4]}-{raw[4:]}"
        code_hash = bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db.execute(
            "INSERT INTO totp_backup_codes (user_id, code_hash) VALUES (%s, %s)",
            (user_id, code_hash),
        )
        plaintext_codes.append(code)
    return plaintext_codes


def confirm_enrollment(db, user_id: int, code: str):
    """Verify the enrollment code and, on success, flip 2FA on and issue
    backup codes. Returns the 10 plaintext backup codes on success, or
    `None` on a bad/missing code (enrollment stays unconfirmed either way,
    so the caller can let the player retry against the same secret)."""
    db.execute("SELECT totp_secret_encrypted FROM users WHERE id=%s", (user_id,))
    row = db.fetchone()
    if not row or not row[0]:
        return None
    try:
        secret = _decrypt_secret(row[0])
    except InvalidToken:
        logger.warning("confirm_enrollment: undecryptable secret for user_id=%s", user_id)
        return None

    code = (code or "").strip()
    if not code or not pyotp.TOTP(secret).verify(code, valid_window=1):
        return None

    db.execute(
        "UPDATE users SET totp_enabled=TRUE, totp_enrolled_at=NOW() WHERE id=%s",
        (user_id,),
    )
    codes = _generate_backup_codes(db, user_id)
    # This is as much an "I think I might be compromised" moment as
    # disabling -- force-kill any other lingering session on this account.
    bump_session_epoch(db, user_id)
    return codes


def verify_login_code(user_id: int, code: str) -> bool:
    """TOTP check first; on failure, fall back to an unused backup code
    (bcrypt-compared, small table so a loop is fine), marking it used on a
    match so it can't be replayed."""
    code = (code or "").strip()
    if not code:
        return False

    with get_request_cursor() as db:
        db.execute(
            "SELECT totp_secret_encrypted, totp_enabled FROM users WHERE id=%s",
            (user_id,),
        )
        row = db.fetchone()
        if not row or not row[1] or not row[0]:
            return False

        secret = None
        try:
            secret = _decrypt_secret(row[0])
        except InvalidToken:
            logger.warning("verify_login_code: undecryptable secret for user_id=%s", user_id)

        if secret and pyotp.TOTP(secret).verify(code, valid_window=1):
            return True

        db.execute(
            "SELECT id, code_hash FROM totp_backup_codes "
            "WHERE user_id=%s AND used_at IS NULL",
            (user_id,),
        )
        candidates = db.fetchall()
        code_bytes = code.encode("utf-8")
        for row_id, code_hash in candidates:
            try:
                stored = code_hash.encode("utf-8") if isinstance(code_hash, str) else code_hash
                if bcrypt.checkpw(code_bytes, stored):
                    db.execute(
                        "UPDATE totp_backup_codes SET used_at=NOW() WHERE id=%s",
                        (row_id,),
                    )
                    return True
            except (ValueError, TypeError):
                continue

    return False


def disable_2fa(db, user_id: int) -> None:
    """Wipe the secret and backup codes, and force-kill every other
    session on this account (reuse database.py's bump_session_epoch, same
    pattern as set_user_password -- disabling 2FA is a security-relevant
    account change just like a password change)."""
    db.execute(
        "UPDATE users SET totp_secret_encrypted=NULL, totp_enabled=FALSE, "
        "totp_enrolled_at=NULL WHERE id=%s",
        (user_id,),
    )
    db.execute("DELETE FROM totp_backup_codes WHERE user_id=%s", (user_id,))
    bump_session_epoch(db, user_id)
