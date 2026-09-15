"""Dynamic per-nation/coalition/province social preview images.

Discord (and every other link-unfurl consumer) only ever reads a page's
Open Graph tags — no JS, no interactivity runs inside a link embed. The
closest thing to "make the embed fun" is a real per-entity generated
image instead of the same static titleimage.png on every link. This
module renders that image with Pillow: a dark "dossier card" carrying
the entity's flag, name, and a few headline stats, in the site's own
brand colors (see .claude/skills/ano-ui-design/SKILL.md's token table).

Rendered as a short looping animated GIF — Discord's link-unfurl embed
image animates a GIF fetched from og:image exactly like a directly-pasted
.gif link does, so a subtle shimmer/drift reads as "alive" instead of a
static screenshot. `render_card` (single static frame) is kept for
render_fallback_card and any non-Discord consumer that wants a plain PNG.

Pure rendering only — no DB/Flask imports here, so it can be unit
tested/iterated on with a plain dict of stats. `routes.py` does the data
fetching and calls into this module.
"""

import math
import os
from io import BytesIO
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

CARD_W, CARD_H = 1200, 630

# Animation tuning: a short, gentle loop — enough to read as "moving" in a
# Discord embed without looking distracting or bloating the GIF's byte size.
# (Tuned against real uploaded flags, which are often photo-like and dither
# noisily: 8 frames / 128-color palette keeps typical output around 1-1.5MB
# instead of 2MB+ at 12 frames / 192 colors, with no visible quality loss.)
GIF_FRAMES = 8
GIF_FRAME_MS = 130
GIF_PALETTE_COLORS = 128

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


def _diagonal_texture(
    size: Tuple[int, int], color: Tuple[int, int, int], alpha: int, spacing: int = 46, offset: float = 0.0
) -> Image.Image:
    """Faint repeating diagonal hairlines — a "dossier/blueprint" texture.
    `offset` (0..1, fraction of `spacing`) shifts the pattern horizontally,
    used across animation frames to make it scroll slowly."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    line_color = (*color, alpha)
    start = -h + (offset % 1.0) * spacing
    x = start
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


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    while text and _text_width(draw, text + "…", font) > max_width:
        text = text[:-1]
    return (text + "…") if text else ""


def _draw_soft_shadow(base: Image.Image, box: Tuple[int, int, int, int], radius: int, blur: int = 18, alpha: int = 130) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [x0, y0 + 8, x1, y1 + 8], radius=radius, fill=(0, 0, 0, alpha)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    base.alpha_composite(shadow)


def _soft_particles(size: Tuple[int, int], accent: Tuple[int, int, int], phase: float, seed_area: Tuple[int, int, int, int]) -> Image.Image:
    """A handful of slow-drifting soft accent-tinted bokeh dots, confined to
    `seed_area` (kept clear of the text/stat columns) — background "life"
    for the animated loop, not a focal element."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ax0, ay0, ax1, ay1 = seed_area
    aw, ah = ax1 - ax0, ay1 - ay0
    particles = [
        (0.15, 0.30, 30, 0.9, 0.0),
        (0.55, 0.70, 22, 1.3, 0.35),
        (0.80, 0.20, 26, 0.7, 0.6),
        (0.35, 0.85, 18, 1.1, 0.85),
    ]
    for fx, fy, radius, speed, phase_off in particles:
        t = (phase * speed + phase_off) % 1.0
        cx = ax0 + fx * aw + 14 * math.sin(2 * math.pi * t)
        cy = ay0 + fy * ah + 10 * math.cos(2 * math.pi * t)
        alpha = int(26 + 14 * math.sin(2 * math.pi * t + phase_off * 6))
        dot = Image.new("RGBA", (radius * 6, radius * 6), (0, 0, 0, 0))
        ImageDraw.Draw(dot).ellipse(
            [radius, radius, radius * 5, radius * 5], fill=(*accent, max(0, alpha))
        )
        dot = dot.filter(ImageFilter.GaussianBlur(radius * 0.7))
        layer.alpha_composite(dot, (int(cx - radius * 3), int(cy - radius * 3)))
    return layer


def _flag_shimmer(size: Tuple[int, int], phase: float) -> Image.Image:
    """A soft diagonal light band that sweeps once across the flag per loop
    — a subtle "foil card" glint rather than a constant back-and-forth scan."""
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    band_w = 70
    travel = w + h + band_w * 2
    band_x = -h - band_w + phase * travel
    draw = ImageDraw.Draw(layer)
    draw.line([(band_x, h), (band_x + h, 0)], fill=(255, 255, 255, 60), width=band_w)
    return layer.filter(ImageFilter.GaussianBlur(14))


def _compose_frame(
    *,
    kind_label: str,
    title: str,
    subtitle: Optional[str],
    stats: Sequence[Tuple[str, str]],
    flag_img_rgba: Image.Image,
    accent: Tuple[int, int, int],
    accent_soft: Tuple[int, int, int],
    ribbon_text: Optional[str],
    phase: float,
) -> Image.Image:
    base = _vertical_gradient((CARD_W, CARD_H), BG_TOP, BG_BOTTOM).convert("RGBA")
    base.alpha_composite(_diagonal_texture((CARD_W, CARD_H), accent, alpha=10, offset=phase))

    # Radial-ish glow behind the flag, accent-tinted, drifting gently in a
    # small orbit so the background never sits perfectly still.
    glow = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    glow_core = Image.new("RGBA", (620, 620), (0, 0, 0, 0))
    ImageDraw.Draw(glow_core).ellipse([0, 0, 620, 620], fill=(*accent, 60))
    glow_core = glow_core.filter(ImageFilter.GaussianBlur(90))
    drift_x = -160 + 22 * math.sin(2 * math.pi * phase)
    drift_y = -140 + 14 * math.cos(2 * math.pi * phase)
    glow.alpha_composite(glow_core, (int(drift_x), int(drift_y)))
    base.alpha_composite(glow)

    # Soft floating particles, confined to the empty background strip below
    # the stat row / above the footer so they never cross text.
    base.alpha_composite(_soft_particles((CARD_W, CARD_H), accent, phase, (760, 40, CARD_W - 60, 150)))

    # Accent edge strip (brand recognizability even as a tiny thumbnail)
    ImageDraw.Draw(base).rectangle([0, 0, 10, CARD_H], fill=(*accent, 255))

    draw = ImageDraw.Draw(base)

    margin_x = 72
    flag_w, flag_h = 372, 248
    flag_x, flag_y = margin_x, (CARD_H - flag_h) // 2 - 10

    _draw_soft_shadow(base, (flag_x, flag_y, flag_x + flag_w, flag_y + flag_h), radius=18)
    draw = ImageDraw.Draw(base)

    frame = Image.new("RGBA", (flag_w, flag_h), (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle([0, 0, flag_w - 1, flag_h - 1], radius=18, fill=(*BG_BOTTOM, 255))
    inner_mask = _rounded_mask((flag_w - 8, flag_h - 8), 14)
    frame.paste(flag_img_rgba, (4, 4), inner_mask)
    shimmer = _flag_shimmer((flag_w - 8, flag_h - 8), phase)
    shimmer.putalpha(Image.composite(shimmer.split()[3], Image.new("L", shimmer.size, 0), inner_mask))
    frame.alpha_composite(shimmer, (4, 4))
    border = Image.new("RGBA", (flag_w, flag_h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle([1, 1, flag_w - 2, flag_h - 2], radius=18, outline=(*accent, 255), width=3)
    frame.alpha_composite(border)
    base.alpha_composite(frame, (flag_x, flag_y))
    draw = ImageDraw.Draw(base)

    # Eyebrow / kind label — its own row, full width to itself so nothing
    # placed later can ever collide with it (see ribbon chip below).
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
        next_y += subtitle_font.size + 20
    else:
        next_y += 16

    # Coalition/tag chip — deliberately its own row (not squeezed into the
    # eyebrow row) so an arbitrarily long name can never overlap anything;
    # it ellipsizes instead of growing past the card's text column.
    if ribbon_text:
        chip_font = _font(21, 600)
        chip_text = _ellipsize(draw, ribbon_text, chip_font, title_max_w - 34)
        chip_w = _text_width(draw, chip_text, chip_font) + 34
        chip_h = 34
        draw.rounded_rectangle(
            [text_x, next_y, text_x + chip_w, next_y + chip_h], radius=17, fill=(*accent, 40), outline=(*accent, 200), width=2
        )
        dot_cy = next_y + chip_h // 2
        draw.ellipse([text_x + 12, dot_cy - 4, text_x + 20, dot_cy + 4], fill=accent_soft)
        draw.text((text_x + 28, next_y + 6), chip_text, font=chip_font, fill=accent_soft)
        next_y += chip_h + 18

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

    return base


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


def _prepare_flag(flag_bytes: Optional[bytes], flag_w: int, flag_h: int) -> Image.Image:
    return _cover_crop(_load_flag(flag_bytes), flag_w - 8, flag_h - 8).convert("RGBA")


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
    """Render a single static 1200x630 PNG "dossier card" and return raw PNG
    bytes. Used by render_fallback_card; the live Discord routes use
    render_card_gif instead so the embed image animates."""
    accent = _hex_to_rgb(accent_hex)
    accent_soft = _lighten(accent, 0.55)
    flag_img = _prepare_flag(flag_bytes, 372, 248)
    frame = _compose_frame(
        kind_label=kind_label,
        title=title,
        subtitle=subtitle,
        stats=stats,
        flag_img_rgba=flag_img,
        accent=accent,
        accent_soft=accent_soft,
        ribbon_text=ribbon_text,
        phase=0.0,
    )
    out = BytesIO()
    frame.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_card_gif(
    *,
    kind_label: str,
    title: str,
    subtitle: Optional[str] = None,
    stats: Sequence[Tuple[str, str]] = (),
    flag_bytes: Optional[bytes] = None,
    accent_hex: Optional[str] = None,
    ribbon_text: Optional[str] = None,
) -> bytes:
    """Render a short looping animated GIF "dossier card" and return raw GIF
    bytes — same layout as render_card, plus a gentle drifting glow, a
    scrolling background texture, and a foil-style shimmer sweep across the
    flag so the Discord embed image reads as alive, not a screenshot."""
    accent = _hex_to_rgb(accent_hex)
    accent_soft = _lighten(accent, 0.55)
    flag_img = _prepare_flag(flag_bytes, 372, 248)

    frames_rgb: List[Image.Image] = []
    for i in range(GIF_FRAMES):
        phase = i / GIF_FRAMES
        frame = _compose_frame(
            kind_label=kind_label,
            title=title,
            subtitle=subtitle,
            stats=stats,
            flag_img_rgba=flag_img,
            accent=accent,
            accent_soft=accent_soft,
            ribbon_text=ribbon_text,
            phase=phase,
        )
        frames_rgb.append(frame.convert("RGB"))

    # Quantize every frame against one shared palette (derived from the
    # first frame, which already contains the accent/flag/background colors
    # every other frame reuses) so frame-to-frame dithering stays stable
    # instead of "sizzling" between slightly different per-frame palettes.
    palette_img = frames_rgb[0].quantize(colors=GIF_PALETTE_COLORS, method=Image.MEDIANCUT)
    frames_p = [f.quantize(palette=palette_img, dither=Image.FLOYDSTEINBERG) for f in frames_rgb]

    out = BytesIO()
    frames_p[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames_p[1:],
        duration=GIF_FRAME_MS,
        loop=0,
        disposal=2,
        optimize=True,
    )
    return out.getvalue()


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
