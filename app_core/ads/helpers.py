"""Helpers for player-submitted advertisements."""
from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from flask import url_for
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

_AD_CACHE: Dict[str, Any] = {"loaded_at": 0.0, "payload": None}
_AD_CACHE_TTL = 60.0

_DISCORD_SNOWFLAKE = re.compile(r"^\d{17,20}$")


def normalize_ad_image_url(image_url: str | None) -> str | None:
    """Return a browser-loadable image URL for an advertisement."""
    if not image_url or not str(image_url).strip():
        return None
    raw = str(image_url).strip()
    if raw.startswith(("http://", "https://", "//", "/")):
        return raw
    if raw.startswith("static/"):
        return f"/{raw}"
    if raw.startswith("uploads/ads/"):
        return url_for("static", filename=raw)
    return url_for("static", filename=f"uploads/ads/{raw}")


def save_ad_image_upload(
    upload: FileStorage, static_folder: str
) -> Tuple[bool, str]:
    """Persist an uploaded ad image under static/uploads/ads/."""
    if not upload or not upload.filename:
        return False, "Advertisement image is required."

    filename = secure_filename(upload.filename)
    if not filename:
        return False, "Invalid image filename."

    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return False, "Image must be JPG, PNG, GIF, or WebP."

    dest_dir = os.path.join(static_folder, "uploads", "ads")
    os.makedirs(dest_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    upload.save(os.path.join(dest_dir, stored_name))
    return True, normalize_ad_image_url(stored_name) or f"/static/uploads/ads/{stored_name}"


def load_rotating_ads(get_db_cursor) -> Dict[str, Optional[dict]]:
    """Fetch approved top/side ads with a short TTL cache."""
    now = time.time()
    cached = _AD_CACHE.get("payload")
    if cached is not None and now - _AD_CACHE["loaded_at"] < _AD_CACHE_TTL:
        return cached

    top_ad = None
    side_ad_left = None
    side_ad_right = None
    try:
        with get_db_cursor(read_only=True) as db:
            db.execute(
                """
                SELECT image_url, target_url
                FROM advertisements
                WHERE status = 'approved' AND ad_type = 'top'
                ORDER BY RANDOM() LIMIT 1
                """
            )
            row = db.fetchone()
            if row:
                image_url = normalize_ad_image_url(row[0])
                if image_url:
                    top_ad = {"image_url": image_url, "target_url": row[1]}

            db.execute(
                """
                SELECT image_url, target_url
                FROM advertisements
                WHERE status = 'approved' AND ad_type = 'side'
                ORDER BY RANDOM() LIMIT 2
                """
            )
            side_rows = db.fetchall()
            if side_rows:
                left_url = normalize_ad_image_url(side_rows[0][0])
                if left_url:
                    side_ad_left = {
                        "image_url": left_url,
                        "target_url": side_rows[0][1],
                    }
                if len(side_rows) > 1:
                    right_url = normalize_ad_image_url(side_rows[1][0])
                    if right_url:
                        side_ad_right = {
                            "image_url": right_url,
                            "target_url": side_rows[1][1],
                        }
    except Exception:
        pass

    payload = {
        "top_ad": top_ad,
        "side_ad_left": side_ad_left,
        "side_ad_right": side_ad_right,
    }
    _AD_CACHE["loaded_at"] = now
    _AD_CACHE["payload"] = payload
    return payload


def is_discord_snowflake(value: str | None) -> bool:
    return bool(value and _DISCORD_SNOWFLAKE.match(str(value).strip()))
