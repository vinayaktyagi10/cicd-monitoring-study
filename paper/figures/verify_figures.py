#!/usr/bin/env python3
"""Re-renders every data figure into a temporary directory and compares it,
pixel by pixel at 150 dpi, against the PDF committed in paper/figures/, and
checks that the hand-drawn Fig. 2 still names every job, action and the
Python version in .github/workflows/ci.yml.
Exit status 1 if anything differs. Needs pdftoppm (poppler).
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = os.path.join(os.path.dirname(os.path.dirname(HERE)), ".github", "workflows", "ci.yml")


def workflow_terms(yml):
    jobs = re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", yml.split("\njobs:", 1)[1], re.M)
    actions = [a.split("/")[-1] for a in re.findall(r"uses:\s*([^@\s]+)@", yml)]
    versions = re.findall(r'python-version:\s*"?([0-9.]+)', yml)
    return sorted(set(jobs + actions + versions))


def check_fig2():
    with open(WORKFLOW) as fh:
        terms = workflow_terms(fh.read())
    with open(os.path.join(HERE, "fig2_gha_workflow.tex")) as fh:
        tex = fh.read()
    missing = [t for t in terms if t not in tex]
    print(f"[{'MATCH' if not missing else 'DIFFERS':8s}] fig2_gha_workflow.tex vs ci.yml: "
          f"{len(terms) - len(missing)}/{len(terms)} jobs/actions/versions present"
          + (f", missing {missing}" if missing else ""))
    return len(missing) > 0


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
    bad += check_fig2()
    print(f"{'all figures reproduce' if not bad else f'{bad} figure(s) do not reproduce'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
