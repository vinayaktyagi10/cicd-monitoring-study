#!/usr/bin/env python3
"""Analysis of Experiment 6 (exp6_overhead.csv): how monitoring overhead,
total host CPU and throughput relate.

    python analyze_overhead.py <exp6_overhead.csv> [--outdir DIR]

Answers, each with 95% intervals:
 1. per cell (case x pinned x loadgen procs): throughput, latency, and where
    the host's busy CPU went (app / monitoring / load generator / docker-proxy
    / unattributed background);
 2. throughput change vs the Docker-only case, as a difference, Hedges' g
    and Cliff's delta;
 3. contention test: does the Docker -> +Grafana throughput drop shrink when
    app, load generator and monitoring are pinned to disjoint cores?
    (bootstrap difference-in-differences);
 4. run-level relationship: throughput vs monitoring cores, vs background
    ("other") cores and vs total host busy cores -- pooled, and within case
    (case means removed, so only run-to-run variation is left);
 5. bottleneck: is the app (~1 core under the GIL) or the load generator
    saturated?
Writes CSVs and figures to --outdir (default: <csv dir>/../results/overhead).
"""
import argparse
import csv
import os
import statistics

import stats_lib as sl

CASE_ORDER = ["docker", "docker_cadvisor", "docker_prometheus", "docker_full"]
CASE_LABEL = {"docker": "Docker", "docker_cadvisor": "+cAdvisor", "docker_prometheus": "+Prometheus",
              "docker_full": "+Grafana"}
PARTS = [("load_app_cores", "App"), ("load_monitoring_cores", "Monitoring"),
         ("load_loadgen_cores", "Load generator"), ("load_proxy_cores", "docker-proxy"),
         ("load_other_cores", "Other (background)")]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SUMMARY_COLS = ["throughput_ok_rps", "p95_latency_ms", "load_host_busy_cores"] + [p for p, _ in PARTS] + \
               ["idle_monitoring_cores", "idle_host_busy_cores", "errors"]


def load(path):
    with open(path, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] == "ok"]
    for r in rows:
        r["pinned"] = r["pinned"] == "True"
        r["loadgen_procs"] = int(r.get("loadgen_procs") or 1)
        for k, v in list(r.items()):
            if isinstance(v, str) and k not in ("case", "timestamp", "status"):
                try:
                    r[k] = float(v)
                except ValueError:
                    pass
            if r[k] == "" and k.endswith("_cores"):
                r[k] = 0.0
    return rows


def cells(rows):
    out = {}
    for r in rows:
        out.setdefault((r["case"], r["pinned"], r["loadgen_procs"]), []).append(r)
    return dict(sorted(out.items(), key=lambda kv: (kv[0][2], kv[0][1], CASE_ORDER.index(kv[0][0]))))


def col(rows, c):
    return [r[c] for r in rows if isinstance(r.get(c), float)]


def cell_name(key):
    case, pinned, procs = key
    return f"{CASE_LABEL[case]}{' pinned' if pinned else ''}{f' x{procs} loadgen' if procs > 1 else ''}"


def summary_table(cs):
    out = []
    for key, rows in cs.items():
        row = {"cell": cell_name(key), "case": key[0], "pinned": key[1], "loadgen_procs": key[2], "n": len(rows)}
        for c in SUMMARY_COLS:
            v = col(rows, c)
            if len(v) > 1:
                m, lo, hi = sl.mean_ci(v)
                row.update({f"{c}_mean": m, f"{c}_lo": lo, f"{c}_hi": hi})
        out.append(row)
    return out


def contrasts(cs):
    out = []
    for (case, pinned, procs), rows in cs.items():
        base = cs.get(("docker", pinned, procs))
        if case == "docker" or not base:
            continue
        a, b = col(rows, "throughput_ok_rps"), col(base, "throughput_ok_rps")
        w = sl.welch(a, b)
        g = sl.hedges_g_ci(a, b)
        mon = statistics.mean(col(rows, "load_monitoring_cores"))
        out.append({"cell": cell_name((case, pinned, procs)), "vs": cell_name(("docker", pinned, procs)),
                    "throughput_diff": w["diff"], "diff_lo": w["lo"], "diff_hi": w["hi"],
                    "pct_change": 100 * w["diff"] / statistics.mean(b), "welch_p": w["p"],
                    "hedges_g": g[0], "g_lo": g[1], "g_hi": g[2], "cliffs_delta": sl.cliffs_delta(a, b),
                    "monitoring_cores": mon,
                    "rps_lost_per_monitoring_core": -w["diff"] / mon if mon else float("nan")})
    return out


def contention_test(cs):
    out = []
    for procs in sorted({k[2] for k in cs}):
        keys = [("docker", False, procs), ("docker_full", False, procs), ("docker", True, procs),
                ("docker_full", True, procs)]
        if not all(k in cs for k in keys):
            continue
        a1, b1, a2, b2 = (col(cs[k], "throughput_ok_rps") for k in keys)
        did, lo, hi = sl.bootstrap_did(a1, b1, a2, b2, seed=1)
        drop_u = statistics.mean(a1) - statistics.mean(b1)
        drop_p = statistics.mean(a2) - statistics.mean(b2)
        out.append({"loadgen_procs": procs, "drop_unpinned_rps": drop_u, "drop_pinned_rps": drop_p,
                    "did_rps": did, "did_lo": lo, "did_hi": hi,
                    "share_of_drop_removed_by_pinning": did / drop_u if drop_u else float("nan")})
    return out


def relationships(rows):
    out = []
    for procs in sorted({r["loadgen_procs"] for r in rows}):
        sub = [r for r in rows if not r["pinned"] and r["loadgen_procs"] == procs]
        if len(sub) < 5:
            continue
        means = {c: {} for c in ("throughput_ok_rps", "load_monitoring_cores", "load_other_cores",
                                 "load_host_busy_cores", "load_app_cores")}
        for case in {r["case"] for r in sub}:
            g = [r for r in sub if r["case"] == case]
            for c in means:
                means[c][case] = statistics.mean(col(g, c))
        y = [r["throughput_ok_rps"] for r in sub]
        yw = [r["throughput_ok_rps"] - means["throughput_ok_rps"][r["case"]] for r in sub]
        for x_col in ("load_monitoring_cores", "load_other_cores", "load_host_busy_cores", "load_app_cores"):
            x = [r[x_col] for r in sub]
            xw = [r[x_col] - means[x_col][r["case"]] for r in sub]
            for scope, xs, ys in (("pooled", x, y), ("within-case", xw, yw)):
                if statistics.pstdev(xs) == 0:
                    continue
                r_, p, lo, hi = sl.pearson(xs, ys)
                slope, slo, shi, _ = sl.ols(xs, ys)
                out.append({"loadgen_procs": procs, "x": x_col, "scope": scope, "n": len(xs), "r": r_,
                            "r_lo": lo, "r_hi": hi, "p": p, "slope_rps_per_core": slope,
                            "slope_lo": slo, "slope_hi": shi})
    return out


def write_csv(path, rows):
    if not rows:
        return
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    print(f"wrote {path}")


def figures(cs, rows, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#52514e", "axes.labelcolor": "#0b0b0b",
                         "xtick.color": "#52514e", "ytick.color": "#52514e", "axes.grid": True,
                         "grid.color": "#e4e3df", "grid.linewidth": 0.6, "axes.axisbelow": True})
    keys = list(cs)
    labels = [cell_name(k).replace(" pinned", "\npinned").replace(" x", "\nx") for k in keys]

    fig, ax = plt.subplots(figsize=(max(5, 0.9 * len(keys)), 3))
    for i, k in enumerate(keys):
        m, lo, hi = sl.mean_ci(col(cs[k], "throughput_ok_rps"))
        c = COLORS[0] if not k[1] else COLORS[1]
        ax.bar(i, m, 0.62, color=c, edgecolor="white", linewidth=2)
        ax.errorbar(i, m, yerr=[[m - lo], [hi - m]], color="#0b0b0b", capsize=3, linewidth=1)
        ax.annotate(f"{m:.0f}", (i, hi), textcoords="offset points", xytext=(0, 3), ha="center",
                    fontsize=7.5, color="#0b0b0b")
    ax.set_xticks(range(len(keys)), labels, fontsize=7.5)
    ax.set_ylabel("Successful requests/s\n(mean, 95% CI)")
    ax.grid(axis="x", visible=False)
    _save(fig, outdir, "exp6_throughput")

    fig, ax = plt.subplots(figsize=(max(5, 0.9 * len(keys)), 3.2))
    bottom = [0.0] * len(keys)
    for (c, name), color in zip(PARTS, COLORS):
        vals = [statistics.mean(col(cs[k], c)) if col(cs[k], c) else 0.0 for k in keys]
        ax.bar(range(len(keys)), vals, 0.62, bottom=bottom, color=color, label=name,
               edgecolor="white", linewidth=1.5)
        bottom = [b + v for b, v in zip(bottom, vals)]
    for i, k in enumerate(keys):
        ax.annotate(f"{bottom[i]:.2f}", (i, bottom[i]), textcoords="offset points", xytext=(0, 3),
                    ha="center", fontsize=7.5, color="#0b0b0b")
    ax.set_xticks(range(len(keys)), labels, fontsize=7.5)
    ax.set_ylabel("Host CPU during load (cores)")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.28))
    _save(fig, outdir, "exp6_host_cpu_breakdown")

    sub = [r for r in rows if not r["pinned"] and r["loadgen_procs"] == 1]
    present = [c for c in CASE_ORDER if any(r["case"] == c for r in sub)]
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.9), sharey=True)
    for ax, x_col, xlabel in ((axes[0], "load_monitoring_cores", "Monitoring containers' CPU (cores)"),
                              (axes[1], "load_other_cores", "Unattributed background CPU (cores)")):
        for case, color in zip(present, COLORS):
            g = [r for r in sub if r["case"] == case]
            ax.scatter([r[x_col] for r in g], [r["throughput_ok_rps"] for r in g], s=22, color=color,
                       edgecolor="white", linewidth=0.8, label=CASE_LABEL[case])
        ax.set_xlabel(xlabel)
    axes[0].set_ylabel("Successful requests/s")
    axes[1].legend(frameon=False, fontsize=7)
    _save(fig, outdir, "exp6_throughput_vs_cpu")


def _save(fig, outdir, name):
    import matplotlib.pyplot as plt
    path = os.path.join(outdir, f"{name}.pdf")
    fig.savefig(path, bbox_inches="tight", metadata={"CreationDate": None})
    fig.savefig(os.path.join(outdir, f"{name}.png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"wrote {path}")


def fmt(v, p=1):
    return "" if v is None or v == "" else f"{v:.{p}f}"


def report(summary, con, did, rel):
    print("\n== Per cell: mean [95% CI] ==")
    for s in summary:
        print(f"{s['cell']:28s} n={s['n']:2d}  rps {fmt(s.get('throughput_ok_rps_mean'), 0)} "
              f"[{fmt(s.get('throughput_ok_rps_lo'), 0)}, {fmt(s.get('throughput_ok_rps_hi'), 0)}]  "
              f"host {fmt(s.get('load_host_busy_cores_mean'), 2)}  app {fmt(s.get('load_app_cores_mean'), 2)}  "
              f"mon {fmt(s.get('load_monitoring_cores_mean'), 2)}  loadgen {fmt(s.get('load_loadgen_cores_mean'), 2)}  "
              f"proxy {fmt(s.get('load_proxy_cores_mean'), 2)}  other {fmt(s.get('load_other_cores_mean'), 2)}  "
              f"idle-mon {fmt(s.get('idle_monitoring_cores_mean'), 3)}")
    print("\n== Throughput vs Docker-only (same pinning / loadgen) ==")
    for c in con:
        print(f"{c['cell']:28s} {c['throughput_diff']:+8.1f} rps [{c['diff_lo']:+.1f}, {c['diff_hi']:+.1f}] "
              f"({c['pct_change']:+.1f}%)  g={c['hedges_g']:+.2f} [{c['g_lo']:+.2f}, {c['g_hi']:+.2f}]  "
              f"Cliff={c['cliffs_delta']:+.2f}  p={c['welch_p']:.4f}  mon={c['monitoring_cores']:.3f} cores")
    print("\n== Contention test: (Docker - +Grafana) unpinned minus pinned ==")
    for d in did:
        print(f"loadgen x{d['loadgen_procs']}: drop unpinned {d['drop_unpinned_rps']:.1f}, pinned "
              f"{d['drop_pinned_rps']:.1f}, DiD {d['did_rps']:.1f} [{d['did_lo']:.1f}, {d['did_hi']:.1f}] rps")
    print("\n== Throughput vs CPU, unpinned runs (r [95% CI], slope rps/core [95% CI]) ==")
    for x in rel:
        print(f"loadgen x{x['loadgen_procs']} {x['scope']:11s} {x['x']:24s} r={x['r']:+.2f} "
              f"[{x['r_lo']:+.2f}, {x['r_hi']:+.2f}] p={x['p']:.4f}  slope={x['slope_rps_per_core']:+.0f} "
              f"[{x['slope_lo']:+.0f}, {x['slope_hi']:+.0f}]")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--outdir")
    args = p.parse_args()
    outdir = args.outdir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.csv))),
                                         "results", "overhead")
    os.makedirs(outdir, exist_ok=True)
    rows = load(args.csv)
    cs = cells(rows)
    summary, con, did, rel = summary_table(cs), contrasts(cs), contention_test(cs), relationships(rows)
    report(summary, con, did, rel)
    write_csv(os.path.join(outdir, "cells.csv"), summary)
    write_csv(os.path.join(outdir, "contrasts_vs_docker.csv"), con)
    write_csv(os.path.join(outdir, "contention_test.csv"), did)
    write_csv(os.path.join(outdir, "throughput_vs_cpu.csv"), rel)
    figures(cs, rows, outdir)


if __name__ == "__main__":
    main()
