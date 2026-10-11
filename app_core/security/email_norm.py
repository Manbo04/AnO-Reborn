"""Email canonicalisation + disposable-domain screening for signup."""
from __future__ import annotations

_GMAIL = {"gmail.com", "googlemail.com"}

# Common throwaway providers. Not exhaustive; extend as abuse shows up.
DISPOSABLE_DOMAINS = frozenset("""
mailinator.com guerrillamail.com guerrillamail.net guerrillamail.org sharklasers.com
grr.la 10minutemail.com 10minutemail.net tempmail.com temp-mail.org temp-mail.io
tempmail.net tempmailo.com throwawaymail.com yopmail.com yopmail.net yopmail.fr
trashmail.com trashmail.net getnada.com nada.email dispostable.com maildrop.cc
mailnesia.com mintemail.com mohmal.com emailondeck.com fakeinbox.com spamgourmet.com
moakt.com mytemp.email burnermail.io discard.email discardmail.com anonbox.net
tmpmail.org tmpmail.net tempr.email tempinbox.com spambox.us getairmail.com
mailcatch.com mail-temp.com inboxkitten.com harakirimail.com emailfake.com
fakemail.net fakemailgenerator.com tmail.ws mailtemp.info 1secmail.com 1secmail.net
1secmail.org esiix.com wwjmp.com xojxe.com yoggm.com vjuum.com laafd.com
""".split())


def canonical_email(email: str) -> str:
    """Lowercase; strip +tag; remove dots and unify domain for Gmail."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return email
    local, _, domain = email.rpartition("@")
    local = local.split("+", 1)[0]
    if domain in _GMAIL:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def is_disposable(email: str) -> bool:
    domain = (email or "").strip().lower().rpartition("@")[2]
    return domain in DISPOSABLE_DOMAINS


# SQL twin of canonical_email() for matching existing rows.
CANONICAL_SQL = """
CASE
  WHEN split_part(lower(email), '@', 2) IN ('gmail.com', 'googlemail.com')
    THEN replace(split_part(split_part(lower(email), '@', 1), '+', 1), '.', '') || '@gmail.com'
  ELSE split_part(split_part(lower(email), '@', 1), '+', 1) || '@' || split_part(lower(email), '@', 2)
END
"""
