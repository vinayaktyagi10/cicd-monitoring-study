#!/usr/bin/env python3
"""Recomputes every Experiment 6 number quoted in paper/paper.tex from a
replication campaign's raw/ (exp6_overhead*.csv, diag_timewait.csv) and
checks that each formatted string appears verbatim in the paper, as
paper_tables.py does for the original dataset. Exit status 1 on any miss.

    python e6_prose.py --campaign ../replication/<dir>
"""
import argparse
import csv
import os
import re
import statistics
import sys

import analyze_overhead as ao
import stats_lib as sl
from paper_tables import f

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GREEN, RED, BOLD, RESET = "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def thousands(v):
    return f"{int(round(v)):,}".replace(",", "{,}")


def signed(v, places):
    s = f(v, places)
    return f"${s if s.startswith('-') else '+' + s}$"


def interval(lo, hi, places):
    a, b = f(lo, places), f(hi, places)
    if a.startswith("-") and not b.startswith("-"):
        b = "+" + b
    return f"$[{a}, {b}]$"


def unpinned(rows, procs=1):
    return [r for r in rows if not r["pinned"] and r["loadgen_procs"] == procs]


def by_case(rows, case):
    return [r["throughput_ok_rps"] for r in rows if r["case"] == case]


def cv_pct(x):
    return 100 * statistics.stdev(x) / statistics.mean(x)


def diag_claims(path):
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    per = [r for r in rows if r["mode"] == "per_request"]
    ka = [r for r in rows if r["mode"] == "keepalive"]
    num = lambda rs, c: [float(r[c]) for r in rs]
    start = [r for r in per if float(r["t_s"]) <= 5]
    late = [r for r in per if float(r["t_s"]) > 30]
    reps = len({r["rep"] for r in rows})
    return [
        ("ephemeral port range", f"{thousands(int(rows[0]['port_range_size']))} ephemeral ports"),
        ("reps per client", f"{reps} repetitions per client"),
        ("per-request rps, first 5 s", f"{thousands(statistics.mean(num(start, 'ok_rps')))}\\,req/s in the first 5\\,s"),
        ("per-request rps, after 30 s", f"{thousands(statistics.mean(num(late, 'ok_rps')))}\\,req/s after 30\\,s"),
        ("per-request peak TIME_WAIT", f"{thousands(max(num(per, 'timewait')))} TIME\\_WAIT sockets"),
        ("per-request proxy sys after 30 s", f"{f(statistics.mean(num(late, 'proxy_sys_cores')), 1)} cores of system time"),
        ("per-request proxy user after 30 s", f"{f(statistics.mean(num(late, 'proxy_user_cores')), 2)} of user time"),
        ("keep-alive rps", f"{thousands(statistics.mean(num(ka, 'ok_rps')))}\\,req/s throughout"),
        ("keep-alive peak TIME_WAIT", f"at most {thousands(max(num(ka, 'timewait')))} TIME\\_WAIT sockets"),
        ("keep-alive proxy sys", f"docker-proxy at {f(statistics.mean(num(ka, 'proxy_sys_cores')), 2)} cores"),
    ]


def per_request_claims(rows):
    u = unpinned(rows)
    tp = [r["throughput_ok_rps"] for r in rows]
    px = [r["load_proxy_cores"] for r in rows]
    r_px, _, lo_px, hi_px = sl.pearson([r["load_proxy_cores"] for r in u], [r["throughput_ok_rps"] for r in u])
    r_host, _, lo_h, hi_h = sl.pearson([r["load_host_busy_cores"] for r in u], [r["throughput_ok_rps"] for r in u])
    return [
        ("throughput range, all runs", f"{thousands(min(tp))}--{thousands(max(tp))}\\,req/s"),
        ("runs below 500 req/s", f"{sum(t < 500 for t in tp)} of {len(tp)} runs below 500\\,req/s"),
        ("docker-proxy cores range", f"docker-proxy used {f(min(px), 1)}--{f(max(px), 1)} cores"),
        ("r(throughput, host busy)", f"$r{{=}}{f(r_host, 2)}$"),
        ("r(throughput, docker-proxy)", f"$r{{=}}{f(r_px, 3)}$, 95\\% CI {interval(lo_px, hi_px, 3)}"),
    ]


def keepalive_claims(rows, rows4, per_rows):
    u = unpinned(rows)
    cs = ao.cells(rows)
    con = {c["cell"]: c for c in ao.contrasts(cs)}
    full = con[ao.cell_name(("docker_full", False, 1))]
    worst = max((c for c in con.values() if "pinned" not in c["cell"]), key=lambda c: abs(c["pct_change"]))
    did = ao.contention_test(cs)[0]
    mon = statistics.mean(r["load_monitoring_cores"] for r in u if r["case"] == "docker_full")
    app = [r["load_app_cores"] for r in u]
    cases = ["docker", "docker_cadvisor", "docker_prometheus", "docker_full"]
    cv_ka = max(cv_pct(by_case(u, c)) for c in cases)
    cv_per = min(cv_pct(by_case(unpinned(per_rows), c)) for c in cases)
    out = [
        ("+Grafana vs Docker, diff", f"{signed(full['throughput_diff'], 0)}\\,req/s, 95\\% CI "
                                     f"{interval(full['diff_lo'], full['diff_hi'], 0)}"),
        ("+Grafana vs Docker, pct", f"({signed(full['pct_change'], 1)}\\%)"),
        ("+Grafana vs Docker, Hedges g", f"Hedges' $g{{=}}{f(full['hedges_g'], 2)}$ "
                                         f"{interval(full['g_lo'], full['g_hi'], 2)}"),
        ("largest |pct| of any monitored case", f"no monitored case moved throughput by more than "
                                                f"{f(abs(worst['pct_change']), 1)}\\%"),
        ("+Grafana monitoring cores", f"{f(mon, 3)} cores for cAdvisor, Prometheus and Grafana together"),
        ("app cores range", f"application container at {f(min(app), 2)}--{f(max(app), 2)} cores"),
        ("max within-case CV, keep-alive", f"at most {f(cv_ka, 1)}\\%"),
        ("min within-case CV, per-request", f"at least {f(cv_per, 0)}\\%"),
        ("pinning DiD", f"difference-in-differences {signed(did['did_rps'], 0)}\\,req/s, 95\\% CI "
                        f"{interval(did['did_lo'], did['did_hi'], 0)}"),
    ]
    if rows4:
        cs4 = ao.cells(rows4)
        c4 = {c["cell"]: c for c in ao.contrasts(cs4)}[ao.cell_name(("docker_full", False, 4))]
        out.append(("loadgen x4 +Grafana vs Docker", f"four load-generator processes "
                                                     f"({signed(c4['pct_change'], 1)}\\%, 95\\% CI "
                                                     f"{interval(c4['diff_lo'], c4['diff_hi'], 0)}\\,req/s)"))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign", required=True)
    args = p.parse_args()
    raw = os.path.join(args.campaign, "raw")
    with open(os.path.join(ROOT, "paper", "paper.tex")) as fh:
        paper = re.sub(r"\s+", " ", fh.read())

    per_rows = ao.load(os.path.join(raw, "exp6_overhead.csv"))
    ka_rows = ao.load(os.path.join(raw, "exp6_overhead_keepalive.csv"))
    ka4_path = os.path.join(raw, "exp6_overhead_keepalive_loadgen4.csv")
    ka4_rows = ao.load(ka4_path) if os.path.exists(ka4_path) else []
    sections = [
        ("TIME_WAIT diagnostic", "diag_timewait.csv", diag_claims(os.path.join(raw, "diag_timewait.csv"))),
        ("E6, new connection per request", "exp6_overhead.csv", per_request_claims(per_rows)),
        ("E6, keep-alive", "exp6_overhead_keepalive*.csv", keepalive_claims(ka_rows, ka4_rows, per_rows)),
    ]
    misses = 0
    for title, src, claims in sections:
        print(f"\n{BOLD}{title}{RESET}  ({src})")
        for what, text in claims:
            ok = re.sub(r"\s+", " ", text) in paper
            misses += not ok
            print(f"  [{GREEN + 'MATCH' if ok else RED + 'NOT FOUND'}{RESET}] {what}: {text}")
    n = sum(len(c) for _, _, c in sections)
    print(f"\n{n - misses}/{n} E6 numbers found verbatim in paper.tex")
    sys.exit(1 if misses else 0)


if __name__ == "__main__":
    main()
