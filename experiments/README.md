# Reproducing the experiments

This folder is self-contained: `scripts/` runs each experiment against the
subject application defined in `../app/`, writes raw per-run measurements to
`raw/`, and `scripts/aggregate.py` computes the mean/standard deviation/
min/max summary tables in `results/` directly from those raw files. Every
number reported in `../paper/paper.tex` traces back to a row in `raw/`
through that aggregation step — nothing is entered by hand.

## What each script does

| Script | Experiment | What it measures |
|---|---|---|
| `scripts/exp1_deploy.py` | E1 — deployment time & reliability | Wall-clock time to a healthy `/health` response, across 4 configurations (manual process, Docker, Docker+GitHub Actions CI/CD, full monitored pipeline) |
| `scripts/exp2_resource.py` | E2 — resource utilization, response time, throughput, monitoring overhead | Per-container CPU%/memory (via `docker stats`), plus request latency/throughput/error rate under a fixed load, across 3 monitoring configurations |
| `scripts/exp3_cpu_stress.py` | E3 — CPU stress detection | Time for Prometheus to observe induced CPU saturation crossing a threshold |
| `scripts/exp4_memory_stress.py` | E4 — memory stress / OOM behaviour | Time-to-OOM, peak memory, and restart behaviour under a hard memory limit. `--fill` writes a non-zero byte to every allocated page; without it the retained memory is zero-filled and the kernel may reclaim it (THP shrinker), so no OOM occurs |
| `scripts/exp5_failure_recovery.py` | E5 & E6 — failure detection & recovery | Time for Prometheus to detect a killed container, and time to recover after restart. Both phases live in one script because they are two halves of the same run (kill, then restart, in sequence) — splitting them would mean re-deriving the failure state twice. |
| `scripts/loadgen.py` | — | Standalone concurrent HTTP load generator (used inside E2 and available to run independently) |
| `scripts/stats_sampler.py` | — | Standalone `docker stats` poller (used inside E2 and available to run independently) |
| `scripts/paper_tables.py` | — | Recomputes every table/prose number from `raw/` in the paper's layout and checks each line appears verbatim in `paper.tex` |
| `scripts/aggregate.py` | — | Reads every CSV in `raw/`, computes mean/std/min/max grouped by configuration, writes `results/*_summary.csv` |
| `scripts/exp6_overhead.py` | E6 — monitoring overhead vs host CPU vs throughput (in the paper; raw data in `raw/exp6_overhead*.csv`, copies of `replication/2026-10-06_1653/raw/`) | Fixed-duration load; host, per-container, load-generator and docker-proxy CPU from kernel counters over exactly the load window; randomized case order; optional CPU-pinned arm |
| `scripts/analyze_overhead.py` | — | E6 analysis: CPU breakdown, throughput contrasts, pinning (contention) test, run-level throughput-vs-CPU relationships, figures |
| `scripts/diag_timewait.py` | E6 diagnostic | Runs the per-request and keep-alive load clients in turn (3 repetitions each, app-only stack, TIME_WAIT drained before each) and samples throughput, TIME_WAIT sockets and docker-proxy CPU every second for 40 s (explains the per-request throughput collapse) |
| `scripts/e6_prose.py` | — | Recomputes every E6 number quoted in `paper.tex` from `raw/` and checks each appears verbatim (`make e6-prose`) |
| `scripts/replication_table.py` | — | Renders the original-vs-replication CSV into the LaTeX table `paper/tables/replication.tex` |
| `scripts/reproducibility_table.py` | — | Classifies every finding as reproduces / environment-dependent / not supported from the comparison CSV, raw files and E6 results; writes `paper/tables/reproducibility.tex` (`tests/test_reproducibility_table.py`) |
| `scripts/stats_prose.py` | — | Recomputes the statistical-methods numbers quoted in the paper (normality rejections, test agreement, Holm correction) and checks each appears verbatim (`make stats-prose`) |
| `scripts/diag_thp.py` | E4 diagnostic | Standalone 150 MB container probe: zero-filled vs non-zero allocation, default THP vs THP disabled for the process; records OOM kills and the kernel's underused-THP split counter (explains the zero-fill result) |
| `scripts/thp_table.py` | — | Renders `raw/diag_thp.csv` into `paper/tables/thp_diag.tex` |
| `scripts/exp7_loaded_overhead.py` | E7 — monitoring cost under background CPU load | Keep-alive throughput, Docker vs full stack, with a duty-cycle burner holding the host at 0/20/40/60% CPU; burner CPU measured from /proc |
| `scripts/analyze_loaded.py`, `scripts/e7_prose.py` | — | E7 analysis (penalty per level, difference-in-differences 60% vs 0%, pre-registered verdict) and verbatim check of E7 numbers in the paper |
| `scripts/diag_power.py` | P4 diagnostic | Keep-alive Docker-only throughput in blocks alternating the laptop power profile (switched between blocks); logs profile, governor, EPP, boost, AC, mean CPU frequency and Tctl per run; refuses to run on battery |
| `scripts/stats_lib.py` | — | Unit-tested CI / effect-size functions (`tests/test_stats_lib.py`) |
| `scripts/validate.py` | — | 95% CI, Hedges' g, Cliff's δ for every headline number; original vs replication comparison |
| `scripts/hostmetrics.py`, `scripts/runmeta.py` | — | Kernel CPU counters; host/software snapshot (kernel, power profile, background load, image digests, packages) |
| `scripts/campaign.py` | — | Runs a full replication campaign into `replication/<timestamp>/` with preconditions, snapshots and logs |

## Prerequisites

- Docker + Docker Compose (tested with Docker 29.7.2)
- Python 3.12+ (tested on 3.12 and 3.14). Every experiment script and `aggregate.py` use the standard library only; `statistical_analysis.py` needs scipy: `pip install -r experiments/requirements.txt`
- The subject app image built once: `docker compose build app` (run from the repository root)
- For E1's `docker_cicd` configuration only: the [`gh` CLI](https://cli.github.com/), authenticated, and push access to trigger the repository's GitHub Actions workflow

Beyond that, the load generator and stats sampler deliberately avoid
external tools (`hey`, `wrk`).

## Running an experiment

Each script takes `--runs` (default 20) and writes to `raw/<name>.csv` by
default (`--out` to override). Runs append to the CSV rather than overwrite
it, so re-running accumulates more data rather than discarding what's there.

```bash
# from the repository root
docker compose build app        # build the subject application image once

python3 experiments/scripts/exp1_deploy.py --configs manual docker full_pipeline --runs 20
python3 experiments/scripts/exp1_deploy.py --configs docker_cicd --runs 8   # slower — real CI runs
python3 experiments/scripts/exp2_resource.py --runs 20
python3 experiments/scripts/exp3_cpu_stress.py --runs 20
python3 experiments/scripts/exp4_memory_stress.py --runs 20
python3 experiments/scripts/exp5_failure_recovery.py --runs 20
python3 experiments/scripts/exp6_overhead.py --runs 20                      # per-request client
python3 experiments/scripts/exp6_overhead.py --keepalive --runs 20          # keep-alive client
python3 experiments/scripts/exp6_overhead.py --keepalive --runs 10 --cases docker docker_full --loadgen-procs 4
python3 experiments/scripts/diag_timewait.py

python3 experiments/scripts/aggregate.py        # regenerate results/*_summary.csv from raw/
```

Each script tears down whatever Docker containers it started before exiting,
so they can be run in any order without manual cleanup in between.

## Reproducing the paper's numbers from raw data

No Docker needed — this only reads `raw/`. From the repository root:

```bash
make reproduce
```

which runs, in order: unit tests; `aggregate.py` and a check that `results/`
is byte-identical to the committed tables; `paper_tables.py` (every table line
recomputed and found verbatim in `paper.tex`); `statistical_analysis.py`;
`validate.py` (CIs and effect sizes into `results/validation/`); the Experiment 6
analysis (`make overhead`, diffed against the committed CSVs) and the check that
every E6 number in the paper matches it (`make e6-prose`); pixel verification of
every data figure; and the LaTeX build of `paper/paper.pdf`. Collecting new data
is not part of this and does not give the same numbers (see the paper's
Limitations).
Each target also runs alone (`make tables`, `make validate`, ...).

## Repeating the experiments (replication campaign)

```bash
make image             # once
make campaign          # or: make campaign-cicd  (adds 8 real GitHub Actions runs)
make validate-campaign # original vs replication + Experiment 6 analysis
```

Output goes to `replication/<timestamp>/` (`raw/`, `meta/`, `logs/`,
`results/`, `CAMPAIGN.md`), never to `raw/`. The campaign refuses to start a
step unless Docker can start a networked container, no other containers run,
the ports are free and background CPU is under 0.5 cores — close browsers and
set a fixed power profile first; the profile is recorded in `meta/`.

| Paper | Source after running the above |
|---|---|
| Table III (deployment time) | `results/exp1_deploy_summary.csv` — `wall_seconds_*`; Docker+CI/CD row uses `elapsed_seconds_*` |
| Table V (resource use, latency, throughput) | `results/exp2_resource_summary.csv` — `app_cpu_mean_*`, `app_mem_mb_mean_*`, `p95_latency_ms_*`, `throughput_rps_*` |
| Table VI (monitoring stack draw) | same file — `cadvisor_*`, `prometheus_*`, `grafana_*` columns |
| §VI.C CPU stress MTTD | `results/exp3_cpu_stress_summary.csv` |
| §VI.D OOM behaviour | `results/exp4_memory_stress_summary.csv` |
| §VI.E failure MTTD / MTTR | `results/exp5_failure_recovery_summary.csv` |
| t-tests, Wilson CI | `statistical_analysis.py` stdout |

Std columns are population standard deviation (`statistics.pstdev`).
`aggregate.py` uses only each file's original-pass rows (`ORIGINAL_PASS_ROWS`);
`--all` includes later re-runs. Full value-by-value trace: `DATA_PROVENANCE.md`.

## Interactive demo

`../scripts/demo.sh` walks through the whole pipeline step by step (repo
identity, the running container, a live CI/CD run, Prometheus, Grafana, the
scripts, the raw data, and a fresh live run) for anyone who wants to watch
it happen rather than run each script directly.

## Layout

```
experiments/
  README.md          — this file
  log.md             — append-only log of when each experiment batch was run
  scripts/           — experiment scripts + shared helpers + analysis
  tests/             — unit tests for the statistics and CPU-accounting code
  raw/               — one CSV per experiment, one row per run (original data; never appended by campaigns)
  results/           — mean/std/min/max summaries (aggregate.py); validation/ (validate.py)
  replication/       — one directory per replication campaign
```
