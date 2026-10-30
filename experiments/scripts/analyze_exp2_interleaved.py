#!/usr/bin/env python3
"""Analysis of raw/exp2_interleaved.csv (Exp 2 with shuffled case order and an A/A arm).

    python analyze_exp2_interleaved.py [--csv ../raw/exp2_interleaved.csv]
"""
import argparse
import csv
import os
import statistics

import stats_lib as sl

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES = ["docker", "docker_aa", "docker_prometheus", "docker_full"]


def load(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def by_case(rows, key="throughput_rps"):
    return {c: [float(r[key]) for r in rows if r["case"] == c and r[key] != ""] for c in CASES}


def summary(rows):
    g = by_case(rows)
    out = {}
    for c in CASES:
        m, lo, hi = sl.mean_ci(g[c])
        out[c] = {"n": len(g[c]), "mean": m, "sd": sl.sd(g[c]), "lo": lo, "hi": hi,
                  "errors": sum(1 for r in rows if r["case"] == c and float(r["error_rate"]) > 0)}
    return out


def contrasts(rows):
    g = by_case(rows)
    out = {}
    for c, ref in [("docker_aa", "docker"), ("docker_prometheus", "docker"), ("docker_full", "docker")]:
        w = sl.welch(g[c], g[ref])
        gv = sl.hedges_g_ci(g[c], g[ref])
        out[c] = {**w, "pct": 100 * w["diff"] / statistics.mean(g[ref]), "pct_lo": 100 * w["lo"] / statistics.mean(g[ref]),
                  "pct_hi": 100 * w["hi"] / statistics.mean(g[ref]), "g": gv[0]}
    pooled_docker = g["docker"] + g["docker_aa"]
    w = sl.welch(g["docker_full"], pooled_docker)
    out["full_vs_pooled_docker"] = {**w, "pct": 100 * w["diff"] / statistics.mean(pooled_docker)}
    return out


def position_trend(rows):
    x = [int(r["position"]) for r in rows]
    y = [float(r["throughput_rps"]) for r in rows]
    slope, lo, hi, _ = sl.ols(x, y)
    return {"slope": slope, "lo": lo, "hi": hi}


def block_trend(rows):
    x = [int(r["block"]) for r in rows]
    y = [float(r["throughput_rps"]) for r in rows]
    slope, lo, hi, _ = sl.ols(x, y)
    return {"slope": slope, "lo": lo, "hi": hi}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(ROOT, "experiments", "raw", "exp2_interleaved.csv"))
    args = p.parse_args()
    rows = load(args.csv)
    print(f"{len(rows)} runs, blocks {min(int(r['block']) for r in rows)}..{max(int(r['block']) for r in rows)}")
    for c, s in summary(rows).items():
        print(f"{c:18s} n={s['n']:2d} mean={s['mean']:.0f} sd={s['sd']:.0f} 95%CI [{s['lo']:.0f}, {s['hi']:.0f}] error-runs={s['errors']}")
    for c, d in contrasts(rows).items():
        print(f"{c:24s} diff={d['diff']:+.0f} CI [{d['lo']:+.0f}, {d['hi']:+.0f}] ({d['pct']:+.1f}%) p={d['p']:.3f}"
              + (f" g={d['g']:+.2f}" if "g" in d else ""))
    t = position_trend(rows)
    print(f"slope per position: {t['slope']:+.0f} req/s [{t['lo']:+.0f}, {t['hi']:+.0f}]")
    t = block_trend(rows)
    print(f"slope per block:    {t['slope']:+.1f} req/s [{t['lo']:+.1f}, {t['hi']:+.1f}]")


if __name__ == "__main__":
    main()
