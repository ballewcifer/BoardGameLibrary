"""Generate icon.ico for Board Game Library.

Hybrid icon: a simple, bold d6 die for the SMALL frames (16–48px) so the
taskbar and title bar stay crisp, and the detailed librarian artwork
(`librarian_meeple.png`) for the LARGE frames (64px+) used by the Start menu,
large icon views, and the installer. A detailed 3-D illustration just turns to
mush at 32px, so small sizes need a simple bold shape instead.

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

# d6 palette (app navy/blue/gold)
DIE_NAVY = (26,  58,  92)
DIE_BLUE = (36, 113, 163)
DIE_SKY  = (93, 173, 226)
DIE_GOLD = (212, 160,  23)

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


def _die_render(size: int) -> Image.Image:
    """Draw a d6 die at *size* px: navy body, blue face, gold pips (no scaling)."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = max(2, size // 10)
    r   = max(4, size // 4)

    so = max(1, size // 16)                                   # drop shadow
    draw.rounded_rectangle([pad + so, pad + so, size - pad + so // 2,
                            size - pad + so // 2], radius=r, fill=(0, 0, 0, 90))
    draw.rounded_rectangle([pad, pad, size - pad, size - pad],
                           radius=r, fill=(*DIE_NAVY, 255))   # navy outer
    brd = max(2, size // 16)
    draw.rounded_rectangle([pad + brd, pad + brd, size - pad - brd,
                            size - pad - brd], radius=max(3, r - brd),
                           fill=(*DIE_BLUE, 255))             # blue face

    if size >= 48:                                            # shine
        hl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(hl).rounded_rectangle(
            [pad + brd + max(1, size // 20), pad + brd + max(1, size // 20),
             size // 2, size // 2], radius=max(2, r // 2), fill=(*DIE_SKY, 55))
        img = Image.alpha_composite(img, hl); draw = ImageDraw.Draw(img)

    fp = pad + brd; fw = size - 2 * fp; pr = max(1, fw // 9)  # gold pips (6-face)
    cx_l, cx_r = fp + fw * 29 // 100, fp + fw * 71 // 100
    cy_t, cy_m, cy_b = fp + fw * 19 // 100, fp + fw * 50 // 100, fp + fw * 81 // 100
    for px, py in [(cx_l, cy_t), (cx_r, cy_t), (cx_l, cy_m),
                   (cx_r, cy_m), (cx_l, cy_b), (cx_r, cy_b)]:
        if pr >= 3:
            draw.ellipse([px - pr + 1, py - pr + 1, px + pr + 1, py + pr + 1],
                         fill=(0, 0, 0, 60))
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(*DIE_GOLD, 255))
    return img


def _die_frame(size: int) -> Image.Image:
    """A d6 frame, 4× supersampled then downscaled for smooth edges."""
    return _die_render(size * 4).resize((size, size), Image.LANCZOS)


def make_icon(dest: Path) -> None:
    """icon.ico — the librarian artwork at every size. This is the app's icon
    everywhere: the .exe, desktop shortcut, Start menu, installer, title bar."""
    src = crop_to_meeple(Image.open(dest.parent / SOURCE).convert("RGBA"))
    frames = [_frame(src, sz) for sz in ICON_SIZES]
    frames[0].save(
        dest, format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"Saved {dest}  ({', '.join(str(f.width) for f in frames)} px)")


def make_die_icon(dest: Path) -> None:
    """die.ico — the d6 die at every size. Used ONLY for the running window's
    taskbar button (set at runtime), where the detailed art looks muddy."""
    frames = [_die_frame(sz) for sz in ICON_SIZES]
    frames[0].save(
        dest, format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    print(f"Saved {dest}  ({', '.join(str(f.width) for f in frames)} px)")


if __name__ == "__main__":
    here = Path(__file__).parent
    make_icon(here / "icon.ico")
    make_die_icon(here / "die.ico")
