#!/usr/bin/env python3
"""Re-renders every data figure into a temporary directory and compares it,
pixel by pixel at 150 dpi, against the PDF committed in paper/figures/.
Exit status 1 if any figure differs. Needs pdftoppm (poppler).
"""
import glob
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def raster(pdf, stem):
    subprocess.run(["pdftoppm", "-r", "150", "-png", "-singlefile", pdf, stem], check=True)
    return np.asarray(Image.open(stem + ".png").convert("RGB"), dtype=np.int16)


def main():
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, os.path.join(HERE, "generate_figures.py"), "--outdir", tmp],
                       check=True, stdout=subprocess.DEVNULL)
        for new in sorted(glob.glob(os.path.join(tmp, "*.pdf"))):
            name = os.path.basename(new)
            committed = os.path.join(HERE, name)
            if not os.path.exists(committed):
                print(f"[MISSING ] {name} has no committed counterpart")
                bad += 1
                continue
            a = raster(new, os.path.join(tmp, name + ".new"))
            b = raster(committed, os.path.join(tmp, name + ".old"))
            if a.shape != b.shape:
                print(f"[DIFFERS ] {name}: size {a.shape[:2]} vs committed {b.shape[:2]}")
                bad += 1
                continue
            n = int((np.abs(a - b).sum(axis=2) > 0).sum())
            print(f"[{'MATCH' if n == 0 else 'DIFFERS':8s}] {name}: {n} differing pixels")
            bad += n > 0
    print(f"{'all figures reproduce' if not bad else f'{bad} figure(s) do not reproduce'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
