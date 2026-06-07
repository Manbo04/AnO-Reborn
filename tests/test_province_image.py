"""Province custom banner image upload and serving."""

import base64
from io import BytesIO

import pytest


def _tiny_png():
    # 1x1 PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


def test_serve_province_image_default(client):
    res = client.get("/province-image/999999")
    assert res.status_code == 200
    assert res.mimetype in ("image/jpeg", "image/png")


def test_update_province_image_requires_login(client):
    res = client.post("/province/1/image")
    assert res.status_code in (302, 401, 403)


def test_compress_province_image_roundtrip():
    from helpers import compress_province_image
    from werkzeug.datastructures import FileStorage

    buf = BytesIO(_tiny_png())
    fs = FileStorage(buf, filename="test.png", content_type="image/png")
    image_data, ext = compress_province_image(fs)
    assert ext == "jpg"
    assert image_data
    assert base64.b64decode(image_data)
