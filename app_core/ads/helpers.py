"""Helpers for player-submitted advertisements."""
from __future__ import annotations

import base64
import os
import re
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import requests
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

_AD_CACHE: Dict[str, Any] = {"loaded_at": 0.0, "payload": None}
_AD_CACHE_TTL = 60.0

_NSFW_SCORE_REJECT_THRESHOLD = 0.85


_NSFW_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _is_nsfw(image_bytes: bytes, ext: str = ".jpg") -> Optional[bool]:
    """Classify image bytes via Cloudmersive. Returns None if the check
    couldn't be performed (missing key, API error, timeout) so callers can
    fail open rather than block ad submissions on a third-party outage.

    Live-tested 2026-09-15 against the real free-tier API:
    - A valid image occasionally took >10s to respond under load, so the
      timeout below is 15s (not 10s) to cut down on spurious fail-opens
      from a merely-slow response rather than an actual outage.
    - Sending a generic "application/octet-stream" content-type made the
      API reject a genuinely valid PNG as "not a valid image type" (400)
      -- it needs the real image/* mime type matching the actual bytes."""
    api_key = os.getenv("CLOUDMERSIVE_API_KEY")
    if not api_key:
        return None
    mime = _NSFW_MIME_TYPES.get(ext.lower(), "image/jpeg")
    try:
        resp = requests.post(
            "https://api.cloudmersive.com/image/nsfw/classify",
            headers={"Apikey": api_key},
            files={"imageFile": (f"image{ext}", image_bytes, mime)},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("Successful"):
            return None
        return data.get("Score", 0.0) >= _NSFW_SCORE_REJECT_THRESHOLD
    except Exception:
        return None


def reset_ad_cache() -> None:
    """Clear cached ad rotation (tests and admin approve/reject)."""
    _AD_CACHE["loaded_at"] = 0.0
    _AD_CACHE["payload"] = None

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
        return f"/static/{raw}"
    return f"/static/uploads/ads/{raw}"


def save_ad_image_upload(
    upload: FileStorage, static_folder: str
) -> Tuple[bool, str, Optional[str]]:
    """Persist an uploaded ad image and return (ok, image_url_or_error, image_data_b64).

    Also base64-encodes the image for `advertisements.image_data` (migration
    0077) because static/uploads/ads/ lives on the web service's local disk,
    which Railway wipes on every redeploy -- any ad approved/pending across a
    redeploy lost its image (404), found 2026-09-15 via a broken preview in
    /admin/ads. The filesystem copy is kept as a same-deploy fast path only;
    the DB copy (served via ads.serve_ad_image) is canonical."""
    if not upload or not upload.filename:
        return False, "Advertisement image is required.", None

    filename = secure_filename(upload.filename)
    if not filename:
        return False, "Invalid image filename.", None

    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return False, "Image must be JPG, PNG, GIF, or WebP.", None

    # Extension alone is attacker-controlled (just the string after the last
    # "."), so this on its own doesn't verify the uploaded bytes are really
    # an image -- unlike countries.py/coalitions' flag uploads (which always
    # re-encode through Pillow), this saved raw upload bytes verbatim under
    # a public, guessable-format /static/uploads/ads/<uuid>.<ext> URL,
    # reachable by any @login_required player (found 2026-09-13, alongside
    # the target_url javascript: scheme issue in services.py). Validate the
    # actual file header via Pillow before persisting anything to disk.
    try:
        from PIL import Image

        upload.stream.seek(0)
        with Image.open(upload.stream) as img:
            img.verify()
    except Exception:
        return False, "File does not look like a valid image.", None
    upload.stream.seek(0)

    # Ads are shown in rotation to every visitor, not just the uploader, so
    # unlike flags (small, re-encoded, low stakes) this is worth an explicit
    # content check. Fails open (allows the upload) if CLOUDMERSIVE_API_KEY
    # is unset or the API errors/times out -- moderation is defense in depth
    # here, not the only gate, so a third-party outage shouldn't block ad
    # submissions entirely.
    image_bytes = upload.stream.read()
    upload.stream.seek(0)
    if _is_nsfw(image_bytes, ext):
        return False, "Image was flagged by content moderation. Please choose a different image.", None

    dest_dir = os.path.join(static_folder, "uploads", "ads")
    os.makedirs(dest_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    upload.save(os.path.join(dest_dir, stored_name))
    image_url = normalize_ad_image_url(stored_name) or f"/static/uploads/ads/{stored_name}"
    image_data = base64.b64encode(image_bytes).decode("ascii")
    return True, image_url, image_data


def load_rotating_ads(get_db_cursor) -> Dict[str, Optional[dict]]:
    """Fetch approved top/side ads with a short TTL cache."""
    now = time.time()
    cached = _AD_CACHE.get("payload")
    if cached is not None and now - _AD_CACHE["loaded_at"] < _AD_CACHE_TTL:
        return cached

    top_ad = None
    side_ad_left = None
    side_ad_right = None
    def _image_src(ad_id, image_data, image_url):
        # Prefer the DB-backed serve route (survives redeploys); fall back to
        # the raw stored URL only for rows uploaded before migration 0077
        # ever got a chance to backfill image_data.
        if image_data:
            return f"/ads/image/{ad_id}"
        return normalize_ad_image_url(image_url)

    try:
        with get_db_cursor(read_only=True) as db:
            db.execute(
                """
                SELECT id, image_url, target_url, image_data
                FROM advertisements
                WHERE status = 'approved' AND ad_type = 'top'
                ORDER BY RANDOM() LIMIT 1
                """
            )
            row = db.fetchone()
            if row:
                image_src = _image_src(row[0], row[3], row[1])
                if image_src:
                    top_ad = {"image_url": image_src, "target_url": row[2]}

            db.execute(
                """
                SELECT id, image_url, target_url, image_data
                FROM advertisements
                WHERE status = 'approved' AND ad_type = 'side'
                ORDER BY RANDOM() LIMIT 2
                """
            )
            side_rows = db.fetchall()
            if side_rows:
                left_src = _image_src(side_rows[0][0], side_rows[0][3], side_rows[0][1])
                if left_src:
                    side_ad_left = {
                        "image_url": left_src,
                        "target_url": side_rows[0][2],
                    }
                if len(side_rows) > 1:
                    right_src = _image_src(side_rows[1][0], side_rows[1][3], side_rows[1][1])
                    if right_src:
                        side_ad_right = {
                            "image_url": right_src,
                            "target_url": side_rows[1][2],
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
