import pytest
import email_verification


def test_generate_and_verify_cycle(monkeypatch):
    email = "user@example.test"
    token = email_verification.generate_verification(email, user_id=123, ttl=2)
    assert token

    # Pending should contain token
    pending = email_verification.list_pending()
    assert token in pending

    entry = email_verification.verify_code(token)
    assert entry is not None
    assert entry.email == email
    assert entry.user_id == 123

    # Subsequent verify should return None
    assert email_verification.verify_code(token) is None


def test_send_verification_email_monkeypatched(monkeypatch):
    sent = {}

    def fake_send_smtp(to_email, subject, body, **kwargs):
        sent["to"] = to_email
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(email_verification, "send_email_smtp", fake_send_smtp)

    token = email_verification.generate_verification("a@b.test")
    email_verification.send_verification_email("a@b.test", token)

    # Give background thread tiny time to call (monkeypatched function is quick)
    import time

    time.sleep(0.01)

    assert sent.get("to") == "a@b.test"
    assert token in sent.get("body", "")
