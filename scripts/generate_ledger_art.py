"""Generate the Ledger goods art: one icon per good, one scene per producer building.

Run from the repo root: python scripts/generate_ledger_art.py
Output: static/images/ledger/res_<good>.svg and bld_<building>.svg (deterministic).
These are clean vector stand-ins; swap in painted/photo art by replacing the files.
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "static" / "images" / "ledger"
INK = "#1b2027"


def gear():
    teeth = "".join(
        f'<rect x="22" y="3" width="6" height="9" rx="1.2" fill="#8d99a6" stroke="{INK}" stroke-width="1.2" transform="rotate({a} 25 25)"/>'
        for a in range(0, 360, 45)
    )
    return (
        teeth
        + f'<circle cx="25" cy="25" r="15" fill="#a9b4c0" stroke="{INK}" stroke-width="1.6"/>'
        + f'<circle cx="25" cy="25" r="9.5" fill="#7c8894" stroke="{INK}" stroke-width="1.2"/>'
        + f'<circle cx="25" cy="25" r="4.2" fill="#2b323b" stroke="{INK}" stroke-width="1.2"/>'
        + '<path d="M14 19a13 13 0 0 1 9-7" stroke="#e3e9ef" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
    )


def sack(body, band, mark):
    return (
        f'<path d="M12 12c3-3 5-4 7-4h12c2 0 4 1 7 4l-3 4c4 6 6 13 5 22-1 4-3 6-7 6H17c-4 0-6-2-7-6-1-9 1-16 5-22z" fill="{body}" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
        f'<path d="M15 16h20" stroke="{INK}" stroke-width="1.6" stroke-linecap="round"/>'
        f'<rect x="12.5" y="24" width="25" height="11" fill="{band}" stroke="{INK}" stroke-width="1.2"/>'
        + mark
        + '<path d="M15 20c-2 4-3 9-3 14" stroke="#ffffff" stroke-opacity=".45" stroke-width="1.6" fill="none" stroke-linecap="round"/>'
    )


def cement():
    return sack("#cdbf9f", "#6f7780", '<path d="M17 32l4-5 4 5zM25 32l4-5 4 5z" fill="#e9edf1"/>')


def fertilizer():
    return sack(
        "#5fa052",
        "#f0ead2",
        '<path d="M25 33c0-5 2-7 7-8-1 5-3 7-7 8zm0 0c0-4-2-6-6-7 1 4 2 6 6 7z" fill="#2f7a3a" stroke="#1b2027" stroke-width=".8"/>',
    )


def textiles():
    return (
        f'<path d="M9 31l22-9c5-2 9 0 10 4s-1 8-6 10l-22 8z" fill="#3f78c9" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
        f'<path d="M9 31c3 1 5 4 4 13" fill="none" stroke="{INK}" stroke-width="1.4"/>'
        f'<ellipse cx="36" cy="29" rx="5.5" ry="7.5" transform="rotate(-22 36 29)" fill="#6fa3ea" stroke="{INK}" stroke-width="1.6"/>'
        f'<ellipse cx="36" cy="29" rx="1.8" ry="2.6" transform="rotate(-22 36 29)" fill="#20304a"/>'
        '<path d="M14 33l16-6.5M15 38l17-7" stroke="#a9c8f5" stroke-width="1.2" stroke-linecap="round"/>'
        f'<path d="M9 31l-3 9 7 4" fill="#2f5fa6" stroke="{INK}" stroke-width="1.4" stroke-linejoin="round"/>'
    )


def clothing():
    return (
        f'<path d="M18 8l-11 6 4 9 5-2v21h18V21l5 2 4-9-11-6c-1 4-4 6-7 6s-6-2-7-6z" fill="#c9433f" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
        f'<path d="M18 8c1 4 4 6 7 6s6-2 7-6" fill="none" stroke="{INK}" stroke-width="1.4"/>'
        '<path d="M19 22v17" stroke="#e98a84" stroke-width="1.8" stroke-linecap="round"/>'
        '<rect x="27" y="24" width="5" height="5" rx="1" fill="#f3d9a4" stroke="#1b2027" stroke-width=".9"/>'
    )


def chemicals():
    return (
        f'<path d="M20 6h10v3h-1.5v10l10 17c2 4 0 8-5 8H16.5c-5 0-7-4-5-8l10-17V9H20z" fill="#dfeff2" fill-opacity=".9" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
        '<path d="M16.6 30h16.8l4 7c1.4 3 0 5-3.5 5H16.1c-3.500 0-4.900-2-3.500-5z" fill="#21b3a3"/>'
        '<circle cx="21" cy="36" r="1.8" fill="#9af0e4"/><circle cx="28" cy="33.500" r="1.200" fill="#9af0e4"/><circle cx="30" cy="38.500" r="1.500" fill="#9af0e4"/>'
        f'<path d="M20 6h10v3H20z" fill="#9fb3bd" stroke="{INK}" stroke-width="1.4"/>'
        '<path d="M23.500 12v8l-7 12" stroke="#ffffff" stroke-opacity=".7" stroke-width="1.4" fill="none" stroke-linecap="round"/>'
    )


def medicine():
    return (
        f'<g transform="rotate(-38 25 25)"><rect x="6" y="17" width="38" height="16" rx="8" fill="#f4f1ea" stroke="{INK}" stroke-width="1.6"/>'
        f'<path d="M25 17h11a8 8 0 0 1 0 16H25z" fill="#d6453f" stroke="{INK}" stroke-width="1.6"/>'
        '<path d="M12 21.500h9" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/><path d="M28 21.500h7" stroke="#f29a94" stroke-width="2" stroke-linecap="round"/></g>'
        f'<circle cx="38" cy="38" r="7.500" fill="#2f9e5b" stroke="{INK}" stroke-width="1.4"/>'
        '<path d="M38 33.500v9M33.500 38h9" stroke="#ffffff" stroke-width="2.600" stroke-linecap="round"/>'
    )


def plastics():
    return (
        f'<path d="M20 5h8v5l5 6v24c0 3-2 5-5 5h-8c-3 0-5-2-5-5V16l5-6z" fill="#7fd3ea" fill-opacity=".85" stroke="{INK}" stroke-width="1.6" stroke-linejoin="round"/>'
        f'<rect x="19.500" y="4" width="9" height="4.500" rx="1" fill="#2c7da0" stroke="{INK}" stroke-width="1.300"/>'
        '<rect x="15.800" y="22" width="16.400" height="10" fill="#f1f6f8" fill-opacity=".9"/>'
        '<path d="M18 18v20" stroke="#ffffff" stroke-opacity=".8" stroke-width="1.600" stroke-linecap="round"/>'
        f'<circle cx="38" cy="39" r="3.400" fill="#f2b84b" stroke="{INK}" stroke-width="1.200"/><circle cx="43" cy="33" r="2.800" fill="#e2605a" stroke="{INK}" stroke-width="1.200"/><circle cx="8" cy="40" r="3" fill="#8bd17c" stroke="{INK}" stroke-width="1.200"/>'
    )


def electronics():
    pins = "".join(
        f'<rect x="{x}" y="5" width="3" height="7" fill="#d9b24a" stroke="{INK}" stroke-width=".9"/><rect x="{x}" y="38" width="3" height="7" fill="#d9b24a" stroke="{INK}" stroke-width=".9"/>'
        f'<rect x="5" y="{x}" width="7" height="3" fill="#d9b24a" stroke="{INK}" stroke-width=".9"/><rect x="38" y="{x}" width="7" height="3" fill="#d9b24a" stroke="{INK}" stroke-width=".9"/>'
        for x in (15, 23.5, 32)
    )
    return (
        pins
        + f'<rect x="11" y="11" width="28" height="28" rx="3" fill="#2f8f5b" stroke="{INK}" stroke-width="1.600"/>'
        + f'<rect x="18" y="18" width="14" height="14" rx="1.500" fill="#20262d" stroke="{INK}" stroke-width="1.200"/>'
        + '<path d="M14 15h6M30 35h6M14 35h3M33 15h3" stroke="#9ee0b8" stroke-width="1.300" stroke-linecap="round"/>'
        + '<circle cx="21.500" cy="21.500" r="1.300" fill="#9aa7b3"/>'
    )


def vehicles():
    return (
        f'<path d="M4 32v-6c0-2 1-3 3-3l5-1 5-7c1-1.500 2-2 4-2h10c2 0 3 .500 4.500 2l6 7 3 1c1.500.500 2.500 1.500 2.500 3.500V32c0 1.500-1 2.500-2.500 2.500h-38C5 34.500 4 33.500 4 32z" fill="#e0862d" stroke="{INK}" stroke-width="1.600" stroke-linejoin="round"/>'
        f'<path d="M15.500 22l4-5.500h6.500V22zM28.500 16.500h5l4.500 5.500h-9.500z" fill="#bfe3f2" stroke="{INK}" stroke-width="1.200" stroke-linejoin="round"/>'
        '<path d="M6 27h38" stroke="#f6b56f" stroke-width="1.400"/>'
        f'<circle cx="14" cy="35" r="5.500" fill="#262c33" stroke="{INK}" stroke-width="1.400"/><circle cx="14" cy="35" r="2.200" fill="#aab4be"/>'
        f'<circle cx="36" cy="35" r="5.500" fill="#262c33" stroke="{INK}" stroke-width="1.400"/><circle cx="36" cy="35" r="2.200" fill="#aab4be"/>'
        '<rect x="42" y="25.500" width="3.500" height="2.500" rx="1" fill="#ffe9a8"/>'
    )


def luxury_goods():
    return (
        f'<circle cx="25" cy="32" r="12" fill="none" stroke="{INK}" stroke-width="7.200"/>'
        '<circle cx="25" cy="32" r="12" fill="none" stroke="#e6b93f" stroke-width="4.400"/>'
        '<path d="M15 27a11 11 0 0 1 5-5" stroke="#fff1b8" stroke-width="1.600" fill="none" stroke-linecap="round"/>'
        f'<path d="M17 12l4-6h8l4 6-8 9z" fill="#8f6bf0" stroke="{INK}" stroke-width="1.600" stroke-linejoin="round"/>'
        f'<path d="M17 12h16M21 6l4 6 4-6M25 12v9" stroke="{INK}" stroke-width="1" fill="none"/>'
        '<path d="M21 6l-2.500 5h5z" fill="#c3b0ff"/>'
    )


GOODS = {
    "machinery": (gear, "#a9b4c0"),
    "cement": (cement, "#cdbf9f"),
    "textiles": (textiles, "#4f8ad8"),
    "clothing": (clothing, "#c9433f"),
    "chemicals": (chemicals, "#21b3a3"),
    "medicine": (medicine, "#d6453f"),
    "fertilizer": (fertilizer, "#5fa052"),
    "plastics": (plastics, "#58c2df"),
    "electronics": (electronics, "#2f8f5b"),
    "vehicles": (vehicles, "#e0862d"),
    "luxury_goods": (luxury_goods, "#e6b93f"),
}

# building -> (good, plant layout)
BUILDINGS = {
    "machinery_works": ("machinery", "sawtooth"),
    "cement_works": ("cement", "silos"),
    "textile_mills": ("textiles", "sawtooth"),
    "clothing_factories": ("clothing", "hall"),
    "chemical_plants": ("chemicals", "tanks"),
    "pharmaceutical_labs": ("medicine", "lab"),
    "fertilizer_plants": ("fertilizer", "silos"),
    "plastics_plants": ("plastics", "tanks"),
    "electronics_factories": ("electronics", "lab"),
    "vehicle_works": ("vehicles", "hall"),
    "luxury_workshops": ("luxury_goods", "workshop"),
}


def _windows(x, y, w, n, color, rows=1, h=26, gap=18):
    step = w / n
    out = ""
    for r in range(rows):
        for i in range(n):
            out += f'<rect x="{x + i * step + step * .18:.0f}" y="{y + r * (h + gap)}" width="{step * .64:.0f}" height="{h}" rx="3" fill="{color}" fill-opacity="{.85 if (i + r) % 3 else .45}"/>'
    return out


def _stack(x, top, base, w, accent):
    return (
        f'<rect x="{x}" y="{top}" width="{w}" height="{base - top}" fill="#3a434e"/>'
        f'<rect x="{x}" y="{top}" width="{w * .35:.0f}" height="{base - top}" fill="#4a5562"/>'
        f'<rect x="{x - 5}" y="{top}" width="{w + 10}" height="16" fill="{accent}"/>'
        f'<rect x="{x - 5}" y="{top + 44}" width="{w + 10}" height="10" fill="#d9dee4" fill-opacity=".7"/>'
        f'<g fill="#c9d2dc" fill-opacity=".16"><circle cx="{x + w / 2 + 20}" cy="{top - 40}" r="42"/><circle cx="{x + w / 2 + 70}" cy="{top - 95}" r="56"/><circle cx="{x + w / 2 + 140}" cy="{top - 150}" r="70"/></g>'
    )


def _plant(kind, accent):
    g = 620  # ground line
    lit = "#ffd98a"
    wall, wall2, roof = "#56616e", "#465059", "#2f3740"
    if kind == "sawtooth":
        teeth = "".join(f'<path d="M{180 + i * 150} 360l150-70v70z" fill="{roof}"/><path d="M{180 + i * 150} 360l150-70v14l-120 56z" fill="#9fd0e6" fill-opacity=".55"/>' for i in range(5))
        return (
            _stack(960, 170, 360, 56, accent) + _stack(1040, 230, 360, 44, accent) + teeth
            + f'<rect x="180" y="360" width="750" height="{g - 360}" fill="{wall}"/><rect x="930" y="360" width="190" height="{g - 360}" fill="{wall2}"/>'
            + f'<rect x="180" y="360" width="940" height="18" fill="{accent}"/>'
            + _windows(210, 420, 690, 9, lit, rows=2)
            + f'<rect x="965" y="470" width="120" height="{g - 470}" fill="#262d35"/><path d="M965 500h120M965 530h120M965 560h120M965 590h120" stroke="#3b444e" stroke-width="5"/>'
        )
    if kind == "silos":
        silos = "".join(
            f'<rect x="{200 + i * 150}" y="250" width="120" height="{g - 250}" fill="{wall if i % 2 else wall2}"/><ellipse cx="{260 + i * 150}" cy="250" rx="60" ry="22" fill="#6c7886"/>'
            f'<rect x="{200 + i * 150}" y="330" width="120" height="14" fill="{accent}"/><rect x="{212 + i * 150}" y="250" width="16" height="{g - 250}" fill="#ffffff" fill-opacity=".08"/>'
            for i in range(4)
        )
        return (
            _stack(1050, 150, 430, 60, accent) + silos
            + f'<path d="M230 235L800 150l20 26L250 262z" fill="#39424c"/><path d="M230 235L800 150" stroke="{accent}" stroke-width="6"/>'
            + f'<rect x="790" y="140" width="110" height="{g - 140}" fill="{wall2}"/><rect x="790" y="140" width="110" height="16" fill="{accent}"/>'
            + f'<rect x="900" y="430" width="290" height="{g - 430}" fill="{wall}"/>' + _windows(915, 470, 260, 4, lit)
        )
    if kind == "tanks":
        tanks = "".join(
            f'<rect x="{190 + i * 190}" y="{380 - (i % 2) * 60}" width="150" height="{g - 380 + (i % 2) * 60}" rx="14" fill="{wall if i % 2 else wall2}"/>'
            f'<ellipse cx="{265 + i * 190}" cy="{380 - (i % 2) * 60}" rx="75" ry="20" fill="#74808e"/>'
            f'<rect x="{190 + i * 190}" y="{450 - (i % 2) * 60}" width="150" height="16" fill="{accent}"/>'
            for i in range(3)
        )
        pipes = f'<path d="M150 560h620M340 400v-70h380v230M760 330h170v290" stroke="#8793a0" stroke-width="12" fill="none"/><path d="M150 585h900" stroke="{accent}" stroke-width="8" fill="none"/>'
        tower = f'<rect x="900" y="180" width="70" height="{g - 180}" fill="#5d6875"/>' + "".join(f'<rect x="888" y="{210 + i * 62}" width="94" height="10" fill="#aab4be"/>' for i in range(6)) + _stack(1060, 240, g, 46, accent)
        return tanks + pipes + tower
    if kind == "lab":
        return (
            f'<rect x="200" y="300" width="560" height="{g - 300}" fill="#66727f"/><rect x="760" y="380" width="400" height="{g - 380}" fill="{wall}"/>'
            f'<rect x="200" y="300" width="960" height="0" /><rect x="200" y="300" width="560" height="16" fill="{accent}"/><rect x="760" y="380" width="400" height="14" fill="{accent}"/>'
            + _windows(225, 345, 510, 7, "#bfe7f5", rows=4, h=34, gap=22)
            + _windows(785, 425, 350, 5, lit, rows=2, h=34, gap=24)
            + f'<rect x="430" y="250" width="110" height="50" fill="{wall2}"/><path d="M485 250v-70" stroke="#aab4be" stroke-width="8"/><circle cx="485" cy="172" r="12" fill="{accent}"/>'
            + f'<rect x="900" y="330" width="60" height="50" fill="{roof}"/><rect x="1010" y="340" width="80" height="40" fill="{roof}"/>'
        )
    if kind == "hall":
        return (
            _stack(1090, 220, 400, 50, accent)
            + f'<path d="M170 400q260-150 520 0z" fill="#6c7886"/><path d="M690 400q230-130 460 0z" fill="#5f6b78"/>'
            + f'<rect x="170" y="400" width="980" height="{g - 400}" fill="{wall}"/><rect x="170" y="400" width="980" height="18" fill="{accent}"/>'
            + _windows(200, 450, 420, 6, lit)
            + "".join(f'<rect x="{680 + i * 160}" y="470" width="130" height="{g - 470}" fill="#262d35"/><rect x="{680 + i * 160}" y="470" width="130" height="12" fill="{accent}"/>' for i in range(3))
            + '<path d="M200 520h420M200 560h420" stroke="#3f4852" stroke-width="6"/>'
        )
    # workshop
    return (
        f'<path d="M260 380l250-150 250 150z" fill="#7a4f3a"/><path d="M760 420l180-110 180 110z" fill="#6b4433"/>'
        f'<rect x="290" y="380" width="440" height="{g - 380}" fill="#8a7461"/><rect x="760" y="420" width="360" height="{g - 420}" fill="#7b6757"/>'
        f'<rect x="290" y="380" width="440" height="14" fill="{accent}"/><rect x="760" y="420" width="360" height="12" fill="{accent}"/>'
        + _windows(320, 430, 380, 4, lit, rows=1, h=70)
        + _windows(790, 470, 300, 3, lit, rows=1, h=60)
        + f'<rect x="455" y="520" width="90" height="{g - 520}" rx="6" fill="#3b2c24"/><circle cx="510" cy="300" r="26" fill="{accent}"/><rect x="620" y="250" width="40" height="110" fill="#5b4a3f"/>'
    )


def building_svg(name, good, kind):
    draw, accent = GOODS[good]
    title = name.replace("_", " ").title()
    stars = "".join(
        f'<circle cx="{(i * 397) % 1500}" cy="{(i * 211) % 300}" r="{1 + i % 3 * .6:.1f}" fill="#ffffff" fill-opacity="{.25 + (i % 4) * .12:.2f}"/>' for i in range(1, 46)
    )
    hills = "".join(f'<path d="M{-100 + i * 420} 620q210-{120 + (i % 3) * 40} 420 0z" fill="#1c2630"/>' for i in range(5))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 1000" role="img" aria-label="{title}">
<defs>
<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#101820"/><stop offset=".55" stop-color="#22313f"/><stop offset="1" stop-color="{accent}" stop-opacity=".55"/></linearGradient>
<linearGradient id="ground" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2a323b"/><stop offset="1" stop-color="#12171c"/></linearGradient>
<radialGradient id="glow" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{accent}" stop-opacity=".5"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient>
</defs>
<rect width="1500" height="1000" fill="#101820"/>
<rect width="1500" height="640" fill="url(#sky)"/>
{stars}
{hills}
<g transform="translate(40 0)">{_plant(kind, accent)}</g>
<rect y="620" width="1500" height="380" fill="url(#ground)"/>
<path d="M0 700h1500M0 800h1500M0 900h1500" stroke="#ffffff" stroke-opacity=".04" stroke-width="3"/>
<circle cx="750" cy="805" r="230" fill="url(#glow)"/>
<circle cx="750" cy="805" r="132" fill="#161c23" stroke="{accent}" stroke-width="8"/>
<g transform="translate(650 705) scale(4)">{draw()}</g>
</svg>
'''


def resource_svg(name):
    draw, _ = GOODS[name]
    title = name.replace("_", " ").title()
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 50 50" width="50" height="50" role="img" aria-label="{title}">{draw()}</svg>\n'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in GOODS:
        (OUT / f"res_{name}.svg").write_text(resource_svg(name))
    for name, (good, kind) in BUILDINGS.items():
        (OUT / f"bld_{name}.svg").write_text(building_svg(name, good, kind))
    print(f"wrote {len(GOODS)} goods + {len(BUILDINGS)} buildings to {OUT}")


if __name__ == "__main__":
    main()
