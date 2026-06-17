"""Generate icon.ico for Board Game Library.

Loads the librarian-meeple source artwork (`librarian_meeple.png`), rounds the
corners, and packages it into a multi-resolution Windows .ico.

Run directly:
    python create_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

SOURCE       = "librarian_meeple.png"
ICON_SIZES   = [256, 128, 64, 48, 32, 16]
RADIUS_FRAC  = 0.18          # corner radius as a fraction of the image size


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


def make_icon(dest: Path) -> None:
    src     = Image.open(dest.parent / SOURCE)
    rounded = _rounded(src)

    frames = [rounded.resize((s, s), Image.LANCZOS) for s in ICON_SIZES]
    frames[0].save(
        dest,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"Saved {dest}  ({', '.join(str(f.width) for f in frames)} px)")


if __name__ == "__main__":
    make_icon(Path(__file__).parent / "icon.ico")
