"""Generate icon.icns for the macOS build of Board Game Library.

Uses the same dice renderer as create_icon.py, then calls macOS's
built-in `iconutil` to assemble the .icns file from a set of PNGs.

Run on a Mac (or in the GitHub Actions macOS runner):
    python create_icon_mac.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Re-use the renderer from the Windows icon script.
from create_icon import _render

from PIL import Image

# Required iconset sizes: (logical_size, scale)
# iconutil expects filenames like icon_16x16.png, icon_16x16@2x.png, etc.
ICONSET_SPECS = [
    (16,   1),
    (16,   2),   # → 32 px file named icon_16x16@2x.png
    (32,   1),
    (32,   2),   # → 64 px
    (128,  1),
    (128,  2),   # → 256 px
    (256,  1),
    (256,  2),   # → 512 px
    (512,  1),
    (512,  2),   # → 1024 px
]


def make_icns(dest: Path) -> None:
    if sys.platform != "darwin":
        print("WARNING: create_icon_mac.py must be run on macOS (needs iconutil).")
        print("The GitHub Actions macOS runner will handle this automatically.")
        return

    if not shutil.which("iconutil"):
        raise RuntimeError("iconutil not found — is Xcode Command Line Tools installed?")

    with tempfile.TemporaryDirectory(suffix=".iconset") as tmp:
        iconset = Path(tmp)

        for logical, scale in ICONSET_SPECS:
            pixel_size = logical * scale
            # 4× supersampling for smooth edges
            big   = _render(pixel_size * 4)
            frame = big.resize((pixel_size, pixel_size), Image.LANCZOS)

            if scale == 1:
                fname = f"icon_{logical}x{logical}.png"
            else:
                fname = f"icon_{logical}x{logical}@2x.png"

            frame.save(iconset / fname, format="PNG")
            print(f"  wrote {fname}  ({pixel_size}px)")

        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(dest)],
            check=True,
        )

    print(f"Saved {dest}")


if __name__ == "__main__":
    out = Path(__file__).parent / "icon.icns"
    make_icns(out)
