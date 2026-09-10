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
| `scripts/exp4_memory_stress.py` | E4 — memory stress / OOM behaviour | Time-to-OOM, peak memory, and restart behaviour under a hard memory limit |
| `scripts/exp5_failure_recovery.py` | E5 & E6 — failure detection & recovery | Time for Prometheus to detect a killed container, and time to recover after restart. Both phases live in one script because they are two halves of the same run (kill, then restart, in sequence) — splitting them would mean re-deriving the failure state twice. |
| `scripts/loadgen.py` | — | Standalone concurrent HTTP load generator (used inside E2 and available to run independently) |
| `scripts/stats_sampler.py` | — | Standalone `docker stats` poller (used inside E2 and available to run independently) |
| `scripts/aggregate.py` | — | Reads every CSV in `raw/`, computes mean/std/min/max grouped by configuration, writes `results/*_summary.csv` |

## Prerequisites

- Docker + Docker Compose (tested with Docker 29.7.2)
- Python 3.12+ (standard library only for every script except the app itself)
- The subject app image built once: `docker compose build app` (run from the repository root)
- For E1's `docker_cicd` configuration only: the [`gh` CLI](https://cli.github.com/), authenticated, and push access to trigger the repository's GitHub Actions workflow

No other dependencies — the load generator and stats sampler deliberately avoid
external tools (`hey`, `wrk`) so there is nothing to install beyond Docker and
Python.

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

python3 experiments/scripts/aggregate.py        # regenerate results/*_summary.csv from raw/
```

Each script tears down whatever Docker containers it started before exiting,
so they can be run in any order without manual cleanup in between.

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
  scripts/           — the six experiment scripts + shared helpers
  raw/               — one CSV per experiment, one row per run
  results/           — mean/std/min/max summaries, computed from raw/ by aggregate.py
```
