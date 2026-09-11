#!/usr/bin/env python3
"""Generates Figures 4-7, 9, 10 directly from experiments/results/*.csv and
experiments/raw/*.csv — no hand-entered numbers. Run with:
    .venv-figs/bin/python3 paper/figures/generate_figures.py
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
RESULTS = os.path.join(ROOT, "experiments", "results")
RAW = os.path.join(ROOT, "experiments", "raw")

plt.rcParams.update({
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})

BAR_COLOR = "#4C72B0"
BAR_COLOR2 = "#DD8452"
BAR_COLOR3 = "#55A868"


def load_summary(name):
    path = os.path.join(RESULTS, f"{name}_summary.csv")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_raw(name):
    path = os.path.join(RAW, f"{name}.csv")
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def savefig(fig, name):
    out = os.path.join(HERE, f"{name}.pdf")
    fig.savefig(out, bbox_inches="tight")
    print(f"wrote {out}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Figure 4 — CI/CD execution / deployment time comparison
# ---------------------------------------------------------------------------
def fig4_deploy_time():
    rows = {r["config"]: r for r in load_summary("exp1_deploy")}
    order = ["manual", "docker", "full_pipeline", "docker_cicd"]
    labels = ["Manual", "Docker", "Full\npipeline", "Docker\n+CI/CD"]
    means, stds = [], []
    for cfg in order:
        r = rows[cfg]
        if cfg == "docker_cicd":
            means.append(float(r["elapsed_seconds_mean"]))
            stds.append(float(r["elapsed_seconds_std"]))
        else:
            means.append(float(r["wall_seconds_mean"]))
            stds.append(float(r["wall_seconds_std"]))

    fig, ax = plt.subplots(figsize=(4.5, 3))
    x = range(len(order))
    ax.bar(x, means, yerr=stds, capsize=4, color=BAR_COLOR)
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Deployment time (s, log scale)")
    for i, m in enumerate(means):
        ax.annotate(f"{m:.2f}s", (i, m), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=8)
    savefig(fig, "fig4_deploy_time")


# ---------------------------------------------------------------------------
# Figure 5 — CPU utilization across the 3 monitoring cases
# ---------------------------------------------------------------------------
def fig5_cpu_utilization():
    rows = {r["config"]: r for r in load_summary("exp2_resource")}
    order = ["docker", "docker_prometheus", "docker_full"]
    labels = ["Docker", "Docker\n+Prometheus", "Docker+Prometheus\n+Grafana"]
    means = [float(rows[c]["app_cpu_mean_mean"]) for c in order]
    stds = [float(rows[c]["app_cpu_mean_std"]) for c in order]

    fig, ax = plt.subplots(figsize=(4.5, 3))
    x = range(len(order))
    ax.bar(x, means, yerr=stds, capsize=4, color=BAR_COLOR2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Application container CPU (%)")
    for i, m in enumerate(means):
        ax.annotate(f"{m:.1f}%", (i, m), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=8)
    savefig(fig, "fig5_cpu_utilization")


# ---------------------------------------------------------------------------
# Figure 6 — Memory utilization across the 3 monitoring cases
# ---------------------------------------------------------------------------
def fig6_memory_utilization():
    rows = {r["config"]: r for r in load_summary("exp2_resource")}
    order = ["docker", "docker_prometheus", "docker_full"]
    labels = ["Docker", "Docker\n+Prometheus", "Docker+Prometheus\n+Grafana"]
    means = [float(rows[c]["app_mem_mb_mean_mean"]) for c in order]
    stds = [float(rows[c]["app_mem_mb_mean_std"]) for c in order]

    fig, ax = plt.subplots(figsize=(4.5, 3))
    x = range(len(order))
    ax.bar(x, means, yerr=stds, capsize=4, color=BAR_COLOR3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Application container memory (MB)")
    ax.set_ylim(30, 40)
    for i, m in enumerate(means):
        ax.annotate(f"{m:.1f}MB", (i, m), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=8)
    savefig(fig, "fig6_memory_utilization")


# ---------------------------------------------------------------------------
# Figure 7 — Response latency (mean vs p95) across the 3 cases
# ---------------------------------------------------------------------------
def fig7_response_latency():
    rows = {r["config"]: r for r in load_summary("exp2_resource")}
    order = ["docker", "docker_prometheus", "docker_full"]
    labels = ["Docker", "Docker\n+Prometheus", "Docker+Prometheus\n+Grafana"]
    mean_lat = [float(rows[c]["mean_latency_ms_mean"]) for c in order]
    p95_lat = [float(rows[c]["p95_latency_ms_mean"]) for c in order]

    fig, ax = plt.subplots(figsize=(5, 3))
    x = list(range(len(order)))
    width = 0.35
    ax.bar([i - width / 2 for i in x], mean_lat, width, label="Mean latency", color=BAR_COLOR)
    ax.bar([i + width / 2 for i in x], p95_lat, width, label="p95 latency", color=BAR_COLOR2)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Latency (ms)")
    ax.legend(frameon=False, fontsize=8)
    savefig(fig, "fig7_response_latency")


# ---------------------------------------------------------------------------
# Figure 8 — Failure detection timeline (per-run, across all 20 trials)
# ---------------------------------------------------------------------------
def fig8_failure_timeline():
    rows = load_raw("exp5_failure_recovery")
    runs = [int(r["run"]) for r in rows]
    detection = [float(r["detection_seconds"]) for r in rows]
    recovery = [float(r["recovery_seconds"]) for r in rows]

    fig, ax = plt.subplots(figsize=(5.5, 3))
    ax.plot(runs, detection, "o-", color=BAR_COLOR, label="MTTD (detection)")
    ax.plot(runs, recovery, "s-", color=BAR_COLOR2, label="MTTR (recovery)")
    ax.set_xlabel("Run number (1-20)")
    ax.set_ylabel("Time (s)")
    ax.set_xticks(range(1, 21, 2))
    ax.legend(frameon=False, fontsize=8)
    savefig(fig, "fig8_failure_timeline")


# ---------------------------------------------------------------------------
# Figure 9 — MTTD/MTTR comparison
# ---------------------------------------------------------------------------
def fig9_mttd_mttr():
    exp3 = load_summary("exp3_cpu_stress")[0]
    exp5 = load_summary("exp5_failure_recovery")[0]

    labels = ["MTTD\n(CPU stress)", "MTTD\n(container failure)", "MTTR\n(recovery)"]
    means = [
        float(exp3["detection_seconds_mean"]),
        float(exp5["detection_seconds_mean"]),
        float(exp5["recovery_seconds_mean"]),
    ]
    stds = [
        float(exp3["detection_seconds_std"]),
        float(exp5["detection_seconds_std"]),
        float(exp5["recovery_seconds_std"]),
    ]

    fig, ax = plt.subplots(figsize=(4.5, 3))
    x = range(len(labels))
    colors = [BAR_COLOR, BAR_COLOR2, BAR_COLOR3]
    ax.bar(x, means, yerr=stds, capsize=4, color=colors)
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Time (s)")
    for i, m in enumerate(means):
        ax.annotate(f"{m:.2f}s", (i, m), textcoords="offset points",
                    xytext=(0, 6), ha="center", fontsize=8)
    savefig(fig, "fig9_mttd_mttr")


# ---------------------------------------------------------------------------
# Figure 10 — Monitoring overhead (container CPU% in the two monitored cases)
# ---------------------------------------------------------------------------
def fig10_monitoring_overhead():
    rows = {r["config"]: r for r in load_summary("exp2_resource")}
    dp = rows["docker_prometheus"]
    df = rows["docker_full"]

    containers = ["cAdvisor", "Prometheus", "Grafana"]
    prometheus_case = [
        float(dp["cadvisor_cpu_mean_mean"]),
        float(dp["prometheus_cpu_mean_mean"]),
        0.0,  # Grafana not present in this case
    ]
    full_case = [
        float(df["cadvisor_cpu_mean_mean"]),
        float(df["prometheus_cpu_mean_mean"]),
        float(df["grafana_cpu_mean_mean"]),
    ]

    fig, ax = plt.subplots(figsize=(5, 3))
    x = list(range(len(containers)))
    width = 0.35
    ax.bar([i - width / 2 for i in x], prometheus_case, width,
           label="Docker+Prometheus case", color=BAR_COLOR)
    ax.bar([i + width / 2 for i in x], full_case, width,
           label="Docker+Prometheus+Grafana case", color=BAR_COLOR2)
    ax.set_xticks(x)
    ax.set_xticklabels(containers)
    ax.set_ylabel("Container CPU (%)")
    ax.legend(frameon=False, fontsize=8)
    savefig(fig, "fig10_monitoring_overhead")


if __name__ == "__main__":
    fig4_deploy_time()
    fig5_cpu_utilization()
    fig6_memory_utilization()
    fig7_response_latency()
    fig8_failure_timeline()
    fig9_mttd_mttr()
    fig10_monitoring_overhead()
