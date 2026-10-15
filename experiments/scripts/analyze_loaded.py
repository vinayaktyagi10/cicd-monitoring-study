#!/usr/bin/env python3
"""Analysis of Experiment 7 (monitoring cost under background CPU load).

Rule fixed before data collection (see exp7_loaded_overhead.py and DECISIONS.md):
penalty(level) = mean throughput of docker minus docker_full, in req/s, so a positive penalty is
a cost of monitoring. Primary: DiD = penalty(60%) - penalty(0%) with a percentile-bootstrap 95% CI
(seed 1). Secondary: penalty at every level with a Welch 95% CI. Contention is "supported" only if
the DiD interval is entirely above zero.

    python analyze_loaded.py <exp7_loaded_overhead.csv> [--outdir DIR]
"""
import argparse
import csv
import os
import statistics

import stats_lib as sl

LO_LEVEL, HI_LEVEL = 0, 60


def load(path):
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] == "ok"]
    for r in rows:
        for k, v in list(r.items()):
            if k not in ("case", "timestamp", "status", "keepalive") and isinstance(v, str):
                try:
                    r[k] = float(v)
                except ValueError:
                    pass
    return rows


def group(rows):
    out = {}
    for r in rows:
        out.setdefault((r["case"], int(r["bg_target_pct"])), []).append(r["throughput_ok_rps"])
    return out


def levels(g):
    return sorted({lv for _, lv in g})


def contrasts(g):
    out = []
    for lv in levels(g):
        d, f = g[("docker", lv)], g[("docker_full", lv)]
        w = sl.welch(d, f)
        out.append({"level": lv, "n_docker": len(d), "n_full": len(f), "docker_mean": statistics.mean(d),
                    "full_mean": statistics.mean(f), "penalty": w["diff"], "lo": w["lo"], "hi": w["hi"],
                    "pct": 100 * w["diff"] / statistics.mean(d), "welch_p": w["p"],
                    "hedges_g": sl.hedges_g(d, f)})
    return out


def did(g, lo_level=LO_LEVEL, hi_level=HI_LEVEL):
    est, lo, hi = sl.bootstrap_did(g[("docker", hi_level)], g[("docker_full", hi_level)],
                                   g[("docker", lo_level)], g[("docker_full", lo_level)], seed=1)
    return {"lo_level": lo_level, "hi_level": hi_level, "did": est, "lo": lo, "hi": hi}


def verdict(d):
    if d["lo"] > 0:
        return "supported"
    if d["hi"] < 0:
        return "reversed"
    return "not supported"


def achieved(rows):
    out = []
    for lv in sorted({int(r["bg_target_pct"]) for r in rows}):
        sub = [r for r in rows if int(r["bg_target_pct"]) == lv]
        full = [r for r in sub if r["case"] == "docker_full"]
        out.append({"level": lv, "n": len(sub),
                    "host_busy_cores": statistics.mean(r["load_host_busy_cores"] for r in sub),
                    "burner_cores": statistics.mean(r.get("load_burner_cores", 0.0) for r in sub),
                    "monitoring_cores": statistics.mean(r["load_monitoring_cores"] for r in full) if full else 0.0})
    return out


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()} for r in rows)


def report(rows, g):
    print("== Achieved load (mean per level) ==")
    for a in achieved(rows):
        print(f"  target {a['level']:3d}%  n={a['n']:3d}  host busy {a['host_busy_cores']:.2f} cores  "
              f"burner {a['burner_cores']:.2f}  monitoring {a['monitoring_cores']:.3f}")
    print("== Monitoring penalty (docker - docker_full, req/s) per level ==")
    for c in contrasts(g):
        print(f"  {c['level']:3d}%  docker {c['docker_mean']:.0f}  full {c['full_mean']:.0f}  "
              f"penalty {c['penalty']:+.0f} [{c['lo']:+.0f}, {c['hi']:+.0f}] ({c['pct']:+.2f}%)  p={c['welch_p']:.3f}")
    d = did(g)
    print(f"== DiD penalty({d['hi_level']}%) - penalty({d['lo_level']}%) = {d['did']:+.0f} "
          f"[{d['lo']:+.0f}, {d['hi']:+.0f}] req/s -> contention {verdict(d)} ==")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--outdir")
    args = p.parse_args()
    outdir = args.outdir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.csv))),
                                         "results", "loaded_overhead")
    rows = load(args.csv)
    g = group(rows)
    report(rows, g)
    d = did(g)
    write_csv(os.path.join(outdir, "contrasts.csv"), contrasts(g))
    write_csv(os.path.join(outdir, "achieved_load.csv"), achieved(rows))
    write_csv(os.path.join(outdir, "did.csv"), [{**d, "verdict": verdict(d)}])


if __name__ == "__main__":
    main()
