"""Generate icon.ico — a blue meeple librarian (glasses + book)."""
from PIL import Image, ImageDraw
import math, pathlib

BLUE      = (24,  85, 184, 255)   # royal blue body
DARK_BLUE = (14,  58, 140, 255)   # shadow / outline
GOLD      = (220, 180,  40, 255)  # glasses frame
WHITE     = (255, 255, 255, 255)
CLEAR     = (  0,   0,   0,   0)

def _sc(val, s): return val * s / 256.0

def draw_meeple(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), CLEAR)
    d   = ImageDraw.Draw(img)
    sc  = size / 256.0

    def e(x1, y1, x2, y2, **kw):
        d.ellipse([x1*sc, y1*sc, x2*sc, y2*sc], **kw)

    def p(pts, **kw):
        d.polygon([(x*sc, y*sc) for x, y in pts], **kw)

    def line(pts, **kw):
        d.line([(x*sc, y*sc) for x, y in pts], **kw)

    # ── body ────────────────────────────────────────────────────────────────
    # Head
    e(84, 14, 172, 102, fill=BLUE)

    # Left arm bump
    e(24, 86, 96, 150, fill=BLUE)

    # Right arm bump
    e(160, 86, 232, 150, fill=BLUE)

    # Torso + legs (single polygon — body connects arms, splits into two legs)
    p([
        (82,  98),   # left top shoulder
        (174,  98),  # right top shoulder
        (198, 168),  # right waist/hip
        (166, 168),  # right leg outer-top
        (166, 224),  # right leg outer-bottom
        (134, 224),  # right leg inner-bottom
        (134, 168),  # right leg inner-top  ← gap between legs
        (122, 168),  # left  leg inner-top
        (122, 224),  # left  leg inner-bottom
        ( 90, 224),  # left  leg outer-bottom
        ( 90, 168),  # left  leg outer-top
        ( 58, 168),  # left waist/hip
    ], fill=BLUE)

    # ── glasses (visible at ≥ 32 px) ────────────────────────────────────────
    if size >= 32:
        gw = max(1, int(3 * sc))   # lens stroke width
        bw = max(1, int(2 * sc))   # bridge stroke width
        # left lens
        e(95, 53, 123, 81, outline=GOLD, width=gw)
        # right lens
        e(133, 53, 161, 81, outline=GOLD, width=gw)
        # bridge
        line([(123, 67), (133, 67)], fill=GOLD, width=bw)
        # left arm (temple)
        if size >= 48:
            line([(95, 60), (80, 54)], fill=GOLD, width=bw)
            line([(161, 60), (176, 54)], fill=GOLD, width=bw)

    # ── tiny book on body (visible at ≥ 64 px) ──────────────────────────────
    if size >= 64:
        bx1, by1, bx2, by2 = 104, 116, 152, 158   # book bounding box
        book_bg   = (240, 240, 255, 255)
        book_cover= (180, 210, 255, 255)
        sw = max(1, int(2 * sc))
        # cover fill
        d.rectangle([bx1*sc, by1*sc, bx2*sc, by2*sc], fill=book_cover, outline=WHITE, width=sw)
        # spine line
        mid_x = ((bx1 + bx2) / 2) * sc
        d.line([(mid_x, by1*sc), (mid_x, by2*sc)], fill=WHITE, width=sw)
        # ruled lines on right page
        for ry in [0.35, 0.55, 0.75]:
            y = (by1 + (by2 - by1) * ry) * sc
            d.line([(mid_x + sw, y), (bx2*sc - sw*2, y)], fill=WHITE, width=max(1, sw-1))

    return img


def build_ico(out_path: str) -> None:
    sizes = [256, 128, 64, 48, 32, 16]
    imgs  = [draw_meeple(s) for s in sizes]
    # Pillow requires the primary image to have all desired sizes listed
    imgs[0].save(
        out_path,
        format  = "ICO",
        sizes   = [(s, s) for s in sizes],
        append_images = imgs[1:],
    )
    print(f"Saved {out_path}  ({len(sizes)} sizes: {sizes})")


if __name__ == "__main__":
    out = pathlib.Path(__file__).parent / "icon.ico"
    build_ico(str(out))
