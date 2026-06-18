"""Generate icon.ico for Board Game Library.

Hybrid icon: a flat, bold meeple for the SMALL frames (16–48px) so the taskbar
and title bar stay crisp, and the detailed librarian artwork
(`librarian_meeple.png`) for the LARGE frames (64px+) used by the Start menu,
large icon views, and the installer. A detailed 3-D illustration just turns to
mush at 32px, so small sizes need the simple flat shape instead.

Run directly:
    python create_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

SOURCE       = "librarian_meeple.png"
# Include the in-between sizes Windows actually requests for the taskbar at
# 100/125/150/175/200% display scaling, so it never has to scale a frame.
ICON_SIZES   = [256, 128, 96, 64, 48, 40, 32, 24, 20, 16]
RADIUS_FRAC  = 0.18          # corner radius as a fraction of the image size

# Frames this size and smaller use the flat meeple; larger use the librarian.
FLAT_MAX     = 48
FLAT_BG      = (14,  42,  71)    # navy square  (matches the app header)
FLAT_MEEPLE  = (120, 180, 240)   # light-blue meeple

# The source art is a full library scene; at taskbar sizes its fine detail
# turns to mush. Crop to the meeple (+ the books it holds) so the icon reads as
# a bold, clear subject at small sizes. Fractions of the 2048px source.
MEEPLE_CROP  = (0.18, 0.16, 0.87, 0.85)   # left, top, right, bottom


def crop_to_meeple(img: Image.Image) -> Image.Image:
    """Crop the full scene down to a square framed on the meeple subject."""
    w, h = img.size
    l, t, r, b = MEEPLE_CROP
    box = (int(w * l), int(h * t), int(w * r), int(h * b))
    cropped = img.crop(box)
    # Make it square (center-cropped) so frames aren't distorted.
    cw, ch = cropped.size
    s = min(cw, ch)
    ox, oy = (cw - s) // 2, (ch - s) // 2
    return cropped.crop((ox, oy, ox + s, oy + s))


def _rounded(img: Image.Image, radius_frac: float = RADIUS_FRAC) -> Image.Image:
    """Return *img* with rounded corners (transparent outside the radius)."""
    s = min(img.size)
    img = img.convert("RGBA").resize((s, s), Image.LANCZOS)
    r = int(s * radius_frac)

    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=255)

    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _frame(src: Image.Image, size: int, radius_frac: float = RADIUS_FRAC) -> Image.Image:
    """Build one crisp icon frame: a direct high-quality downscale of the
    full-resolution source to *size*, with rounded corners cut at that size."""
    img = src.convert("RGBA").resize((size, size), Image.LANCZOS)
    r = max(1, int(size * radius_frac))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _meeple_mask(size: int) -> Image.Image:
    """An L-mode mask of a classic meeple silhouette, sized to *size*."""
    S = size * 8                              # supersample for smooth edges
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    def s(v): return v / 100 * S
    d.ellipse([s(34), s(8), s(66), s(40)], fill=255)           # head
    pts = [
        (50, 30), (62, 36), (70, 40),                          # right shoulder
        (92, 56), (92, 66), (70, 64), (64, 62), (66, 74),      # right arm/waist
        (72, 94), (56, 94), (50, 74),                          # right leg + notch
        (44, 94), (28, 94), (34, 74),                          # left leg
        (36, 62), (30, 64), (8, 66), (8, 56), (30, 40), (38, 36),  # left arm
    ]
    d.polygon([(s(x), s(y)) for x, y in pts], fill=255)
    return m.resize((size, size), Image.LANCZOS)


def _flat_frame(size: int, radius_frac: float = RADIUS_FRAC) -> Image.Image:
    """A flat, bold meeple on a rounded navy square — crisp at tiny sizes."""
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r = max(1, int(size * radius_frac))
    ImageDraw.Draw(out).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=r, fill=(*FLAT_BG, 255))
    out.paste(Image.new("RGBA", (size, size), (*FLAT_MEEPLE, 255)),
              (0, 0), _meeple_mask(size))
    return out


def make_icon(dest: Path) -> None:
    src = crop_to_meeple(Image.open(dest.parent / SOURCE).convert("RGBA"))

    # Small frames: flat meeple (crisp on the taskbar). Large frames: the
    # detailed librarian, rendered straight from the source at each pixel size.
    frames = [
        _flat_frame(sz) if sz <= FLAT_MAX else _frame(src, sz)
        for sz in ICON_SIZES
    ]
    frames[0].save(
        dest,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"Saved {dest}  ({', '.join(str(f.width) for f in frames)} px)")


if __name__ == "__main__":
    make_icon(Path(__file__).parent / "icon.ico")
