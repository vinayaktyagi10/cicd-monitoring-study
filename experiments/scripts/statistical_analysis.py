#!/usr/bin/env python3
"""Statistical validity checks for the paper's headline comparisons.

Everything here is computed from the existing raw CSVs in experiments/raw/
-- no new experimental data is generated. This exists to answer, with
numbers rather than assertion: (1) how tight is the CI/CD reliability
estimate given n=8, and (2) are the reported differences between monitoring
cases (RQ3: throughput/CPU/latency across docker / docker_prometheus /
docker_full) distinguishable from run-to-run noise, or not.
"""
import csv
import math
import os

from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RAW = os.path.join(ROOT, "experiments", "raw")


def load_raw(name):
    with open(os.path.join(RAW, f"{name}.csv"), newline="") as f:
        return list(csv.DictReader(f))


def wilson_ci(successes, n, z=1.96):
    """95% Wilson score interval for a binomial proportion -- the standard
    choice over the naive normal-approximation interval when n is small or
    p is near 0/1, both true here (n=8, p=7/8)."""
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)) / denom
    return centre - half, centre + half


def welch_t(a, b):
    """Welch's t-test (unequal variances, appropriate here since sample
    sizes are equal at n=20 but variances are not assumed equal) plus
    Cohen's d for effect size."""
    t, p = stats.ttest_ind(a, b, equal_var=False)
    pooled_sd = math.sqrt((stats.tstd(a) ** 2 + stats.tstd(b) ** 2) / 2)
    d = (stats.tmean(a) - stats.tmean(b)) / pooled_sd if pooled_sd else float("nan")
    return t, p, d


def section(title):
    print(f"\n{'=' * len(title)}\n{title}\n{'=' * len(title)}")


def main():
    section("1. CI/CD deployment reliability (RQ4) -- n=8, 7 successes")
    lo, hi = wilson_ci(7, 8)
    print(f"Point estimate: 7/8 = 87.5%")
    print(f"95% Wilson score CI: [{lo*100:.1f}%, {hi*100:.1f}%]")
    print("Interpretation: with only 8 trials, the true reliability could")
    print("plausibly be anywhere from about half to essentially all runs")
    print("succeeding. This interval, not the 87.5% point estimate alone,")
    print("is the honest statement of what n=8 supports.")

    section("2. Monitoring-case comparisons (RQ3) -- Welch's t-test, n=20 each")
    # exp2_resource.csv has been re-run multiple times since the original
    # data collection (see experiments/reproduction_run_2026-09-10.txt); the
    # first 60 rows are the original pass that results/*_summary.csv and the
    # paper's tables are built from, so restrict to those for consistency
    # with what's actually reported.
    rows = load_raw("exp2_resource")[:60]
    by_case = {}
    for r in rows:
        by_case.setdefault(r["case"], []).append(r)

    metrics = [
        ("app_cpu_mean", "Application CPU %"),
        ("throughput_rps", "Throughput (req/s)"),
        ("p95_latency_ms", "p95 latency (ms)"),
    ]
    pairs = [("docker", "docker_prometheus"), ("docker_prometheus", "docker_full"),
             ("docker", "docker_full")]

    for metric_key, metric_label in metrics:
        print(f"\n--- {metric_label} ---")
        for a_name, b_name in pairs:
            a = [float(r[metric_key]) for r in by_case[a_name]]
            b = [float(r[metric_key]) for r in by_case[b_name]]
            t, p, d = welch_t(a, b)
            sig = "significant (p<0.05)" if p < 0.05 else "NOT significant (p>=0.05)"
            print(f"  {a_name:18s} vs {b_name:18s}: "
                  f"t={t:+.2f}, p={p:.4f}, Cohen's d={d:+.2f}  -> {sig}")

    section("3. CPU-stress detection: original vs isolated reproduction runs")
    print("(sanity check: does the isolated re-run genuinely differ from the")
    print(" original 20-run pass, or is the 2.64s vs 5.65s gap noted in the")
    print(" reproduction writeup within normal sampling variance?)")
    exp3 = load_raw("exp3_cpu_stress")
    original = [float(r["detection_seconds"]) for r in exp3[:20] if r["detection_seconds"]]
    isolated = [float(r["detection_seconds"]) for r in exp3[-20:] if r["detection_seconds"]]
    if len(original) == 20 and len(isolated) == 20:
        t, p, d = welch_t(original, isolated)
        sig = "significant (p<0.05)" if p < 0.05 else "NOT significant (p>=0.05)"
        print(f"  original (n={len(original)}) vs isolated re-run (n={len(isolated)}): "
              f"t={t:+.2f}, p={p:.4f}, Cohen's d={d:+.2f}  -> {sig}")


if __name__ == "__main__":
    main()
