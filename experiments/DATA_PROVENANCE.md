# Data provenance

Every numerical result in `paper/paper.tex` traces to a specific raw CSV
file, produced by a specific script, aggregated or tested by a specific
second script. This document is that trace, table by table and figure by
figure. Nothing here is computed by hand — every number below can be
reproduced by running the listed script against the listed raw file.

General pipeline: `experiments/scripts/expN_*.py` (run the real experiment,
produce `experiments/raw/<name>.csv`) → `experiments/scripts/aggregate.py`
(mean/std/min/max, produce `experiments/results/<name>_summary.csv`) →
numbers copied into `paper/paper.tex` tables/prose →
`paper/figures/generate_figures.py` (renders Figs. 4-10 from the same
`results/`/`raw/` files) → `experiments/scripts/statistical_analysis.py`
(significance tests on the raw per-run data, not the summaries).

## Table III — Deployment time by configuration

| Paper value | Raw file | Script that produced the raw rows | Column in `exp1_deploy_summary.csv` |
|---|---|---|---|
| Manual: 0.592 / 0.020 / 0.577 / 0.633, n=20 | `raw/exp1_deploy.csv` (rows `config=manual`) | `scripts/exp1_deploy.py --configs manual --runs 20` | `wall_seconds_{mean,std,min,max}` |
| Docker: 1.454 / 0.107 / 1.267 / 1.581, n=20 | same file, `config=docker` | `scripts/exp1_deploy.py --configs docker --runs 20` | `wall_seconds_*` |
| Docker+CI/CD: 50.231 / 3.816 / 44.404 / 55.362, n=8 (1 fail) | same file, `config=docker_cicd` | `scripts/exp1_deploy.py --configs docker_cicd --runs 8` (real `gh workflow run` dispatch per run) | `elapsed_seconds_*` (this column, not `wall_seconds`, is the CI+deploy combined figure — see script docstring) |
| Full pipeline: 1.552 / 0.031 / 1.485 / 1.636, n=20 | same file, `config=full_pipeline` | `scripts/exp1_deploy.py --configs full_pipeline --runs 20` | `wall_seconds_*` |

Computed by: `scripts/aggregate.py` (plain `statistics.mean` /
`statistics.pstdev` / `min` / `max` over each config's rows).

## Table V — Application resource use and response characteristics

| Paper value | Raw file | Script | Column in `exp2_resource_summary.csv` |
|---|---|---|---|
| Docker: CPU 11.02(3.23), Mem 36.11(0.41), p95 5.23(1.00), Throughput 2737(206) | `raw/exp2_resource.csv`, rows 1-20 (`case=docker`) | `scripts/exp2_resource.py --cases docker docker_prometheus docker_full --runs 20` | `app_cpu_mean_{mean,std}`, `app_mem_mb_mean_{mean,std}`, `p95_latency_ms_{mean,std}`, `throughput_rps_{mean,std}` |
| +Prometheus: CPU 3.76(4.42), Mem 35.68(0.43), p95 5.34(0.80), Throughput 2641(226) | same file, rows 21-40 | same invocation | same columns, `case=docker_prometheus` |
| +Grafana: CPU 1.79(3.11), Mem 35.79(0.96), p95 5.51(0.86), Throughput 2449(285) | same file, rows 41-60 | same invocation | same columns, `case=docker_full` |

Each row of `raw/exp2_resource.csv` is itself derived from a 300-request
load test (`ThreadPoolExecutor`-based, see `scripts/exp2_resource.py:
run_load`) plus a concurrent `docker stats` sampling thread
(`scripts/exp2_resource.py: sample_stats`), both running for the same
~1-2s window per run.

**Important**: `raw/exp2_resource.csv` has since been appended to twice
more (a contaminated reproduction run, then a clean isolated re-run — see
`experiments/reproduction_run_2026-09-10.txt`). Table V and
`results/exp2_resource_summary.csv` reflect **only the first 60 rows**
(the original collection pass). Any script reading this file for paper
numbers must slice to `[:60]`, exactly as `statistical_analysis.py` does.

## Table VI — Monitoring stack's own resource draw

| Paper value | Raw file | Column |
|---|---|---|
| cAdvisor 6.13% / 47.16MB (+Prometheus case) | `raw/exp2_resource.csv` rows 21-40 | `cadvisor_cpu_mean_mean`, `cadvisor_mem_mb_mean_mean` |
| cAdvisor 6.40% / 45.39MB (+Grafana case) | rows 41-60 | same columns |
| Prometheus 0.78%/59.40MB, 0.80%/52.78MB | rows 21-40, 41-60 | `prometheus_cpu_mean_mean`, `prometheus_mem_mb_mean_mean` |
| Grafana 0.06%/60.70MB | rows 41-60 only (Grafana absent in the +Prometheus case) | `grafana_cpu_mean_mean`, `grafana_mem_mb_mean_mean` |

Same underlying rows as Table V — these are different columns of the same
`docker stats` sampling pass, not a separate experiment.

## Prose numbers — CPU stress detection (Section VI.C)

| Paper value | Raw file | Script | Column in `exp3_cpu_stress_summary.csv` |
|---|---|---|---|
| MTTD 5.65s / 3.68 / 1.51 / 18.58, 20/20 detected | `raw/exp3_cpu_stress.csv`, first 20 rows | `scripts/exp3_cpu_stress.py --runs 20` | `detection_seconds_{mean,std,min,max}` |
| Peak CPU 96.6% (std 10.0) | same rows | same script | `peak_cpu_percent_mean`, `peak_cpu_percent_std` |

`detection_seconds` for each run is the wall-clock gap between starting 8
concurrent `/cpu` stress threads and Prometheus's `app_process_cpu_percent`
gauge (a value the app computes about itself, not cAdvisor) first reading
≥60% (`scripts/exp3_cpu_stress.py: query_process_cpu_percent`, polled every
0.5s). **Note**: this file now has 60 rows (3 collection passes — see
`reproduction_run_2026-09-10.txt`); the paper's numbers are the **first 20
rows only**.

## Prose numbers — Memory stress / OOM (Section VI.D)

| Paper value | Raw file | Script | Column in `exp4_memory_stress_summary.csv` |
|---|---|---|---|
| Peak mem 135.54MB (std 0.17) | `raw/exp4_memory_stress.csv`, first 20 rows | `scripts/exp4_memory_stress.py --runs 20` | `peak_mem_mb_mean`, `peak_mem_mb_std` |
| Time-to-OOM 11.58s (std 2.23) | same rows | same script | `time_to_oom_seconds_mean`, `time_to_oom_seconds_std` |
| 5.25 requests before failure (std 1.09) | same rows | same script | `requests_before_failure_mean`, `requests_before_failure_std` |
| RestartCount=1, 20/20 OOMKilled | same rows | same script | `restart_count_mean`=1.0, `restart_count_std`=0.0 |

`oom_killed`/`restart_count` come directly from `docker inspect`'s
`State.OOMKilled` and top-level `RestartCount` fields — kernel/Docker-set,
not computed (`scripts/exp4_memory_stress.py: container_state`). This file
also now has 60 rows (3 passes); paper numbers are the **first 20 rows**.

## Prose numbers — Failure detection & recovery (Section VI.E)

| Paper value | Raw file | Script | Column in `exp5_failure_recovery_summary.csv` |
|---|---|---|---|
| MTTD 1.15s (std 0.21, min 0.82, max 2.03) | `raw/exp5_failure_recovery.csv`, first 20 rows | `scripts/exp5_failure_recovery.py --runs 20` | `detection_seconds_{mean,std,min,max}` |
| MTTR 1.994s (std 0.006) | same rows | same script | `recovery_seconds_{mean,std}` |

MTTD comes from polling Prometheus's built-in `up{job="app"}` series
(Prometheus itself sets this to 0 on scrape failure) after a real
`docker kill`; MTTR from polling `/health` + `up==1` after a real
`docker start` (`scripts/exp5_failure_recovery.py`). This file also has 60
rows (3 passes); paper numbers are the **first 20 rows**.

## Statistical tests (Section VI.B, VII, VIII)

All computed by `scripts/statistical_analysis.py`, run against the raw CSVs
directly (not the summaries):

| Paper claim | Test | Exact output |
|---|---|---|
| CI/CD reliability 95% CI [52.9%, 97.8%] | Wilson score interval, 7/8 | `wilson_ci(7, 8)` → `(0.529, 0.978)` |
| Docker vs.\ +Grafana CPU%: significant | Welch's $t$-test, `raw/exp2_resource.csv[:60]` | $t{=}8.98$, $p{<}0.0001$, $d{=}2.84$ |
| Docker vs.\ +Prometheus CPU%: significant | same | $t{=}5.78$, $p{<}0.0001$, $d{=}1.83$ |
| +Prometheus vs.\ +Grafana CPU%: NOT significant | same | $t{=}1.60$, $p{=}0.1196$, $d{=}0.50$ |
| Docker vs.\ +Grafana throughput: significant | same | $t{=}3.57$, $p{=}0.0011$, $d{=}1.13$ |
| Docker vs.\ +Prometheus throughput: NOT significant | same | $t{=}1.37$, $p{=}0.1773$, $d{=}0.43$ |
| +Prometheus vs.\ +Grafana throughput: significant | same | $t{=}2.30$, $p{=}0.0275$, $d{=}0.73$ |
| p95 latency, all three pairs: NOT significant | same | $p{=}0.71$, $0.53$, $0.36$ |
| Original vs.\ isolated CPU-stress detection: significant | `raw/exp3_cpu_stress.csv`, rows 1-20 vs.\ rows 41-60 | $t{=}3.52$, $p{=}0.0022$, $d{=}1.11$ |

Reproduce with: `.venv-figs/bin/python3 experiments/scripts/statistical_analysis.py`
(needs `scipy`, installed only in `.venv-figs/`, not the system Python).

## Figures 4-10

All rendered by `paper/figures/generate_figures.py` reading directly from
`experiments/results/*.csv` and `experiments/raw/*.csv` — no numbers are
typed into the figure script by hand. Reproduce with:
`.venv-figs/bin/python3 paper/figures/generate_figures.py`.

| Figure | Source function | Source data |
|---|---|---|
| Fig. 4 (deployment time) | `fig4_deploy_time()` | `results/exp1_deploy_summary.csv` |
| Fig. 5 (CPU utilization) | `fig5_cpu_utilization()` | `results/exp2_resource_summary.csv` |
| Fig. 6 (memory utilization) | `fig6_memory_utilization()` | `results/exp2_resource_summary.csv` |
| Fig. 7 (response latency) | `fig7_response_latency()` | `results/exp2_resource_summary.csv` |
| Fig. 8 (failure timeline) | `fig8_failure_timeline()` | `raw/exp5_failure_recovery.csv` (per-run, not summarized) |
| Fig. 9 (MTTD/MTTR comparison) | `fig9_mttd_mttr()` | `results/exp3_cpu_stress_summary.csv` + `results/exp5_failure_recovery_summary.csv` |
| Fig. 10 (monitoring overhead) | `fig10_monitoring_overhead()` | `results/exp2_resource_summary.csv` |

Figs. 1-3 are not data-driven: Fig. 1 (architecture) and Fig. 2 (GitHub
Actions workflow) are hand-built TikZ diagrams matching the real
`docker-compose.yml` and `.github/workflows/ci.yml` structure; Fig. 3 is a
live screenshot of the running Grafana dashboard (not regenerable by
script — see `experiments/reproduction_run_2026-09-10.txt` for how it was
captured).

## Reproducing everything from scratch

```bash
docker compose build app
python3 experiments/scripts/exp1_deploy.py --configs manual docker full_pipeline --runs 20
python3 experiments/scripts/exp1_deploy.py --configs docker_cicd --runs 8
python3 experiments/scripts/exp2_resource.py --runs 20
python3 experiments/scripts/exp3_cpu_stress.py --runs 20
python3 experiments/scripts/exp4_memory_stress.py --runs 20
python3 experiments/scripts/exp5_failure_recovery.py --runs 20
python3 experiments/scripts/aggregate.py
.venv-figs/bin/python3 experiments/scripts/statistical_analysis.py
.venv-figs/bin/python3 paper/figures/generate_figures.py
```

Each `expN` script appends to its raw CSV rather than overwriting it, so
running this against an existing `experiments/raw/` directory adds a new
collection pass rather than replacing the one the paper's numbers came
from — see the note on Table V and the reproduction writeup for why that
matters when re-deriving numbers.
