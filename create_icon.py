"""Generate icon.ico for Board Game Library.

Loads the librarian-meeple source artwork (`librarian_meeple.png`), rounds the
corners, and packages it into a multi-resolution Windows .ico.

Run directly:
    python create_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

SOURCE       = "librarian_meeple.png"
# Include the in-between sizes Windows actually requests for the taskbar at
# 100/125/150/175/200% display scaling (40/48/56/64…), so it never has to
# upscale a smaller frame — which is what made the taskbar icon look blurry.
ICON_SIZES   = [256, 128, 96, 64, 48, 40, 32, 24, 20, 16]
RADIUS_FRAC  = 0.18          # corner radius as a fraction of the image size

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


def make_icon(dest: Path) -> None:
    src = crop_to_meeple(Image.open(dest.parent / SOURCE).convert("RGBA"))

    # Each frame is rendered straight from the cropped source at its exact pixel
    # size (sharpest result) rather than downscaled from a single rounded image.
    frames = [_frame(src, sz) for sz in ICON_SIZES]
    frames[0].save(
        dest,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"Saved {dest}  ({', '.join(str(f.width) for f in frames)} px)")


if __name__ == "__main__":
    make_icon(Path(__file__).parent / "icon.ico")
