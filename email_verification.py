"""Simple email verification helper

Features:
- generate_verification(email, user_id=None): generates a verification token, stores it in an in-memory TTL store and (optionally) sends the verification email asynchronously
- send_verification_email(email, token): small wrapper to send a verification email containing a clickable URL
- verify_code(token): validate a token, return the associated payload (email, user_id) and remove it
- The store automatically expires entries after EMAIL_VERIFICATION_TTL seconds via a background cleanup thread

Notes for you:
- This uses the standard library `smtplib` + `email.message.EmailMessage` so no new dependencies are required.
- Configure SMTP via env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
- Configure verification TTL via EMAIL_VERIFICATION_TTL (seconds) and the base URL via VERIFICATION_BASE_URL or the existing `init.BASE_URL` if available.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
import smtplib
from typing import Optional, Dict, Any

# Configuration
DEFAULT_TTL = int(os.getenv("EMAIL_VERIFICATION_TTL", str(60 * 60)))  # 1 hour default
CLEANUP_INTERVAL = int(
    os.getenv("EMAIL_VERIFICATION_CLEANUP_INTERVAL", str(60))
)  # run cleanup every minute
VERIFICATION_BASE_URL = os.getenv(
    "VERIFICATION_BASE_URL"
)  # optional; fallback to /verify_email/<token>

# SMTP env vars (examples): SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@example.com")

# Basic helpers and data model
_cleanup_thread_started = False


@dataclass
class VerificationEntry:
    email: str
    user_id: Optional[int]
    expires_at: float
    created_at: float
    metadata: Dict[str, Any]


def _now_ts() -> float:
    return time.time()


def _generate_token(nbytes: int = 24) -> str:
    # URL-safe token
    return secrets.token_urlsafe(nbytes)


def _cleanup_loop() -> None:
    while True:
        time.sleep(CLEANUP_INTERVAL)
        try:
            _cleanup_expired()
        except Exception:
            pass


# Pluggable verification store interface + implementations (in-memory default, optional postgres)

import json
from typing import Protocol, Tuple


class VerificationStore(Protocol):
    def create(self, token: str, entry: VerificationEntry) -> None:
        """Persist a token -> entry mapping."""

    def get_and_remove(self, token: str) -> Optional[VerificationEntry]:
        """Return and remove token entry, or None if missing/expired."""

    def list_pending(self) -> Dict[str, VerificationEntry]:
        """Return a shallow mapping for inspection."""

    def cleanup(self) -> None:
        """Remove expired entries."""


# In-memory implementation (default)
class InMemoryStore:
    def __init__(self):
        self._store: Dict[str, VerificationEntry] = {}
        self._lock = threading.Lock()

    def create(self, token: str, entry: VerificationEntry) -> None:
        with self._lock:
            self._store[token] = entry

    def get_and_remove(self, token: str) -> Optional[VerificationEntry]:
        with self._lock:
            entry = self._store.get(token)
            if not entry:
                return None
            if entry.expires_at < _now_ts():
                del self._store[token]
                return None
            del self._store[token]
            return entry

    def list_pending(self) -> Dict[str, VerificationEntry]:
        with self._lock:
            return dict(self._store)

    def cleanup(self) -> None:
        with self._lock:
            now = _now_ts()
            expired = [k for k, v in self._store.items() if v.expires_at < now]
            for k in expired:
                del self._store[k]


# Optional Postgres-backed store (requires a migration to create the table)
class PostgresStore:
    """Simple Postgres-backed store for persistence across restarts.

    Table schema expected (see scripts/create_email_verifications_table.py):
    CREATE TABLE email_verifications (
        token TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        user_id INTEGER,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        metadata JSONB
    );
    """

    def __init__(self):
        # Lazy import to avoid circular imports at module load
        from database import get_db_connection

        self.get_db_connection = get_db_connection

    def create(self, token: str, entry: VerificationEntry) -> None:
        import json

        ts_exp = datetime.utcfromtimestamp(entry.expires_at)
        ts_created = datetime.utcfromtimestamp(entry.created_at)
        mjson = json.dumps(entry.metadata or {})
        with self.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO email_verifications (token, email, user_id, expires_at, created_at, metadata) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (token) DO UPDATE SET email=EXCLUDED.email, user_id=EXCLUDED.user_id, expires_at=EXCLUDED.expires_at, created_at=EXCLUDED.created_at, metadata=EXCLUDED.metadata",
                (token, entry.email, entry.user_id, ts_exp, ts_created, mjson),
            )
            conn.commit()

    def get_and_remove(self, token: str) -> Optional[VerificationEntry]:
        with self.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT email, user_id, expires_at, created_at, metadata FROM email_verifications WHERE token=%s",
                (token,),
            )
            row = cur.fetchone()
            if not row:
                return None
            ts_exp = row[2]
            if ts_exp.timestamp() < _now_ts():
                cur.execute("DELETE FROM email_verifications WHERE token=%s", (token,))
                conn.commit()
                return None
            cur.execute("DELETE FROM email_verifications WHERE token=%s", (token,))
            conn.commit()
            metadata = json.loads(row[4]) if row[4] else {}
            return VerificationEntry(
                email=row[0],
                user_id=row[1],
                expires_at=ts_exp.timestamp(),
                created_at=row[3].timestamp(),
                metadata=metadata,
            )

    def list_pending(self) -> Dict[str, VerificationEntry]:
        with self.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT token, email, user_id, expires_at, created_at, metadata FROM email_verifications"
            )
            rows = cur.fetchall()
            out: Dict[str, VerificationEntry] = {}
            for r in rows:
                metadata = json.loads(r[5]) if r[5] else {}
                out[r[0]] = VerificationEntry(
                    email=r[1],
                    user_id=r[2],
                    expires_at=r[3].timestamp(),
                    created_at=r[4].timestamp(),
                    metadata=metadata,
                )
            return out

    def cleanup(self) -> None:
        with self.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM email_verifications WHERE expires_at < now()")
            conn.commit()


# Factory to choose store implementation
_store_impl: VerificationStore
_backend = os.getenv("EMAIL_VERIFICATION_BACKEND", "memory").lower()
if _backend == "postgres":
    try:
        _store_impl = PostgresStore()
    except Exception:
        # Fallback to memory if Postgres isn't available at import time
        _store_impl = InMemoryStore()
else:
    _store_impl = InMemoryStore()


def send_email_smtp(
    to_email: str,
    subject: str,
    body: str,
    *,
    smtp_host: str = SMTP_HOST,
    smtp_port: int = SMTP_PORT,
    smtp_user: Optional[str] = SMTP_USER,
    smtp_password: Optional[str] = SMTP_PASSWORD,
    smtp_from: str = SMTP_FROM,
) -> None:
    """Send a simple text email via SMTP. Raises on failure."""
    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    # Basic SMTP with optional login. For production you may want TLS/SSL or an external provider.
    try:
        if smtp_port in (587, 25):
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.ehlo()
                if s.has_extn("starttls"):
                    s.starttls()
                    s.ehlo()
                if smtp_user and smtp_password:
                    s.login(smtp_user, smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as s:
                if smtp_user and smtp_password:
                    s.login(smtp_user, smtp_password)
                s.send_message(msg)
    except Exception:
        # Bubble up or log in real system; for tests we let errors surface
        raise


def _build_verification_url(token: str) -> str:
    if VERIFICATION_BASE_URL:
        base = VERIFICATION_BASE_URL.rstrip("/")
        return f"{base}/{token}"

    try:
        from init import BASE_URL  # type: ignore

        base = BASE_URL.rstrip("/")
        return f"{base}/verify_email/{token}"
    except Exception:
        return f"/verify_email/{token}"


def send_verification_email(
    email: str,
    token: str,
    subject: Optional[str] = None,
    prebuilt_url: Optional[str] = None,
) -> None:
    """Send the verification email asynchronously (background thread)."""
    if subject is None:
        subject = "Please verify your email"
    url = prebuilt_url or _build_verification_url(token)

    body = (
        f"Please verify your email by visiting the following link:\n\n{url}\n\nIf you did not request this, ignore this message."
        f"\n\nVerification code: {token}\n"
    )

    # Send in background so calling thread is not blocked
    t = threading.Thread(
        target=lambda: send_email_smtp(email, subject, body), daemon=True
    )
    t.start()


def generate_verification(
    email: str,
    user_id: Optional[int] = None,
    ttl: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Create and store a verification token, and return it.

    The implementation stores to the configured backend (memory by default). This does NOT send the email automatically; call send_verification_email() if you want to email it.
    """
    if ttl is None:
        ttl = DEFAULT_TTL
    if metadata is None:
        metadata = {}

    token = _generate_token()
    now = _now_ts()
    entry = VerificationEntry(
        email=email,
        user_id=user_id,
        expires_at=now + ttl,
        created_at=now,
        metadata=metadata,
    )

    _store_impl.create(token, entry)
    _start_cleanup_thread_once()
    return token


def verify_code(token: str) -> Optional[VerificationEntry]:
    """Verify a token. If valid and not expired, remove it from the store and return the entry. Otherwise return None."""
    return _store_impl.get_and_remove(token)


def _cleanup_expired() -> None:
    _store_impl.cleanup()


def _start_cleanup_thread_once() -> None:
    global _cleanup_thread_started
    if not _cleanup_thread_started:
        t = threading.Thread(target=_cleanup_loop, daemon=True)
        t.start()
        _cleanup_thread_started = True


# Utility functions for debugging/inspection (not required for production)
def list_pending() -> Dict[str, VerificationEntry]:
    """Return a shallow copy of pending tokens (for admin/debug)."""
    return _store_impl.list_pending()


# Exported API: generate_verification, send_verification_email, verify_code, list_pending
__all__ = [
    "generate_verification",
    "send_verification_email",
    "verify_code",
    "send_email_smtp",
    "list_pending",
]
