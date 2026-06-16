"""Generate icon.ico — a blue meeple librarian (glasses + book).

Run directly:
    python create_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

BLUE      = (24,  85, 184, 255)
GOLD      = (220, 180,  40, 255)
WHITE     = (255, 255, 255, 255)
BOOK_CVR  = (180, 210, 255, 255)
CLEAR     = (  0,   0,   0,   0)

ICON_SIZES = [256, 128, 64, 48, 32, 16]


def _render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), CLEAR)
    d   = ImageDraw.Draw(img)
    sc  = size / 256.0

    def e(x1, y1, x2, y2, **kw):
        d.ellipse([x1*sc, y1*sc, x2*sc, y2*sc], **kw)

    def p(pts, **kw):
        d.polygon([(x*sc, y*sc) for x, y in pts], **kw)

    def line(pts, **kw):
        d.line([(x*sc, y*sc) for x, y in pts], **kw)

    # ── body ─────────────────────────────────────────────────────────────────
    e(84, 14, 172, 102, fill=BLUE)           # head
    e(24,  86,  96, 150, fill=BLUE)          # left arm
    e(160,  86, 232, 150, fill=BLUE)         # right arm
    p([                                       # torso + legs
        ( 82,  98), (174,  98),
        (198, 168), (166, 168), (166, 224), (134, 224),
        (134, 168), (122, 168), (122, 224), ( 90, 224),
        ( 90, 168), ( 58, 168),
    ], fill=BLUE)

    # ── glasses (≥ 32 px) ────────────────────────────────────────────────────
    if size >= 32:
        gw = max(1, int(3 * sc))
        bw = max(1, int(2 * sc))
        e( 95, 53, 123, 81, outline=GOLD, width=gw)   # left lens
        e(133, 53, 161, 81, outline=GOLD, width=gw)   # right lens
        line([(123, 67), (133, 67)], fill=GOLD, width=bw)   # bridge
        if size >= 48:
            line([(95, 60), (80, 54)],   fill=GOLD, width=bw)  # left temple
            line([(161, 60), (176, 54)], fill=GOLD, width=bw)  # right temple

    # ── book (≥ 64 px) ───────────────────────────────────────────────────────
    if size >= 64:
        sw = max(1, int(2 * sc))
        d.rectangle(
            [104*sc, 116*sc, 152*sc, 158*sc],
            fill=BOOK_CVR, outline=WHITE, width=sw,
        )
        mid = 128 * sc
        d.line([(mid, 116*sc), (mid, 158*sc)], fill=WHITE, width=sw)
        for ry in [0.35, 0.55, 0.75]:
            y = (116 + 42 * ry) * sc
            d.line([(mid + sw, y), (152*sc - sw*2, y)],
                   fill=WHITE, width=max(1, sw - 1))

    return img


def make_icon(dest: Path) -> None:
    frames = [_render(s) for s in ICON_SIZES]
    frames[0].save(
        dest,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"Saved {dest}  ({', '.join(str(f.width) for f in frames)} px)")


if __name__ == "__main__":
    make_icon(Path(__file__).parent / "icon.ico")
