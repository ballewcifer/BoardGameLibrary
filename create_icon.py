"""Generate icon.ico — a sky-blue meeple with gold glasses and dark navy outline.

Run directly:
    python create_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

LIGHT_BLUE = (91,  184, 232)
DARK       = (22,   38,  68)
GOLD       = (220, 180,  40)
CLEAR      = (0,     0,   0, 0)

ICON_SIZES = [256, 128, 64, 48, 32, 16]


def _render(size: int) -> Image.Image:
    SCALE = 4
    R = size * SCALE
    k = R / 256

    # ── draw meeple shapes in light blue (overlapping → no gaps) ────────────
    layer = Image.new("RGBA", (R, R), CLEAR)
    d     = ImageDraw.Draw(layer)
    LB    = (*LIGHT_BLUE, 255)

    def e(x1, y1, x2, y2):
        d.ellipse([x1*k, y1*k, x2*k, y2*k], fill=LB)

    def p(pts):
        d.polygon([(x*k, y*k) for x, y in pts], fill=LB)

    # Head
    e(84,  6, 172, 94)
    # Neck bridge — fills the concave gap between head bottom and arm tops
    e(100, 80, 156, 108)
    # Arms — moderate ovals at shoulder level
    e( 28, 90, 100, 148)   # left  arm
    e(156, 90, 228, 148)   # right arm
    # Torso: widens to arm level, narrows to waist, flares for hip, V between legs
    p([
        ( 94,  92), (162,  92),
        (176, 148),
        (170, 166), (158, 180),
        (164, 198), (170, 212),
        (170, 252), (142, 252),
        (128, 194), (114, 252), ( 86, 252),
        ( 86, 212), ( 92, 198),
        ( 98, 180), ( 86, 166), ( 80, 148),
    ])

    # ── dark-navy outline via alpha dilation ─────────────────────────────────
    ow = max(2, size // 14)
    alpha   = layer.split()[3]
    dilated = alpha
    for _ in range(ow * SCALE):
        dilated = dilated.filter(ImageFilter.MaxFilter(3))
    navy = Image.new("RGBA", (R, R), CLEAR)
    navy.paste(Image.new("RGBA", (R, R), (*DARK, 255)), mask=dilated)

    out = Image.alpha_composite(navy, layer)
    out = out.resize((size, size), Image.LANCZOS)

    # ── gold glasses (≥ 32 px) ───────────────────────────────────────────────
    if size >= 32:
        d2  = ImageDraw.Draw(out)
        gsc = size / 256
        gw  = max(1, round(2.5 * gsc))
        bw  = max(1, round(2   * gsc))

        def ge(x1, y1, x2, y2):
            d2.ellipse([x1*gsc, y1*gsc, x2*gsc, y2*gsc],
                       outline=(*GOLD, 255), width=gw)

        def gl(pts):
            d2.line([(x*gsc, y*gsc) for x, y in pts],
                    fill=(*GOLD, 255), width=bw)

        ge( 90, 36, 118, 64)         # left  lens
        ge(138, 36, 166, 64)         # right lens
        gl([(118, 50), (138, 50)])   # bridge
        if size >= 48:
            gl([( 90, 44), ( 74, 36)])   # left  temple
            gl([(166, 44), (182, 36)])   # right temple

    return out


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
