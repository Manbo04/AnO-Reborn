"""Dynamic per-nation/coalition/province social preview images.

Discord (and every other link-unfurl consumer) only ever reads a page's
Open Graph tags — no JS, no interactivity runs inside a link embed. The
closest thing to "make the embed fun" is a real per-entity generated
image instead of the same static titleimage.png on every link. This
module renders that image with Pillow: a dark "dossier card" carrying
the entity's flag, name, and a few headline stats, in the site's own
brand colors (see .claude/skills/ano-ui-design/SKILL.md's token table).

Pure rendering only — no DB/Flask imports here, so it can be unit
tested/iterated on with a plain dict of stats. `routes.py` does the data
fetching and calls into this module.
"""

import os
from io import BytesIO
from typing import Iterable, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

CARD_W, CARD_H = 1200, 630

# Brand tokens (static/css/tokens.css .theme-dark block) — a generated
# image can't inherit CSS variables, so these are the dark-theme values
# copied by hand. Keep in sync if tokens.css's dark palette changes.
BG_TOP = (13, 16, 21)  # near --background dark #13171e, darkened for a card top
BG_BOTTOM = (26, 31, 41)  # near --foreground dark #1c2029
TEXT_PRIMARY = (224, 228, 234)  # --colorOne dark #e0e4ea
TEXT_SECONDARY = (138, 151, 171)  # muted dark-theme caption gray
BORDER = (58, 66, 82)
DEFAULT_ACCENT = (0, 167, 225)  # --accent #00a7e1 (constant across themes)
GOLD = (224, 184, 77)  # --gold dark #e0b84d

_FONT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "static", "fonts", "roboto-latin-variable.ttf"
)
_FAVICON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "static", "images", "favicon.png"
)
_DEFAULT_FLAG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "static", "flags", "default_flag.jpg"
)

_FONT_CACHE = {}
_WEIGHT_AXIS = {300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 900: "Black"}


def _font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    key = (size, weight)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    font = ImageFont.truetype(_FONT_PATH, size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        pass
    _FONT_CACHE[key] = font
    return font


def _hex_to_rgb(hex_color: Optional[str], fallback: Tuple[int, int, int] = DEFAULT_ACCENT) -> Tuple[int, int, int]:
    if not hex_color:
        return fallback
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return fallback
    try:
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def _lighten(color: Tuple[int, int, int], amount: float) -> Tuple[int, int, int]:
    return tuple(min(255, int(c + (255 - c) * amount)) for c in color)


def _vertical_gradient(size: Tuple[int, int], top: Tuple[int, int, int], bottom: Tuple[int, int, int]) -> Image.Image:
    w, h = size
    strip = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        strip.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return strip.resize((w, h))


def _diagonal_texture(size: Tuple[int, int], color: Tuple[int, int, int], alpha: int, spacing: int = 46) -> Image.Image:
    """Faint repeating diagonal hairlines — a "dossier/blueprint" texture."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    line_color = (*color, alpha)
    x = -h
    while x < w:
        draw.line([(x, h), (x + h, 0)], fill=line_color, width=1)
        x += spacing
    return layer


def _rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def _cover_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    return ImageOps.fit(img, (target_w, target_h), method=Image.LANCZOS, centering=(0.5, 0.5))


def _load_flag(flag_bytes: Optional[bytes]) -> Image.Image:
    try:
        if flag_bytes:
            return Image.open(BytesIO(flag_bytes)).convert("RGB")
    except Exception:
        pass
    return Image.open(_DEFAULT_FLAG_PATH).convert("RGB")


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    return draw.textlength(text, font=font)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, weight: int, max_width: int, start_size: int, min_size: int = 28) -> Tuple[str, ImageFont.FreeTypeFont]:
    size = start_size
    while size > min_size:
        font = _font(size, weight)
        if _text_width(draw, text, font) <= max_width:
            return text, font
        size -= 4
    font = _font(min_size, weight)
    while text and _text_width(draw, text + "…", font) > max_width:
        text = text[:-1]
    return (text + "…") if text else "", font


def _draw_soft_shadow(base: Image.Image, box: Tuple[int, int, int, int], radius: int, blur: int = 18, alpha: int = 130) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [x0, y0 + 8, x1, y1 + 8], radius=radius, fill=(0, 0, 0, alpha)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(shadow)


def render_card(
    *,
    kind_label: str,
    title: str,
    subtitle: Optional[str] = None,
    stats: Sequence[Tuple[str, str]] = (),
    flag_bytes: Optional[bytes] = None,
    accent_hex: Optional[str] = None,
    ribbon_text: Optional[str] = None,
) -> bytes:
    """Render a 1200x630 PNG "dossier card" and return raw PNG bytes.

    kind_label: small uppercase eyebrow, e.g. "NATION DOSSIER" / "COALITION" / "PROVINCE"
    title: the big headline (nation/coalition/province name)
    subtitle: one line under the title, e.g. "Led by {leader}"
    stats: up to 4 (label, value) pairs rendered as a stat row
    ribbon_text: optional small pill in the top-right, e.g. a coalition tag
    """
    accent = _hex_to_rgb(accent_hex)
    accent_soft = _lighten(accent, 0.55)

    base = _vertical_gradient((CARD_W, CARD_H), BG_TOP, BG_BOTTOM).convert("RGBA")
    base.alpha_composite(_diagonal_texture((CARD_W, CARD_H), accent, alpha=10))

    # Radial-ish glow behind the flag, accent-tinted
    glow = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    glow_core = Image.new("RGBA", (620, 620), (0, 0, 0, 0))
    ImageDraw.Draw(glow_core).ellipse([0, 0, 620, 620], fill=(*accent, 60))
    glow_core = glow_core.filter(ImageFilter.GaussianBlur(90))
    glow.alpha_composite(glow_core, (-160, -140))
    base.alpha_composite(glow)

    # Accent edge strip (brand recognizability even as a tiny thumbnail)
    ImageDraw.Draw(base).rectangle([0, 0, 10, CARD_H], fill=(*accent, 255))

    draw = ImageDraw.Draw(base)

    margin_x = 72
    flag_w, flag_h = 372, 248
    flag_x, flag_y = margin_x, (CARD_H - flag_h) // 2 - 10

    _draw_soft_shadow(base, (flag_x, flag_y, flag_x + flag_w, flag_y + flag_h), radius=18)
    draw = ImageDraw.Draw(base)

    flag_img = _cover_crop(_load_flag(flag_bytes), flag_w - 8, flag_h - 8).convert("RGBA")
    frame = Image.new("RGBA", (flag_w, flag_h), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle([0, 0, flag_w - 1, flag_h - 1], radius=18, fill=(*BG_BOTTOM, 255))
    inner_mask = _rounded_mask((flag_w - 8, flag_h - 8), 14)
    frame.paste(flag_img, (4, 4), inner_mask)
    border = Image.new("RGBA", (flag_w, flag_h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle([1, 1, flag_w - 2, flag_h - 2], radius=18, outline=(*accent, 255), width=3)
    frame.alpha_composite(border)
    base.alpha_composite(frame, (flag_x, flag_y))
    draw = ImageDraw.Draw(base)

    # Eyebrow / kind label
    text_x = flag_x + flag_w + 56
    text_top = flag_y - 10
    eyebrow_font = _font(24, 700)
    draw.text((text_x, text_top), kind_label.upper(), font=eyebrow_font, fill=accent_soft)
    eyebrow_w = _text_width(draw, kind_label.upper(), eyebrow_font)
    draw.line(
        [(text_x + eyebrow_w + 16, text_top + 16), (CARD_W - margin_x, text_top + 16)],
        fill=BORDER,
        width=2,
    )

    if ribbon_text:
        pill_font = _font(22, 600)
        pw = _text_width(draw, ribbon_text, pill_font) + 32
        px1, py1 = CARD_W - margin_x - pw, text_top - 6
        draw.rounded_rectangle([px1, py1, px1 + pw, py1 + 36], radius=18, fill=(*accent, 40), outline=(*accent, 200), width=2)
        draw.text((px1 + 16, py1 + 6), ribbon_text, font=pill_font, fill=accent_soft)

    # Title
    title_max_w = CARD_W - margin_x - text_x
    title_text, title_font = _fit_text(draw, title, 700, title_max_w, start_size=72, min_size=40)
    title_y = text_top + 46
    draw.text((text_x, title_y), title_text, font=title_font, fill=TEXT_PRIMARY)

    # Subtitle
    next_y = title_y + title_font.size + 14
    if subtitle:
        subtitle_text, subtitle_font = _fit_text(draw, subtitle, 500, title_max_w, start_size=30, min_size=20)
        draw.text((text_x, next_y), subtitle_text, font=subtitle_font, fill=accent_soft)
        next_y += subtitle_font.size + 26
    else:
        next_y += 16

    # Stat row
    if stats:
        stat_top = max(next_y, flag_y + flag_h - 118)
        _draw_stats(draw, text_x, stat_top, CARD_W - margin_x - text_x, stats)

    # Footer watermark: favicon + wordmark, bottom-right; tagline bottom-left
    footer_font = _font(22, 600)
    draw.text((margin_x, CARD_H - 54), "affairsandorder.org", font=footer_font, fill=TEXT_SECONDARY)

    wordmark_font = _font(26, 700)
    wordmark = "Affairs and Order"
    ww = _text_width(draw, wordmark, wordmark_font)
    try:
        icon = Image.open(_FAVICON_PATH).convert("RGBA")
        icon = icon.resize((34, 34), Image.LANCZOS)
        icon_x = int(CARD_W - margin_x - ww - 44)
        base.alpha_composite(icon, (icon_x, CARD_H - 60))
        draw = ImageDraw.Draw(base)
        draw.text((icon_x + 44, CARD_H - 54), wordmark, font=wordmark_font, fill=TEXT_PRIMARY)
    except Exception:
        draw.text((CARD_W - margin_x - ww, CARD_H - 54), wordmark, font=wordmark_font, fill=TEXT_PRIMARY)

    out = BytesIO()
    base.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def _draw_stats(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, stats: Sequence[Tuple[str, str]]) -> None:
    stats = list(stats)[:4]
    if not stats:
        return
    col_w = width // len(stats)
    label_font = _font(20, 600)
    value_font = _font(38, 700)
    for i, (label, value) in enumerate(stats):
        cx = x + i * col_w
        if i > 0:
            draw.line([(cx - 24, y - 4), (cx - 24, y + 66)], fill=BORDER, width=2)
        draw.text((cx, y), label.upper(), font=label_font, fill=TEXT_SECONDARY)
        value_text, vfont = _fit_text(draw, value, 700, col_w - 32, start_size=38, min_size=24)
        draw.text((cx, y + 28), value_text, font=vfont, fill=(255, 255, 255))


def render_fallback_card() -> bytes:
    """Generic branded card for pages with no single entity (used nowhere
    yet — layout.html keeps its static titleimage.png default; this exists
    so future non-entity pages can opt in without a new code path)."""
    return render_card(
        kind_label="MMO Nation Game",
        title="Affairs and Order",
        subtitle="Build a nation. Trade, ally, or go to war.",
        stats=(),
    )
