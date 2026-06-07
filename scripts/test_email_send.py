#!/usr/bin/env python3
"""Send a test email using configured SMTP or Resend. Usage: python3 scripts/test_email_send.py recipient@example.com"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from email_utils import is_email_configured, send_email, get_email_config


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/test_email_send.py <to_email>")
        return 1
    to_email = sys.argv[1].strip()
    cfg = get_email_config()
    print("configured:", is_email_configured())
    print("smtp_user:", cfg.get("user") or "(not set)")
    print("resend:", bool(os.getenv("RESEND_API_KEY")))
    ok = send_email(
        to_email,
        "Affairs and Order — email test",
        "<p>If you received this, email delivery is working.</p>",
        "If you received this, email delivery is working.",
    )
    print("sent:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
