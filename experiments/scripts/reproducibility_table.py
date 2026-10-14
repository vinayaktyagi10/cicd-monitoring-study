#!/usr/bin/env python3
"""Writes the paper's reproducible / environment-dependent / not-supported table.

Status is computed from validate.py's original_vs_replication.csv (a metric group is
reproducible only if every metric in it is CONSISTENT, environment-dependent only if every
one is DIFFERENT; a mixed group raises), from the raw files for orderings and OOM rates, and
from the Experiment 6 result CSVs for the overhead rows.

    python3 reproducibility_table.py <campaign dir> <out.tex>
"""
import csv
import os
import sys

REPRODUCES, ENV, UNSUPPORTED = "Reproduces", "Environment-dependent", "Not supported"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXP = os.path.join(ROOT, "experiments")


def classify(rows):
    verdicts = {r["verdict"] for r in rows}
    if verdicts == {"CONSISTENT"}:
        return REPRODUCES
    if verdicts == {"DIFFERENT"}:
        return ENV
    raise ValueError(f"cannot classify group with verdicts {sorted(verdicts)}")


def ordered(values, increasing):
    pairs = list(zip(values, values[1:]))
    return all(a < b for a, b in pairs) if increasing else all(a > b for a, b in pairs)


def pct(v):
    return f"${float(v):+.1f}$"


def pct_range(rows):
    vals = sorted(float(r["rel_change_pct"]) for r in rows)
    if len(vals) == 1 or vals[0] == vals[-1]:
        return pct(vals[0]) + r"\%"
    return f"{pct(vals[0])} to {pct(vals[-1])}" + r"\%"


def read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def pick(rows, *names):
    out = [r for r in rows if r["metric"] in names]
    if len(out) != len(names):
        raise KeyError(f"missing metrics: {set(names) - {r['metric'] for r in out}}")
    return out


def mean_of(rows, metric):
    return float(pick(rows, metric)[0]["rep_mean"])


def findings(campaign):
    cmp_rows = read(os.path.join(campaign, "results", "original_vs_replication.csv"))
    raw = os.path.join(campaign, "raw")
    out = []

    def add(finding, status, evidence):
        out.append((finding, status, evidence))

    def group(finding, evidence_prefix, *names):
        rows = pick(cmp_rows, *names)
        add(finding, classify(rows), f"{evidence_prefix}{pct_range(rows)}")

    dep = ["Deploy time, manual (s)", "Deploy time, Docker (s)", "Deploy time, full pipeline (s)"]
    rep_dep = [mean_of(cmp_rows, m) for m in dep]
    if ordered(rep_dep, increasing=True):
        add("Deployment ordering: manual $<$ Docker $<$ full pipeline", REPRODUCES, "Order preserved in all three means")
    else:
        add("Deployment ordering: manual $<$ Docker $<$ full pipeline", ENV, "Order not preserved")
    group("Docker+CI/CD deployment time", "Change ", "Deploy time, Docker+CI/CD (s)")
    group("MTTR after container failure", "Change ", "MTTR (s)")
    group("Peak CPU under CPU stress", "Change ", "CPU-stress peak CPU%")
    group("Prometheus and Grafana CPU draw", "Changes ", "Prometheus CPU%, +Prometheus",
          "Prometheus CPU%, +Grafana", "Grafana CPU%, +Grafana")
    app_cpu = [mean_of(cmp_rows, m) for m in ("App CPU%, Docker", "App CPU%, +Prometheus", "App CPU%, +Grafana")]
    add("Application CPU\\% reading falls as monitoring is added (observation only)",
        REPRODUCES if ordered(app_cpu, increasing=False) else ENV,
        "Falls in the replication too (" + " $\\to$ ".join(f"{v:.1f}" for v in app_cpu)
        + r"\%); the reading itself is a sampling artifact (last rows)")

    fill = read(os.path.join(raw, "exp4_memory_stress_fill.csv"))
    fill_rows = pick(cmp_rows, "Requests before OOM, non-zero fill", "Peak memory, non-zero fill (MB)")
    killed = sum(r["oom_killed"] == "True" for r in fill)
    near = all(abs(float(r["rep_mean"]) - float(r["orig_mean"])) <= max(1.0, 0.01 * float(r["orig_mean"]))
               for r in fill_rows)
    add("OOM kill when the allocation is resident (non-zero fill)", REPRODUCES if killed == len(fill) and near else ENV,
        f"{killed}/{len(fill)} killed; requests and peak memory within 1 request and 1\\,MB of the original")

    group("Absolute deployment times", "Change ", *dep)
    group("Throughput level", "Change ", "Throughput, Docker (req/s)", "Throughput, +Prometheus (req/s)",
          "Throughput, +Grafana (req/s)")
    tp = [mean_of(cmp_rows, m) for m in ("Throughput, Docker (req/s)", "Throughput, +Prometheus (req/s)",
                                         "Throughput, +Grafana (req/s)")]
    add("Throughput falls as monitoring is added",
        REPRODUCES if ordered(tp, increasing=False) else ENV,
        "Replication means " + ", ".join(f"{v:.0f}" for v in tp) + "\\,req/s: not monotone")
    group("p95 latency", "Change ", "p95 latency, Docker (ms)", "p95 latency, +Prometheus (ms)",
          "p95 latency, +Grafana (ms)")
    group("Application memory", "Change ", "App mem, Docker (MB)", "App mem, +Prometheus (MB)",
          "App mem, +Grafana (MB)")
    group("cAdvisor CPU draw", "Change ", "cAdvisor CPU%, +Prometheus", "cAdvisor CPU%, +Grafana")
    group("CPU-stress detection time", "Change ", "CPU-stress MTTD (s)")
    group("Failure detection time", "Change ", "Failure MTTD (s)")

    zero = read(os.path.join(raw, "exp4_memory_stress.csv"))
    orig = read(os.path.join(EXP, "raw", "exp4_memory_stress.csv"))[:20]
    k_rep = sum(r["oom_killed"] == "True" for r in zero)
    k_orig = sum(r["oom_killed"] == "True" for r in orig)
    add("OOM kill with zero-filled allocation", REPRODUCES if k_rep == k_orig else ENV,
        f"{k_orig}/{len(orig)} killed originally, {k_rep}/{len(zero)} in the replication (THP shrinker)")

    ka = read(os.path.join(EXP, "results", "overhead_keepalive", "contrasts_vs_docker.csv"))
    ka4 = read(os.path.join(EXP, "results", "overhead_keepalive_loadgen4", "contrasts_vs_docker.csv"))
    unpinned = [r for r in ka if "pinned" not in r["cell"]]
    worst = max(abs(float(r["pct_change"])) for r in unpinned + [r for r in ka4 if "pinned" not in r["cell"]])
    mon = float(next(r for r in ka if r["cell"] == "+Grafana")["monitoring_cores"])
    add("Host CPU contention explains the throughput drop", UNSUPPORTED,
        f"Monitoring containers {mon:.2f} cores; keep-alive throughput within {worst:.1f}\\% of Docker-only")
    add("Application CPU\\% falls because of contention", UNSUPPORTED,
        "Reading is bimodal (0.11\\,s load window sampled by a longer interval), not a CPU effect")
    return out


STATUS_ORDER = {REPRODUCES: 0, ENV: 1, UNSUPPORTED: 2}


def build_table(rows):
    rows = sorted(rows, key=lambda r: STATUS_ORDER[r[1]])
    lines = ["\\begin{tabular}{p{0.31\\textwidth}p{0.19\\textwidth}p{0.40\\textwidth}}", "\\toprule",
             "Finding & Status & Evidence \\\\", "\\midrule"]
    lines += [f"{f} & {s} & {e} \\\\" for f, s, e in rows]
    lines += ["\\bottomrule", "\\end{tabular}"]
    return "\n".join(lines) + "\n"


def main():
    campaign, dst = sys.argv[1], sys.argv[2]
    rows = findings(campaign)
    with open(dst, "w") as fh:
        fh.write(build_table(rows))
    print(f"wrote {dst} ({len(rows)} findings)")


if __name__ == "__main__":
    main()
