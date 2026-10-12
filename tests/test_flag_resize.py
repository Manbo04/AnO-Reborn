import io
from PIL import Image


def _jpeg(w, h):
    buf = io.BytesIO()
    Image.effect_noise((w, h), 80).convert("RGB").save(buf, "JPEG", quality=95)
    return buf.getvalue()


def test_oversized_flag_is_downscaled():
    from app_core.main.routes import _shrink_flag_bytes
    raw = _jpeg(2000, 1300)
    assert len(raw) > 40_000
    out, mime = _shrink_flag_bytes(raw, "image/jpeg")
    img = Image.open(io.BytesIO(out))
    assert max(img.size) <= 300 and mime == "image/jpeg" and len(out) < len(raw) // 10


def test_small_flag_and_garbage_untouched():
    from app_core.main.routes import _shrink_flag_bytes
    small = _jpeg(100, 60)
    assert _shrink_flag_bytes(small, "image/jpeg") == (small, "image/jpeg")
    junk = b"x" * 100_000
    assert _shrink_flag_bytes(junk, "image/png") == (junk, "image/png")


def test_flag_route_is_publicly_cacheable_only_on_success():
    from app import resolve_cache_control
    assert resolve_cache_control("/flag/country/1", 200, None) == "public, max-age=600, must-revalidate"
    assert resolve_cache_control("/flag/country/1", 403, None).startswith("private")
