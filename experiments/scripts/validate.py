#!/usr/bin/env python3
"""95% confidence intervals and effect sizes for every headline number in
the paper, and -- given a replication campaign directory -- a metric-by-metric
comparison of the original data against the replication.

    python validate.py                                   # original data only
    python validate.py --campaign experiments/replication/<id>

Original data = the first ORIGINAL_PASS_ROWS rows of experiments/raw/*.csv
(exactly what the paper's tables use). Replication data = every row of
<campaign>/raw/*.csv. Writes CSVs to experiments/results/validation/ (original
only) or <campaign>/results/ (with --campaign) and prints a report.

Replication verdict rule, fixed before any replication data existed:
CONSISTENT if the original mean lies inside the replication's 95% CI for the
mean, otherwise DIFFERENT. Effect sizes are reported regardless, because with
near-deterministic metrics (e.g. MTTR, std 0.006s) a practically irrelevant
shift is still DIFFERENT under that rule.
"""
import argparse
import csv
import math
import os
import statistics

import stats_lib as sl
from aggregate import ORIGINAL_PASS_ROWS, RAW_DIR

EXP_DIR = os.path.dirname(RAW_DIR)
IDLE_CPU_THRESHOLD = 1.0

METRICS = [
    ("E1", "exp1_deploy", ("config", "manual"), "wall_seconds", "Deploy time, manual (s)"),
    ("E1", "exp1_deploy", ("config", "docker"), "wall_seconds", "Deploy time, Docker (s)"),
    ("E1", "exp1_deploy", ("config", "full_pipeline"), "wall_seconds", "Deploy time, full pipeline (s)"),
    ("E1", "exp1_deploy", ("config", "docker_cicd"), "elapsed_seconds", "Deploy time, Docker+CI/CD (s)"),
    ("E2", "exp2_resource", ("case", "docker"), "throughput_rps", "Throughput, Docker (req/s)"),
    ("E2", "exp2_resource", ("case", "docker_prometheus"), "throughput_rps", "Throughput, +Prometheus (req/s)"),
    ("E2", "exp2_resource", ("case", "docker_full"), "throughput_rps", "Throughput, +Grafana (req/s)"),
    ("E2", "exp2_resource", ("case", "docker"), "p95_latency_ms", "p95 latency, Docker (ms)"),
    ("E2", "exp2_resource", ("case", "docker_prometheus"), "p95_latency_ms", "p95 latency, +Prometheus (ms)"),
    ("E2", "exp2_resource", ("case", "docker_full"), "p95_latency_ms", "p95 latency, +Grafana (ms)"),
    ("E2", "exp2_resource", ("case", "docker"), "app_cpu_mean", "App CPU%, Docker"),
    ("E2", "exp2_resource", ("case", "docker_prometheus"), "app_cpu_mean", "App CPU%, +Prometheus"),
    ("E2", "exp2_resource", ("case", "docker_full"), "app_cpu_mean", "App CPU%, +Grafana"),
    ("E2", "exp2_resource", ("case", "docker"), "app_mem_mb_mean", "App mem, Docker (MB)"),
    ("E2", "exp2_resource", ("case", "docker_prometheus"), "app_mem_mb_mean", "App mem, +Prometheus (MB)"),
    ("E2", "exp2_resource", ("case", "docker_full"), "app_mem_mb_mean", "App mem, +Grafana (MB)"),
    ("E2", "exp2_resource", ("case", "docker_prometheus"), "cadvisor_cpu_mean", "cAdvisor CPU%, +Prometheus"),
    ("E2", "exp2_resource", ("case", "docker_full"), "cadvisor_cpu_mean", "cAdvisor CPU%, +Grafana"),
    ("E2", "exp2_resource", ("case", "docker_prometheus"), "prometheus_cpu_mean", "Prometheus CPU%, +Prometheus"),
    ("E2", "exp2_resource", ("case", "docker_full"), "prometheus_cpu_mean", "Prometheus CPU%, +Grafana"),
    ("E2", "exp2_resource", ("case", "docker_full"), "grafana_cpu_mean", "Grafana CPU%, +Grafana"),
    ("E3", "exp3_cpu_stress", None, "detection_seconds", "CPU-stress MTTD (s)"),
    ("E3", "exp3_cpu_stress", None, "peak_cpu_percent", "CPU-stress peak CPU%"),
    ("E4", "exp4_memory_stress", None, "time_to_oom_seconds", "Time to OOM (s)"),
    ("E4", "exp4_memory_stress", None, "peak_mem_mb", "Peak memory (MB)"),
    ("E4", "exp4_memory_stress", None, "requests_before_failure", "Requests before OOM"),
    ("E5", "exp5_failure_recovery", None, "detection_seconds", "Failure MTTD (s)"),
    ("E5", "exp5_failure_recovery", None, "recovery_seconds", "MTTR (s)"),
]

RATES = [
    ("E1", "exp1_deploy", ("config", "docker_cicd"), "success", "True", "CI/CD deploy success"),
    ("E3", "exp3_cpu_stress", None, "detected", "True", "CPU stress detected"),
    ("E4", "exp4_memory_stress", None, "oom_killed", "True", "OOM-killed"),
]

COMPARISONS = [
    ("E1", "exp1_deploy", "config", "wall_seconds", "docker", "manual", "Docker vs manual deploy time"),
    ("E1", "exp1_deploy", "config", "wall_seconds", "full_pipeline", "docker", "Full pipeline vs Docker deploy time"),
    ("E2", "exp2_resource", "case", "throughput_rps", "docker", "docker_prometheus", "Throughput Docker vs +Prometheus"),
    ("E2", "exp2_resource", "case", "throughput_rps", "docker_prometheus", "docker_full", "Throughput +Prometheus vs +Grafana"),
    ("E2", "exp2_resource", "case", "throughput_rps", "docker", "docker_full", "Throughput Docker vs +Grafana"),
    ("E2", "exp2_resource", "case", "p95_latency_ms", "docker", "docker_prometheus", "p95 Docker vs +Prometheus"),
    ("E2", "exp2_resource", "case", "p95_latency_ms", "docker_prometheus", "docker_full", "p95 +Prometheus vs +Grafana"),
    ("E2", "exp2_resource", "case", "p95_latency_ms", "docker", "docker_full", "p95 Docker vs +Grafana"),
    ("E2", "exp2_resource", "case", "app_cpu_mean", "docker", "docker_prometheus", "App CPU Docker vs +Prometheus"),
    ("E2", "exp2_resource", "case", "app_cpu_mean", "docker_prometheus", "docker_full", "App CPU +Prometheus vs +Grafana"),
    ("E2", "exp2_resource", "case", "app_cpu_mean", "docker", "docker_full", "App CPU Docker vs +Grafana"),
]


def load(path, cap=None):
    if not os.path.exists(path):
        return None
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:cap] if cap else rows


def original(name):
    return load(os.path.join(RAW_DIR, f"{name}.csv"), ORIGINAL_PASS_ROWS[name])


def select(rows, flt, col):
    if rows is None:
        return []
    if flt:
        rows = [r for r in rows if r.get(flt[0]) == flt[1]]
    return [float(r[col]) for r in rows if r.get(col) not in (None, "", "None")]


def fmt(v, p=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return f"{v:.{p}f}"


def describe(vals):
    if not vals:
        return {"n": 0}
    m, lo, hi = sl.mean_ci(vals)
    return {"n": len(vals), "mean": m, "ci_lo": lo, "ci_hi": hi,
            "sd": sl.sd(vals) if len(vals) > 1 else float("nan"),
            "median": statistics.median(vals), "min": min(vals), "max": max(vals)}


def effect(a, b):
    if len(a) < 2 or len(b) < 2:
        return {}
    w = sl.welch(a, b)
    if sl.sd(a) == 0 and sl.sd(b) == 0:
        g = (float("nan"),) * 3
    else:
        g = sl.hedges_g_ci(a, b)
    return {"diff": w["diff"], "diff_lo": w["lo"], "diff_hi": w["hi"], "welch_t": w["t"], "welch_p": w["p"],
            "hedges_g": g[0], "g_lo": g[1], "g_hi": g[2], "cliffs_delta": sl.cliffs_delta(a, b),
            "mw_p": sl.mann_whitney_p(a, b)}


def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()})
    print(f"wrote {path}")


def metric_table(loader):
    out = []
    for exp, name, flt, col, label in METRICS:
        d = describe(select(loader(name), flt, col))
        out.append({"exp": exp, "metric": label, **d})
    return out


def rate_table(loader):
    out = []
    for exp, name, flt, col, ok, label in RATES:
        rows = loader(name) or []
        if flt:
            rows = [r for r in rows if r.get(flt[0]) == flt[1]]
        if not rows:
            continue
        k = sum(r[col] == ok for r in rows)
        lo, hi = sl.wilson_ci(k, len(rows))
        out.append({"exp": exp, "metric": label, "successes": k, "n": len(rows),
                    "rate": k / len(rows), "wilson_lo": lo, "wilson_hi": hi})
    return out


def idle_sample_table(loader):
    rows = loader("exp2_resource") or []
    out = []
    for case in ("docker", "docker_prometheus", "docker_full"):
        g = [r for r in rows if r["case"] == case and r.get("app_cpu_mean") not in ("", None)]
        if not g:
            continue
        cpu = [float(r["app_cpu_mean"]) for r in g]
        idle = [c for c in cpu if c < IDLE_CPU_THRESHOLD]
        busy = [c for c in cpu if c >= IDLE_CPU_THRESHOLD]
        lo, hi = sl.wilson_ci(len(idle), len(cpu))
        load_window = statistics.mean(float(r["wall_seconds"]) for r in g)
        out.append({"case": case, "n": len(cpu), "idle_samples": len(idle), "idle_frac": len(idle) / len(cpu),
                    "idle_frac_lo": lo, "idle_frac_hi": hi,
                    "busy_sample_mean_cpu": statistics.mean(busy) if busy else float("nan"),
                    "mean_load_window_s": load_window})
    return out


def comparison_table(loader):
    out = []
    for exp, name, gcol, col, a_key, b_key, label in COMPARISONS:
        rows = loader(name)
        a = select(rows, (gcol, a_key), col)
        b = select(rows, (gcol, b_key), col)
        out.append({"exp": exp, "comparison": label, "n_a": len(a), "n_b": len(b), **effect(a, b)})
    exp3 = load(os.path.join(RAW_DIR, "exp3_cpu_stress.csv"))
    if loader is original:
        a = [float(r["detection_seconds"]) for r in exp3[:20] if r["detection_seconds"]]
        b = [float(r["detection_seconds"]) for r in exp3[40:60] if r["detection_seconds"]]
        out.append({"exp": "E3", "comparison": "CPU-stress MTTD original vs 2026-09-10 isolated rerun",
                    "n_a": len(a), "n_b": len(b), **effect(a, b)})
    return out


def replication_table(rep_loader):
    out = []
    for exp, name, flt, col, label in METRICS:
        o = select(original(name), flt, col)
        r = select(rep_loader(name), flt, col)
        if not r:
            out.append({"exp": exp, "metric": label, "verdict": "NOT RUN"})
            continue
        do, dr = describe(o), describe(r)
        e = effect(r, o)
        inside = dr["n"] > 1 and dr["ci_lo"] <= do["mean"] <= dr["ci_hi"]
        out.append({"exp": exp, "metric": label, "orig_n": do["n"], "orig_mean": do["mean"],
                    "orig_ci_lo": do["ci_lo"], "orig_ci_hi": do["ci_hi"],
                    "rep_n": dr["n"], "rep_mean": dr["mean"], "rep_ci_lo": dr.get("ci_lo"),
                    "rep_ci_hi": dr.get("ci_hi"),
                    "rel_change_pct": 100 * (dr["mean"] - do["mean"]) / do["mean"] if do["mean"] else float("nan"),
                    **e, "verdict": "CONSISTENT" if inside else "DIFFERENT"})
    return out


def print_table(title, rows, cols):
    print(f"\n== {title} ==")
    widths = [max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, widths)))


def show_metrics(rows):
    print_table("Mean [95% CI] per metric", [
        {"exp": r["exp"], "metric": r["metric"], "n": r["n"],
         "mean [95% CI]": f"{fmt(r.get('mean'))} [{fmt(r.get('ci_lo'))}, {fmt(r.get('ci_hi'))}]",
         "sd(n-1)": fmt(r.get("sd")), "median": fmt(r.get("median"))} for r in rows],
        ["exp", "metric", "n", "mean [95% CI]", "sd(n-1)", "median"])


def show_rates(rows):
    print_table("Proportions, Wilson 95% CI", [
        {"exp": r["exp"], "metric": r["metric"], "k/n": f"{r['successes']}/{r['n']}",
         "rate [95% CI]": f"{r['rate']:.3f} [{r['wilson_lo']:.3f}, {r['wilson_hi']:.3f}]"} for r in rows],
        ["exp", "metric", "k/n", "rate [95% CI]"])


def show_comparisons(rows):
    print_table("Pairwise comparisons (A - B): Welch diff [95% CI], Hedges g [95% CI], Cliff's delta", [
        {"comparison": r["comparison"],
         "diff [95% CI]": f"{fmt(r.get('diff'))} [{fmt(r.get('diff_lo'))}, {fmt(r.get('diff_hi'))}]",
         "p(Welch)": fmt(r.get("welch_p"), 4), "p(MW)": fmt(r.get("mw_p"), 4),
         "g [95% CI]": f"{fmt(r.get('hedges_g'), 2)} [{fmt(r.get('g_lo'), 2)}, {fmt(r.get('g_hi'), 2)}]",
         "Cliff d": fmt(r.get("cliffs_delta"), 2)} for r in rows],
        ["comparison", "diff [95% CI]", "p(Welch)", "p(MW)", "g [95% CI]", "Cliff d"])


def show_idle(rows):
    print_table(f"E2 app-CPU sampling check: runs reading < {IDLE_CPU_THRESHOLD}% (idle)", [
        {"case": r["case"], "idle/n": f"{r['idle_samples']}/{r['n']}",
         "idle frac [95% CI]": f"{r['idle_frac']:.2f} [{r['idle_frac_lo']:.2f}, {r['idle_frac_hi']:.2f}]",
         "mean CPU% of non-idle runs": fmt(r["busy_sample_mean_cpu"], 2),
         "load window (s)": fmt(r["mean_load_window_s"], 3)} for r in rows],
        ["case", "idle/n", "idle frac [95% CI]", "mean CPU% of non-idle runs", "load window (s)"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign", help="replication campaign directory (contains raw/)")
    args = p.parse_args()

    if not args.campaign:
        out_dir = os.path.join(EXP_DIR, "results", "validation")
        m, r, c, i = metric_table(original), rate_table(original), comparison_table(original), idle_sample_table(original)
        show_metrics(m), show_rates(r), show_comparisons(c), show_idle(i)
        write_csv(os.path.join(out_dir, "original_metrics_ci.csv"), m)
        write_csv(os.path.join(out_dir, "original_rates_ci.csv"), r)
        write_csv(os.path.join(out_dir, "original_comparisons.csv"), c)
        write_csv(os.path.join(out_dir, "original_exp2_idle_samples.csv"), i)
        return

    camp = os.path.abspath(args.campaign)

    def rep(name):
        return load(os.path.join(camp, "raw", f"{name}.csv"))

    out_dir = os.path.join(camp, "results")
    m, r, c, i = metric_table(rep), rate_table(rep), comparison_table(rep), idle_sample_table(rep)
    rt = replication_table(rep)
    show_metrics(m), show_rates(r), show_comparisons(c), show_idle(i)
    print_table("Original vs replication (verdict: original mean inside replication 95% CI?)", [
        {"metric": x["metric"],
         "original [95% CI]": f"{fmt(x.get('orig_mean'))} [{fmt(x.get('orig_ci_lo'))}, {fmt(x.get('orig_ci_hi'))}]",
         "replication [95% CI]": f"{fmt(x.get('rep_mean'))} [{fmt(x.get('rep_ci_lo'))}, {fmt(x.get('rep_ci_hi'))}]",
         "change %": fmt(x.get("rel_change_pct"), 1), "g": fmt(x.get("hedges_g"), 2),
         "Cliff d": fmt(x.get("cliffs_delta"), 2), "verdict": x["verdict"]} for x in rt],
        ["metric", "original [95% CI]", "replication [95% CI]", "change %", "g", "Cliff d", "verdict"])
    write_csv(os.path.join(out_dir, "replication_metrics_ci.csv"), m)
    write_csv(os.path.join(out_dir, "replication_rates_ci.csv"), r)
    write_csv(os.path.join(out_dir, "replication_comparisons.csv"), c)
    write_csv(os.path.join(out_dir, "replication_exp2_idle_samples.csv"), i)
    write_csv(os.path.join(out_dir, "original_vs_replication.csv"), rt)


if __name__ == "__main__":
    main()
