#!/usr/bin/env python3
"""Recomputes every Experiment 7 number quoted in paper/paper.tex from
raw/exp7_loaded_overhead.csv and checks that each appears verbatim. Exit status 1 on any miss.

    python e7_prose.py [--csv ../raw/exp7_loaded_overhead.csv]
"""
import argparse
import os
import re
import sys

import statistics

import analyze_loaded as al
import analyze_overhead as ao
from e6_prose import interval, signed, thousands
from paper_tables import f

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GREEN, RED, BOLD, RESET = "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def claims(rows):
    g = al.group(rows)
    con = {c["level"]: c for c in al.contrasts(g)}
    ach = {a["level"]: a for a in al.achieved(rows)}
    d = al.did(g)
    out = []
    for lv in sorted(ach):
        out.append((f"achieved host load at {lv}%", f"{f(ach[lv]['host_busy_cores'], 1)} busy cores"))
    for lv in sorted(con):
        c = con[lv]
        out.append((f"penalty at {lv}%", f"{signed(c['penalty'], 0)}\\,req/s, 95\\% CI {interval(c['lo'], c['hi'], 0)}"))
        out.append((f"penalty pct at {lv}%", f"({signed(c['pct'], 1)}\\%)"))
    out.append(("DiD 60 vs 0", f"difference-in-differences {signed(d['did'], 0)}\\,req/s, 95\\% CI "
                               f"{interval(d['lo'], d['hi'], 0)}"))
    out.append(("verdict", f"contention {al.verdict(d)}"))
    n = min(c["n_docker"] for c in con.values())
    out.append(("runs per cell", f"{n} runs per cell"))
    hi = max(ach)
    out.append(("DiD upper bound as % of loaded throughput",
                f"about {f(100 * d['hi'] / con[hi]['docker_mean'], 0)}\\% of throughput"))
    cvs = {}
    for r in rows:
        cvs.setdefault((r["case"], int(r["bg_target_pct"])), []).append(r["throughput_ok_rps"])
    cv = {k: 100 * statistics.stdev(v) / statistics.mean(v) for k, v in cvs.items()}
    out.append(("min CV below top level", f"{f(min(v for (c, lv), v in cv.items() if lv < hi), 0)}--"
                                          f"{f(max(v for (c, lv), v in cv.items() if lv < hi), 0)}\\%"))
    out.append(("max CV at top level", f"up to {f(max(v for (c, lv), v in cv.items() if lv == hi), 0)}\\%"))
    mon = [a["monitoring_cores"] for a in ach.values()]
    out.append(("monitoring cores range", f"{f(min(mon), 3)}--{f(max(mon), 3)} cores"))
    lo = min(ach)
    d0 = [r for r in rows if r["case"] == "docker" and int(r["bg_target_pct"]) == lo]
    out.append(("E7 docker at 0%", f"{thousands(statistics.mean(r['throughput_ok_rps'] for r in d0))}\\,req/s"))
    out.append(("E7 other cores at 0%", f"{f(statistics.mean(r['load_other_cores'] for r in d0), 2)} cores"))
    e6 = [r for r in ao.load(os.path.join(ROOT, "experiments", "raw", "exp6_overhead_keepalive.csv"))
          if r["case"] == "docker" and not r["pinned"] and r["loadgen_procs"] == 1]
    e6m, e7m = statistics.mean(r["throughput_ok_rps"] for r in e6), statistics.mean(r["throughput_ok_rps"] for r in d0)
    out.append(("E6 keep-alive docker", f"{thousands(e6m)}\\,req/s in Experiment~6"))
    out.append(("E6 other cores", f"{f(statistics.mean(r['load_other_cores'] for r in e6), 2)} cores in Experiment~6"))
    out.append(("E7 vs E6 gap", f"{signed(100 * (e7m - e6m) / e6m, 0)}\\%"))
    out += power_claims()
    return out


def power_claims():
    import csv
    import stats_lib as sl
    with open(os.path.join(ROOT, "experiments", "raw", "diag_power.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    tp = lambda prof: [float(r["throughput_ok_rps"]) for r in rows if r["expected_profile"] == prof]
    perf, bal = tp("custom"), tp("balanced")
    slow = [v for v in perf + bal if v < 0.6 * statistics.median(perf + bal)]
    w = sl.welch(perf, bal)
    fast = [v for v in perf if v not in slow]
    w2 = sl.welch(fast, bal)
    return [
        ("power: median performance", f"{thousands(statistics.median(perf))}\\,req/s under performance"),
        ("power: median balanced", f"{thousands(statistics.median(bal))}\\,req/s under balanced"),
        ("power: runs per profile", f"{len(perf)} runs per profile"),
        ("power: all-run difference", f"{signed(w['diff'], 0)}\\,req/s, 95\\% CI {interval(w['lo'], w['hi'], 0)}"),
        ("power: slow runs", f"{len(slow)} runs at half speed"),
        ("power: difference without slow runs", f"{signed(w2['diff'], 0)}\\,req/s, 95\\% CI "
                                                f"{interval(w2['lo'], w2['hi'], 0)} ({signed(100 * w2['diff'] / statistics.mean(bal), 1)}\\%)"),
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(ROOT, "experiments", "raw", "exp7_loaded_overhead.csv"))
    args = p.parse_args()
    with open(os.path.join(ROOT, "paper", "paper.tex")) as fh:
        paper = re.sub(r"\s+", " ", fh.read())
    cl = claims(al.load(args.csv))
    misses = 0
    print(f"\n{BOLD}Experiment 7{RESET}")
    for what, text in cl:
        ok = re.sub(r"\s+", " ", text) in paper
        misses += not ok
        print(f"  [{GREEN + 'MATCH' if ok else RED + 'NOT FOUND'}{RESET}] {what}: {text}")
    print(f"\n{len(cl) - misses}/{len(cl)} E7 numbers found verbatim in paper.tex")
    sys.exit(1 if misses else 0)


if __name__ == "__main__":
    main()
