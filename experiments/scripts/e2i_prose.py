#!/usr/bin/env python3
"""Recomputes every Experiment 2i number (and the two Experiment 5 repeat sessions quoted in
Section P4) in paper/paper.tex from raw/exp2_interleaved.csv and raw/exp5_aa_session*.csv, and checks that each appears verbatim. Exit status 1 on any miss.

    python e2i_prose.py [--csv ../raw/exp2_interleaved.csv]
"""
import argparse
import os
import re
import statistics
import sys

import analyze_exp2_interleaved as a
from e6_prose import interval, signed, thousands
from paper_tables import f

ROOT = a.ROOT
GREEN, RED, BOLD, RESET = "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def claims(rows):
    s, c = a.summary(rows), a.contrasts(rows)
    pos, blk = a.position_trend(rows), a.block_trend(rows)
    out = [("case means", f"{thousands(s['docker']['mean'])}, {thousands(s['docker_aa']['mean'])} (A/A), "
                          f"{thousands(s['docker_prometheus']['mean'])} and {thousands(s['docker_full']['mean'])}\\,req/s")]
    for key, label in [("docker_aa", "A/A"), ("docker_prometheus", "+Prometheus"), ("docker_full", "+Grafana")]:
        d = c[key]
        out.append((f"{label} vs Docker", f"{signed(d['diff'], 0)}\\,req/s, 95\\% CI {interval(d['lo'], d['hi'], 0)} "
                                          f"({signed(d['pct'], 1)}\\%)"))
    p = c["full_vs_pooled_docker"]
    out.append(("+Grafana vs pooled Docker", f"{signed(p['diff'], 0)}\\,req/s, 95\\% CI {interval(p['lo'], p['hi'], 0)}"))
    out.append(("block slope", f"{signed(blk['slope'], 1)}\\,req/s per block, 95\\% CI {interval(blk['lo'], blk['hi'], 1)}"))
    blocks = max(int(r["block"]) for r in rows)
    allmean = statistics.mean(float(r["throughput_rps"]) for r in rows)
    out.append(("drift pct", f"about {f(100 * -blk['slope'] * (blocks - 1) / allmean, 0)}\\% over the {blocks} blocks"))
    out.append(("position slope", f"{signed(pos['slope'], 0)}\\,req/s per position, 95\\% CI {interval(pos['lo'], pos['hi'], 0)}"))
    g = lambda case, lo, hi: [float(r["throughput_rps"]) for r in rows if r["case"] == case and lo <= int(r["block"]) <= hi]
    first = g("docker", 1, 7) + g("docker_aa", 1, 7)
    mid, last = g("docker_prometheus", 8, 14), g("docker_full", 15, 20)
    m = [statistics.mean(x) for x in (first, mid, last)]
    out.append(("fixed-order mimic", f"{thousands(m[0])}, {thousands(m[1])} and {thousands(m[2])}\\,req/s, a "
                                     f"{signed(100 * (m[2] / m[0] - 1), 1)}\\% fall to the full stack"))
    out.append(("runs", f"{len(rows)} runs"))
    return out


def e5_claims(raw_dir):
    import csv
    parts = []
    for n in (1, 2):
        with open(os.path.join(raw_dir, f"exp5_aa_session{n}.csv"), newline="") as fh:
            d = [float(r["detection_seconds"]) for r in csv.DictReader(fh) if r["detection_seconds"]]
        parts.append(f"{f(statistics.mean(d), 2)}\\,s (SD {f(statistics.stdev(d), 2)}\\,s)")
    return [("E5 repeat sessions", f"gave {parts[0]} and {parts[1]}")]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(ROOT, "experiments", "raw", "exp2_interleaved.csv"))
    args = p.parse_args()
    with open(os.path.join(ROOT, "paper", "paper.tex")) as fh:
        paper = re.sub(r"\s+", " ", fh.read())
    miss = 0
    for label, text in claims(a.load(args.csv)) + e5_claims(os.path.dirname(args.csv)):
        ok = re.sub(r"\s+", " ", text) in paper
        miss += not ok
        print(f"  [{GREEN + 'MATCH' + RESET if ok else RED + 'MISSING' + RESET}] {label}: {text}")
    print(f"\n{BOLD}{'all' if not miss else 'not all'} E2i numbers found verbatim in paper.tex{RESET}")
    sys.exit(1 if miss else 0)


if __name__ == "__main__":
    main()
