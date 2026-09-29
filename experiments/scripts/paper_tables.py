#!/usr/bin/env python3
"""Recomputes every numeric table and prose result in paper/paper.tex from
experiments/raw/, prints it in the paper's layout, and checks that each
formatted line appears verbatim in paper.tex. No paper values are stored
here: a MATCH means the string built from raw data was found in the paper.
"""
import csv
import os
import re
import statistics
from decimal import ROUND_HALF_UP, Decimal

from aggregate import ORIGINAL_PASS_ROWS, RAW_DIR

ROOT = os.path.dirname(os.path.dirname(RAW_DIR))
with open(os.path.join(ROOT, "paper", "paper.tex")) as fh:
    PAPER = re.sub(r"\s+", " ", fh.read())

GREEN, RED, BOLD, RESET = "\033[32m", "\033[31m", "\033[1m", "\033[0m"
results = []


def load(name):
    with open(os.path.join(RAW_DIR, f"{name}.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[:ORIGINAL_PASS_ROWS[name]]


def col(rows, name):
    return [float(r[name]) for r in rows if r.get(name) not in (None, "")]


def stats(vals):
    return statistics.mean(vals), statistics.pstdev(vals), min(vals), max(vals)


def f(v, places):
    return str(Decimal(repr(v)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def check(line):
    ok = re.sub(r"\s+", " ", line) in PAPER
    results.append(ok)
    tag = f"{GREEN}MATCH{RESET}" if ok else f"{RED}NOT FOUND{RESET}"
    print(f"  [{tag}] {line}")


def header(title, source):
    print(f"\n{BOLD}{title}{RESET}\n  source: {source}")


def table_iii():
    rows = load("exp1_deploy")
    header("Table III - Deployment time by configuration (seconds)",
           f"raw/exp1_deploy.csv, first {ORIGINAL_PASS_ROWS['exp1_deploy']} rows")
    labels = [("manual", "Manual (Baseline A)", "wall_seconds"),
              ("docker", "Docker (Baseline B)", "wall_seconds"),
              ("docker_cicd", "Docker+CI/CD", "elapsed_seconds"),
              ("full_pipeline", "Full pipeline", "wall_seconds")]
    for key, label, metric in labels:
        group = [r for r in rows if r["config"] == key]
        fails = sum(r["success"] != "True" for r in group)
        m, s, lo, hi = stats(col(group, metric))
        check(f"{label} & {f(m, 3)} & {f(s, 3)} & {f(lo, 3)} & {f(hi, 3)} & {len(group)} ({fails}) \\\\")


def table_v_vi():
    rows = load("exp2_resource")
    src = f"raw/exp2_resource.csv, first {ORIGINAL_PASS_ROWS['exp2_resource']} rows"
    cases = [("docker", "Docker"), ("docker_prometheus", "+Prometheus"), ("docker_full", "+Grafana")]
    by_case = {k: [r for r in rows if r["case"] == k] for k, _ in cases}

    def ms(case, metric, fmt):
        m, s, _, _ = stats(col(by_case[case], metric))
        return f"{f(m, fmt)} ({f(s, fmt)})"

    header("Table V - Application resource use and response characteristics (mean (std))", src)
    for key, label in cases:
        check(f"{label} & {ms(key, 'app_cpu_mean', 2)} & {ms(key, 'app_mem_mb_mean', 2)} & "
              f"{ms(key, 'p95_latency_ms', 2)} & {ms(key, 'throughput_rps', 0)} \\\\")

    header("Table VI - Monitoring stack's own resource draw (mean)", src)

    def mean(case, metric):
        return f(statistics.mean(col(by_case[case], metric)), 2)

    for container in ("cadvisor", "prometheus"):
        label = {"cadvisor": "cAdvisor", "prometheus": "Prometheus"}[container]
        check(f"{label} & {mean('docker_prometheus', container + '_cpu_mean')} & "
              f"{mean('docker_prometheus', container + '_mem_mb_mean')} & "
              f"{mean('docker_full', container + '_cpu_mean')} & "
              f"{mean('docker_full', container + '_mem_mb_mean')} \\\\")
    check(f"Grafana & --- & --- & {mean('docker_full', 'grafana_cpu_mean')} & "
          f"{mean('docker_full', 'grafana_mem_mb_mean')} \\\\")


def prose():
    rows = load("exp3_cpu_stress")
    header("Section VI.C - CPU stress detection", "raw/exp3_cpu_stress.csv, first 20 rows")
    m, s, lo, hi = stats(col(rows, "detection_seconds"))
    check(f"(MTTD) {f(m, 2)}s (std {f(s, 2)}s, min {f(lo, 2)}s, max {f(hi, 2)}s)")
    m, s, _, _ = stats(col(rows, "peak_cpu_percent"))
    check(f"{f(m, 1)}\\% (std {f(s, 1)}")
    detected = sum(r["detected"] == "True" for r in rows)
    print(f"  detected: {detected}/{len(rows)}")

    rows = load("exp4_memory_stress")
    header("Section VI.D - Memory stress / OOM", "raw/exp4_memory_stress.csv, first 20 rows")
    m, s, _, _ = stats(col(rows, "requests_before_failure"))
    check(f"mean {f(m, 2)} successful allocation requests (std {f(s, 2)})")
    m, s, _, _ = stats(col(rows, "peak_mem_mb"))
    check(f"{f(m, 2)}\\,MB (std {f(s, 2)})")
    m, s, _, _ = stats(col(rows, "time_to_oom_seconds"))
    check(f"time-to-OOM was {f(m, 2)}s (std {f(s, 2)}s)")
    oom = sum(r["oom_killed"] == "True" for r in rows)
    restarts = {r["restart_count"] for r in rows}
    print(f"  OOMKilled: {oom}/{len(rows)}, RestartCount values: {sorted(restarts)}")

    rows = load("exp5_failure_recovery")
    header("Section VI.E - Failure detection & recovery", "raw/exp5_failure_recovery.csv, first 20 rows")
    m, s, lo, hi = stats(col(rows, "detection_seconds"))
    check(f"{f(m, 2)}s (std {f(s, 2)}s, min {f(lo, 2)}s, max {f(hi, 2)}s)")
    m, s, _, _ = stats(col(rows, "recovery_seconds"))
    check(f"$\\approx${f(m, 1)}s (std {f(s, 3)}s")


if __name__ == "__main__":
    table_iii()
    table_v_vi()
    prose()
    ok = sum(results)
    colour = GREEN if ok == len(results) else RED
    print(f"\n{BOLD}{colour}{ok}/{len(results)} recomputed lines found verbatim in paper/paper.tex{RESET}")
