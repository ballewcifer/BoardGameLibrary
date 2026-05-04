"""Generate icon.ico for Board Game Library.

Renders a d6 (six-sided die) in the app's navy/blue/gold colour palette,
with a drop shadow, a subtle top-left highlight, and gold pips.
Four-times supersampling is used so edges look smooth at every size.

Run directly:
    python create_icon.py
"""

from pathlib import Path
from PIL import Image, ImageDraw

# ── app colour palette ────────────────────────────────────────────────────────
NAVY  = (26,  58,  92)
BLUE  = (36, 113, 163)
SKY   = (93, 173, 226)
GOLD  = (212, 160,  23)
WHITE = (255, 255, 255)

ICON_SIZES = [256, 128, 64, 48, 32, 16]


def _render(size: int) -> Image.Image:
    """Draw one frame of the dice icon at *size* × *size* pixels."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(2, size // 10)          # outer margin
    r   = max(4, size // 4)           # corner radius for dice body

    # ── soft drop shadow ─────────────────────────────────────────────────────
    so = max(1, size // 16)
    draw.rounded_rectangle(
        [pad + so, pad + so, size - pad + so // 2, size - pad + so // 2],
        radius=r, fill=(0, 0, 0, 90),
    )

    # ── navy outer ring (thick border effect) ────────────────────────────────
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r, fill=NAVY,
    )

    # ── blue inner face ───────────────────────────────────────────────────────
    brd = max(2, size // 16)
    inner_r = max(3, r - brd)
    draw.rounded_rectangle(
        [pad + brd, pad + brd, size - pad - brd, size - pad - brd],
        radius=inner_r, fill=BLUE,
    )

    # ── top-left highlight (simulated shine) ─────────────────────────────────
    if size >= 48:
        hl      = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        hd      = ImageDraw.Draw(hl)
        hl_pad  = pad + brd + max(1, size // 20)
        hl_end  = size // 2
        hd.rounded_rectangle(
            [hl_pad, hl_pad, hl_end, hl_end],
            radius=max(2, r // 2),
            fill=(*SKY, 55),       # semi-transparent sky-blue
        )
        img  = Image.alpha_composite(img, hl)
        draw = ImageDraw.Draw(img)

    # ── gold pips: 6-face layout (2 columns × 3 rows) ────────────────────────
    fp  = pad + brd                    # face padding (start of usable face area)
    fw  = size - 2 * fp                # face width / height (it's square)
    pr  = max(1, fw // 9)             # pip radius

    cx_l = fp + fw * 29 // 100        # left column  (~29% across)
    cx_r = fp + fw * 71 // 100        # right column (~71% across)
    cy_t = fp + fw * 19 // 100        # top row      (~19% down)
    cy_m = fp + fw * 50 // 100        # middle row   (~50% down)
    cy_b = fp + fw * 81 // 100        # bottom row   (~81% down)

    for px, py in [
        (cx_l, cy_t), (cx_r, cy_t),
        (cx_l, cy_m), (cx_r, cy_m),
        (cx_l, cy_b), (cx_r, cy_b),
    ]:
        # Small shadow under each pip for depth
        if pr >= 3:
            draw.ellipse(
                [px - pr + 1, py - pr + 1, px + pr + 1, py + pr + 1],
                fill=(0, 0, 0, 60),
            )
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=GOLD)

    return img


def make_icon(dest: Path) -> None:
    frames: list[Image.Image] = []
    for size in ICON_SIZES:
        big   = _render(size * 4)                          # 4× supersample
        frame = big.resize((size, size), Image.LANCZOS)    # downscale cleanly
        frames.append(frame)

    frames[0].save(
        dest,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=frames[1:],
    )
    sizes_str = ", ".join(str(f.width) for f in frames)
    print(f"Saved {dest}  ({sizes_str} px)")


if __name__ == "__main__":
    out = Path(__file__).parent / "icon.ico"
    make_icon(out)
