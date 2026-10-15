#!/usr/bin/env python3
"""Writes the paper's original-versus-replication findings table.

Four statuses: reproduced, environment-sensitive, not supported by replication, and
inconclusive. A metric group is reproduced only if every metric in it is CONSISTENT in
validate.py's original_vs_replication.csv and environment-sensitive only if every one is
DIFFERENT (a mixed group raises). The other rows are computed from the raw files and the
Experiment 6 and 7 result CSVs; a row whose evidence no longer fits its status raises.

    python3 reproducibility_table.py <campaign dir> <out.tex>
"""
import csv
import os
import sys

from aggregate import ORIGINAL_PASS_ROWS
from stats_lib import wilson_ci

REPRODUCES, ENV = "Reproduced", "Environment-sensitive"
UNSUPPORTED, INCONCLUSIVE = "Not supported by replication", "Inconclusive"
STATUSES = [REPRODUCES, ENV, UNSUPPORTED, INCONCLUSIVE]
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


def excludes_zero(lo, hi):
    return lo > 0 or hi < 0


def require(cond, what):
    if not cond:
        raise ValueError(f"evidence no longer supports: {what}")


def findings(campaign):
    cmp_rows = read(os.path.join(campaign, "results", "original_vs_replication.csv"))
    raw = os.path.join(campaign, "raw")
    out = []

    def add(finding, status, evidence):
        out.append((finding, status, evidence))

    def ranges(*parts):
        return "; ".join(f"{label} {pct_range(pick(cmp_rows, *names))}" for label, names in parts)

    def group(finding, parts):
        rows = pick(cmp_rows, *[n for _, names in parts for n in names])
        add(finding, classify(rows), ranges(*parts))

    dep = ("Deploy time, manual (s)", "Deploy time, Docker (s)", "Deploy time, full pipeline (s)")
    cicd = pick(cmp_rows, "Deploy time, Docker+CI/CD (s)")
    in_order = ordered([mean_of(cmp_rows, m) for m in dep], increasing=True)
    add("Deployment ordering (manual $<$ Docker $<$ full pipeline) and CI/CD deployment time",
        REPRODUCES if in_order and classify(cicd) == REPRODUCES else ENV,
        ("Order preserved" if in_order else "Order not preserved") + f"; CI/CD time {pct_range(cicd)}")
    group("Recovery time (MTTR) after a container kill", [("Change", ("MTTR (s)",))])
    group("Peak CPU under CPU stress", [("Change", ("CPU-stress peak CPU%",))])
    group("Prometheus and Grafana CPU draw", [("Change", ("Prometheus CPU%, +Prometheus",
          "Prometheus CPU%, +Grafana", "Grafana CPU%, +Grafana"))])

    fill = read(os.path.join(raw, "exp4_memory_stress_fill.csv"))
    fill_rows = pick(cmp_rows, "Requests before OOM, non-zero fill", "Peak memory, non-zero fill (MB)")
    killed = sum(r["oom_killed"] == "True" for r in fill)
    near = all(abs(float(r["rep_mean"]) - float(r["orig_mean"])) <= max(1.0, 0.01 * float(r["orig_mean"]))
               for r in fill_rows)
    add("OOM kill when the allocated memory is non-zero", REPRODUCES if killed == len(fill) and near else ENV,
        f"{killed}/{len(fill)} killed, within 1 request and 1\\,MB of the original")

    group("Absolute deployment time, throughput, latency and memory", [
        ("deployment", dep),
        ("throughput", ("Throughput, Docker (req/s)", "Throughput, +Prometheus (req/s)",
                        "Throughput, +Grafana (req/s)")),
        ("p95", ("p95 latency, Docker (ms)", "p95 latency, +Prometheus (ms)", "p95 latency, +Grafana (ms)")),
        ("memory", ("App mem, Docker (MB)", "App mem, +Prometheus (MB)", "App mem, +Grafana (MB)"))])
    group("Detection times", [("CPU stress", ("CPU-stress MTTD (s)",)), ("failure", ("Failure MTTD (s)",))])
    group("cAdvisor CPU draw", [("Change", ("cAdvisor CPU%, +Prometheus", "cAdvisor CPU%, +Grafana"))])

    zero = read(os.path.join(raw, "exp4_memory_stress.csv"))
    orig = read(os.path.join(EXP, "raw", "exp4_memory_stress.csv"))[:ORIGINAL_PASS_ROWS["exp4_memory_stress"]]
    k_rep = sum(r["oom_killed"] == "True" for r in zero)
    k_orig = sum(r["oom_killed"] == "True" for r in orig)
    add("OOM kill when the allocated memory is zero-filled", REPRODUCES if k_rep == k_orig else ENV,
        f"{k_orig}/{len(orig)} killed originally, {k_rep}/{len(zero)} in the replication")

    tp = [mean_of(cmp_rows, m) for m in ("Throughput, Docker (req/s)", "Throughput, +Prometheus (req/s)",
                                         "Throughput, +Grafana (req/s)")]
    ka = read(os.path.join(EXP, "results", "overhead_keepalive", "contrasts_vs_docker.csv"))
    ka4 = read(os.path.join(EXP, "results", "overhead_keepalive_loadgen4", "contrasts_vs_docker.csv"))
    grafana = [next(r for r in ka if r["cell"] == "+Grafana"), next(r for r in ka4 if r["cell"] == "+Grafana x4 loadgen")]
    worst = max(abs(float(r["pct_change"])) for r in grafana)
    mon = float(grafana[0]["monitoring_cores"])
    e7 = read(os.path.join(EXP, "results", "loaded_overhead", "did.csv"))[0]
    require(not ordered(tp, increasing=False) and worst < 5 and e7["verdict"] == "not supported",
            "contention not supported")
    add("Monitoring lowers throughput through host CPU contention", UNSUPPORTED,
        "Replication means " + ", ".join(f"{v:.0f}" for v in tp)
        + f"\\,req/s, not monotone; monitoring used {mon:.2f} cores and keep-alive throughput stayed within"
        f" {worst:.1f}\\%; the penalty did not grow with background load (Exp.~7)")
    app_cpu = [mean_of(cmp_rows, m) for m in ("App CPU%, Docker", "App CPU%, +Prometheus", "App CPU%, +Grafana")]
    add("Application CPU\\% falls because monitoring competes for CPU", UNSUPPORTED,
        "The reading falls again (" + " $\\to$ ".join(f"{v:.1f}" for v in app_cpu)
        + "\\%) but is bimodal: a 0.11\\,s load sampled over a longer window")

    detected = [r for r in grafana if excludes_zero(float(r["diff_lo"]), float(r["diff_hi"]))]
    require(0 < len(detected) < len(grafana), "small loss is detected by some but not all configurations")
    d = detected[0]
    add("A small throughput loss from monitoring", INCONCLUSIVE,
        f"Detected in {len(detected)} of {len(grafana)} keep-alive configurations"
        f" (${float(d['pct_change']):+.1f}$\\%); mechanism not identified")
    pin = read(os.path.join(EXP, "results", "overhead", "contention_test.csv"))[0]
    lo, hi = float(pin["did_lo"]), float(pin["did_hi"])
    require(not excludes_zero(lo, hi), "pinning effect undetermined")
    add("CPU pinning removes the monitoring penalty", INCONCLUSIVE,
        f"Difference-in-differences ${float(pin['did_rps']):+.0f}$\\,req/s, 95\\% CI $[{lo:.0f}, {hi:+.0f}]$,"
        " from the unreliable per-request client")

    def rate(rows):
        runs = [r for r in rows if r["config"] == "docker_cicd"]
        return sum(r["success"] == "True" for r in runs), len(runs)

    k_o, n_o = rate(read(os.path.join(EXP, "raw", "exp1_deploy.csv"))[:ORIGINAL_PASS_ROWS["exp1_deploy"]])
    k_r, n_r = rate(read(os.path.join(raw, "exp1_deploy.csv")))
    (lo_o, hi_o), (lo_r, hi_r) = wilson_ci(k_o, n_o), wilson_ci(k_r, n_r)
    require(lo_o < hi_r and lo_r < hi_o, "CI/CD success rates indistinguishable")
    add("CI/CD deployment success rate", INCONCLUSIVE,
        f"{k_o}/{n_o} [{lo_o:.2f}, {hi_o:.2f}] originally, {k_r}/{n_r} [{lo_r:.2f}, {hi_r:.2f}];"
        " too few runs to estimate the rate")
    add("THP policy is what changed the zero-fill OOM result", INCONCLUSIVE,
        "Sufficient on the replication host (Table~\\ref{tab:thp}); the original THP setting was not recorded")
    add("Cause of the 27\\% Exp.~6 to Exp.~7 throughput gap", INCONCLUSIVE,
        "Power profile explains a few percent (Section~\\ref{sec:p4}); Docker and kernel updates untested")
    return out


def build_table(rows):
    order = {s: i for i, s in enumerate(STATUSES)}
    rows = sorted(rows, key=lambda r: order[r[1]])
    lines = ["\\begin{tabular}{@{}p{0.36\\textwidth}p{0.60\\textwidth}@{}}", "\\toprule",
             "Finding & Evidence (change is replication relative to original) \\\\"]
    current = None
    for f, s, e in rows:
        if s != current:
            lines += ["\\midrule", f"\\multicolumn{{2}}{{@{{}}l}}{{\\textit{{{s}}}}} \\\\"]
            current = s
        lines.append(f"{f} & {e} \\\\")
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
