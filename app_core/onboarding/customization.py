"""Nation customization chosen on the signup page (templates/signup.html, step 3).

Applied once, right after a new account's game data is initialised, for every
signup path (email form, Discord, Google) via signup.init_user_game_data().
Everything here is cosmetic and optional: each field is length-capped to the
same widths countries.update_info() enforces, and any failure is swallowed so
a bad flag image can never block an account from being created.
"""

import base64
import binascii
import logging
from io import BytesIO

logger = logging.getLogger(__name__)

# Same caps as countries.update_info() / the DB column widths.
_TEXT_FIELDS = (
    ("leader_name", 60),
    ("currency_name", 40),
    ("ruling_party", 60),
)
_CAPITAL_MAX = 40
_DESCRIPTION_MAX = 1000
# The signup flag designer exports a ~300x200 PNG; anything far bigger than
# that is not from our page.
_FLAG_MAX_BYTES = 400_000
_DATA_URL_PREFIX = "data:image/png;base64,"


def _decode_flag(data_url: str):
    """Return (base64_jpeg, ext) for a designer-exported PNG data URL, or None."""
    if not data_url or not data_url.startswith(_DATA_URL_PREFIX):
        return None
    try:
        raw = base64.b64decode(data_url[len(_DATA_URL_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        return None
    if not raw or len(raw) > _FLAG_MAX_BYTES:
        return None
    try:
        from PIL import Image

        # Verify it really is an image before handing it to the compressor.
        Image.open(BytesIO(raw)).verify()
    except Exception:
        return None
    from werkzeug.datastructures import FileStorage
    from helpers import compress_flag_image

    return compress_flag_image(
        FileStorage(stream=BytesIO(raw), filename="flag.png"), max_size=300, quality=85
    )


def apply_signup_customization(db, user_id: int, form) -> None:
    """Persist the optional nation customization submitted with the signup form."""
    if form is None:
        return
    try:
        db.execute("SAVEPOINT signup_customization")

        for field, max_len in _TEXT_FIELDS:
            value = (form.get(field) or "").strip()[:max_len]
            if value:
                # field comes from the fixed whitelist above, never from input.
                db.execute(f"UPDATE users SET {field}=%s WHERE id=%s", (value, user_id))

        description = (form.get("description") or "").strip()[:_DESCRIPTION_MAX]
        if description:
            db.execute(
                "UPDATE users SET description=%s WHERE id=%s", (description, user_id)
            )

        capital = (form.get("capital_name") or "").strip()[:_CAPITAL_MAX]
        # The free starter province (onboarding.service.ensure_starter_province)
        # becomes the named capital.
        db.execute(
            "SELECT id FROM provinces WHERE userId=%s ORDER BY id LIMIT 1", (user_id,)
        )
        row = db.fetchone()
        if row:
            pid = row["id"] if isinstance(row, dict) else row[0]
            if capital:
                db.execute(
                    "UPDATE provinces SET provinceName=%s WHERE id=%s", (capital, pid)
                )
            db.execute(
                "UPDATE provinces SET is_capital = FALSE WHERE userId=%s AND id<>%s",
                (user_id, pid),
            )
            db.execute("UPDATE provinces SET is_capital = TRUE WHERE id=%s", (pid,))

        flag = _decode_flag(form.get("flag_png") or "")
        if flag:
            flag_data, ext = flag
            db.execute(
                "UPDATE users SET flag=%s, flag_data=%s WHERE id=%s",
                (f"flag_{user_id}.{ext}", flag_data, user_id),
            )

        db.execute("RELEASE SAVEPOINT signup_customization")
    except Exception as exc:
        try:
            db.execute("ROLLBACK TO SAVEPOINT signup_customization")
        except Exception:
            pass
        logger.warning("signup customization failed for %s: %s", user_id, exc)
