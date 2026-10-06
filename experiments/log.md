# Experiment log

Append-only, raw. One entry per run (or batch of runs) as they happen — the
mean/std/min/max tables in the paper are computed from this, never typed by
hand.

## 2026-09-09 — Experiment 1: deployment time & reliability
Configs: manual (20), docker (20), full_pipeline (20), docker_cicd (8, real
GitHub Actions workflow_dispatch runs — capped below 20 because each run is
~45-65s of real CI wall time and consumes Actions minutes; documented
deviation from the ≥20 default).
Raw data: experiments/raw/exp1_deploy.csv (`wall_seconds` is the deployment-
time metric; `elapsed_seconds` is health-poll-only, diagnostic).
Notes: docker_cicd run 1/8 failed (wall_seconds=0.95s) — a transient race in
`gh run list` returning before the new dispatch registered, not a pipeline
failure. Kept as a genuine data point for the reliability/failure-count RQ4
table rather than discarded. GHCR pull for docker_cicd was not authenticated
(gh CLI token lacks read:packages scope, needs interactive re-auth) — deploy
step for that config runs the locally-built image from the same commit/
Dockerfile CI just built, standing in for "pull the CI-built artifact"
without the registry auth dependency. Script: scripts/exp1_deploy.py.

## 2026-09-09 — Experiment 2: resource utilization, response time, throughput,
monitoring overhead across the 3 baseline cases
Configs: docker (20), docker_prometheus (20), docker_full (20). Fixed load:
300 concurrent /health requests, concurrency=10, per run.
Raw data: experiments/raw/exp2_resource.csv — per-run throughput, mean/p95
latency, error rate, and per-container mean CPU%/mem MB (app, cadvisor,
prometheus, grafana as applicable) sampled via `docker stats` every 1s during
the load window. Script: scripts/exp2_resource.py.
Notes: zero errors across all 60 runs. Container CPU%/mem columns give the
monitoring-stack containers' own resource draw directly (Table 5 overhead
source), separate from the app container's own CPU/mem (Table 3 source).

## 2026-09-09 — Experiment 3: CPU stress detection time via Prometheus (20 runs)
8 concurrent threads flood /cpu (8M-iteration pure-Python loop each); detect
via app_process_cpu_percent (self-reported gauge, sampled every 1s from
time.process_time() deltas) crossing 60%. Raw: experiments/raw/exp3_cpu_stress.csv.
Notes: switched away from a /health-latency detection signal after finding
it barely moves under CPU load — CPython's GIL round-robins fairly at ~5ms
intervals — see DECISIONS.md 2026-09-09 entry. All 20/20 runs detected;
mean 5.65s, stdev 3.68s, min 1.51s, max 18.58s (bounded below by the 2s
Prometheus scrape_interval, tail driven by GIL scheduling noise across runs).
Also added app_process_cpu_percent / app_process_memory_bytes gauges to
app/main.py and rebuilt the local image before this run.

## 2026-09-09 — Experiment 4: memory stress / OOM behaviour (20 runs)
`docker run` (not compose) with --memory 150m --memory-swap 150m
--restart on-failure:1, repeated /memory?mb=20&hold=true calls until the
kernel OOM-kills the container; ground truth via `docker inspect`
(OOMKilled, RestartCount), captured at the moment of observation since
Docker resets State.OOMKilled once --restart brings the container back up.
Raw: experiments/raw/exp4_memory_stress.csv.
Notes: 20/20 OOM-killed and auto-restarted (RestartCount=1, except run 18
which needed a second cycle). Consistent ~135MB peak (limit 150MB) after 5
allocations of 20MB each; time_to_oom ~11.07s dominated by the fixed
per-iteration curl+inspect+stats overhead in the polling loop, not by the
kernel's actual OOM response time.

## 2026-09-09 — Experiments 5 & 6: application failure detection & recovery (20 runs)
Single stack up (app+cadvisor+prometheus). Per run: `docker kill` the app
container, poll Prometheus `up{job="app"}` until 0 (detection), `docker
start` it, poll /health + up==1 until both recover (recovery).
Raw: experiments/raw/exp5_failure_recovery.csv.
Notes: 20/20 detected and recovered. Detection: mean ~1.1s (floor set by the
2s scrape_interval combined with 0.3s poll granularity plus Docker's own
kill signal latency). Recovery: consistently ~2.0s, i.e. essentially
uvicorn's own startup time inside the container — recovery time here is
dominated by app boot, not by the monitoring stack.

Entry shape:

```
## YYYY-MM-DD HH:MM — <experiment name> — run <n>/<total>
Config: <Manual | Docker | Docker+CI/CD | Full pipeline>
Command: <exact command run>
Raw output / metrics: <pasted numbers or path to raw file>
Notes: <anything anomalous>
```

## 2026-09-29 — Correction to the 2026-09-09 Experiment 4 entry
The Experiment 4 entry above says run 18 "needed a second cycle" in the
context of RestartCount. The raw row shows RestartCount=1 for run 18 like
every other run; what differs is requests_before_failure=10 and
time_to_oom_seconds=21.32 (vs 5 and ~11.07s for the other 19). That single
run is why the reported time-to-OOM mean is 11.58s (std 2.23) rather than
~11.07s. Raw data unchanged; this entry only corrects the prose.

## 2026-09-29 — statistical_analysis.py: isolated-rerun slice fixed
The original-vs-isolated CPU-stress comparison sliced `exp3[-20:]` (last 20
rows) instead of rows 41-60, so it drifted every time a demo sample was
appended (gave t=3.40 at the 62-row committed state, t=3.49 at 64 rows).
Pinned to `exp3[40:60]`; output is now t=3.52, p=0.0022, d=1.11, matching
the paper and DATA_PROVENANCE.md regardless of later appends.

## 2026-09-29 — Environment check after host reinstall: Experiment 5 (10 runs)
Host now CachyOS, kernel 7.2.6, Docker 29.8.1, Python 3.14.7 (paper data
was collected on Arch/Omarchy, kernel 7.1.9, Docker 29.7.2).
Command: `python3 experiments/scripts/exp5_failure_recovery.py --runs 2`,
then `--runs 8`, both with `--out` to a scratch file.
Raw: experiments/env_check_2026-09-29/exp5_failure_recovery.csv (kept out of
raw/ so it never enters the paper's aggregation).
Notes: detection mean 3.08s (std 0.24, min 2.63, max 3.60) vs the paper's
1.15s (max 2.03); recovery 2.01s (std 0.115), unchanged. Diagnostic: after
`docker kill` of the app, `wget http://app:8000/health` from inside the
Prometheus container took 7.95s to fail instead of failing immediately, so
each failed scrape now ends at Prometheus's 2s scrape timeout rather than
instantly — consistent with the ~2s shift. Likely cause is name resolution
of the removed container on the new host (not yet confirmed). MTTD for a
killed container is therefore sensitive to how the failure surfaces to the
scraper, not only to scrape_interval.

## 2026-10-06 — Validation audit of the existing data (no new runs)
Command: `make reproduce` (tests, aggregate, paper_tables, statistical_analysis, validate, verify-figures, paper build).
Raw: unchanged; outputs in experiments/results/validation/.
Notes:
- Every table/prose number (17/17) and every t-test reproduces from raw/.
- Fig. 8 as published plotted 40 rows (original + 2026-09-10 reproduction) as one series; generate_figures.py now slices to the original 20 rows; figure and paper.pdf regenerated. Figs 4-7, 9, 10 reproduce pixel-identically.
- exp2 app CPU% is bimodal: runs reading <1% are 0/20 (Docker), 12/20 (+Prometheus), 16/20 (+Grafana); non-idle runs read ~8-11% in every case. Load window per run is ~0.11s. The "app CPU falls with monitoring" result is therefore mostly a sampling artifact -- see DECISIONS.md and Experiment 6.
- exp2 run_load counts failed requests in throughput_rps; original 60 rows unaffected (error_rate 0), the 2026-09-10 reproduction rows with error_rate 0.54-1.0 are not valid throughput values.
- New data could not be collected: host kernel 7.2.6 running with only 7.2.9 modules installed (package upgraded, no reboot) -> veth unavailable -> Docker cannot start networked containers. Also platform_profile=low-power and ~3-4 cores of background browser CPU at the time.
- 10 uncommitted rows in raw/*.csv (2 per file, after each file's original pass) are live-demo samples from scripts/demo.sh; excluded from all paper numbers by ORIGINAL_PASS_ROWS. Left in place, not committed.

## 2026-10-06T16:53:48+05:30 - Replication campaign 2026-10-06_1653, step e1
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp1_deploy.py --configs manual docker full_pipeline --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp1_deploy.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e1.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e1_before.json
Notes: exit code 0, 2.0 min, background CPU 0.05 cores at start (written automatically by campaign.py).

## 2026-10-06T16:57:02+05:30 - Replication campaign 2026-10-06_1653, step e2
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp2_resource.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp2_resource.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e2.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e2_before.json
Notes: exit code 0, 3.0 min, background CPU 0.22 cores at start (written automatically by campaign.py).

## 2026-10-06T17:01:14+05:30 - Replication campaign 2026-10-06_1653, step e3
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp3_cpu_stress.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp3_cpu_stress.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e3.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e3_before.json
Notes: exit code 0, 2.7 min, background CPU 0.05 cores at start (written automatically by campaign.py).

## 2026-10-06T17:05:08+05:30 - Replication campaign 2026-10-06_1653, step e4
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp4_memory_stress.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp4_memory_stress.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e4.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e4_before.json
Notes: exit code 0, 10.8 min, background CPU 0.05 cores at start (written automatically by campaign.py).

## 2026-10-06T17:17:07+05:30 - Replication campaign 2026-10-06_1653, step e5
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp5_failure_recovery.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp5_failure_recovery.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e5.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e5_before.json
Notes: exit code 0, 2.8 min, background CPU 0.05 cores at start (written automatically by campaign.py).

## 2026-10-06T17:21:09+05:30 - Replication campaign 2026-10-06_1653, step e6
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp6_overhead.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp6_overhead.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e6.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e6_before.json
Notes: exit code 0, 73.3 min, background CPU 0.05 cores at start (written automatically by campaign.py).

## 2026-10-06T18:35:41+05:30 - Replication campaign 2026-10-06_1653, step e6x4
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp6_overhead.py --runs 10 --cases docker docker_full --loadgen-procs 4 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp6_overhead_loadgen4.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e6x4.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e6x4_before.json
Notes: exit code 0, 24.4 min, background CPU 0.05 cores at start (written automatically by campaign.py).

## 2026-10-06 — Replication campaign 2026-10-06_1653 and E4 zero-page finding
Command: `make campaign` (e1-e5, e6, e6x4), then `exp4_memory_stress.py --fill --runs 20 --out experiments/replication/2026-10-06_1653/raw/exp4_memory_stress_fill.csv`.
Raw: experiments/replication/2026-10-06_1653/ (original raw/ untouched).
Notes:
- Host: kernel 7.2.9, platform_profile=performance, background CPU <= 0.22 cores before each step.
- Most absolute numbers differ from the original run (deploy -12..-29%, throughput +48%, CPU-stress MTTD 2.41s vs 5.65s, failure MTTD 3.14s vs 1.15s); MTTR, peak CPU under stress, Prometheus/Grafana CPU consistent.
- E4 as originally written: 0/20 OOM-killed, 16 requests succeeded, peak ~139MB. Cause: zero-filled ballast is reclaimed by the kernel's THP underused-page shrinker (shrink_underused=1); memory.events showed max=1, oom_kill=0. A script allocating zero bytearrays was OOM-killed only with THP disabled via prctl.
- E4 with --fill (non-zero byte per page): 20/20 OOM-killed, 5.0 requests, peak 136.4MB, time-to-OOM 11.06s -- matches the original.
- Not established: whether the original 2026-09 run differed in kernel/THP settings. shrink_underused could not be toggled directly (needs root).
- E6: monitoring containers ~0.03 cores; no throughput contrast vs Docker-only excludes zero; pinning test inconclusive; throughput varied ~3x run to run and tracked host load (r=-0.98).

## 2026-10-06T23:55:45+05:30 - Replication campaign 2026-10-06_1653, step e1cicd
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp1_deploy.py --configs docker_cicd --runs 8 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp1_deploy.csv`
Raw: experiments/replication/2026-10-06_1653/raw/ ; log: experiments/replication/2026-10-06_1653/logs/e1cicd.log ; host snapshot: experiments/replication/2026-10-06_1653/meta/e1cicd_before.json
Notes: exit code 0, 8.4 min, background CPU 0.18 cores at start (written automatically by campaign.py).
Note: the first e1cicd attempts at 23:47 were refused by the background-CPU precondition (0.79-0.80 cores > 0.5, Zen browser) and recorded as NOT RUN in CAMPAIGN.md. A second attempt at --max-busy-cores 1.0 was stopped after a few GitHub runs, before any row was written, and its partial work discarded. The reported result is the run above, started after closing the browser, under the default 0.5-core limit. Result: 8/8 successful, mean 48.6s (original 50.2s, CONSISTENT).

## 2026-10-07 — Provenance correction: the replication was on a reinstalled OS
/var/log/pacman.log starts with a Calamares install on 2026-09-23, after the original runs (2026-09-09/10). Original host: Arch/Omarchy kernel 7.1.9-arch1-2, Docker 29.7.2 (paper Table II). Replication host: CachyOS kernel 7.2.9, Docker 29.8.2, THP=always. The paper now calls it a same-hardware, reinstalled-OS replication, not a same-host one. The original host's THP setting was not recorded and that install no longer exists.
Also: scripts/demo_tables.sh wrote its live-demo rows into experiments/raw/; it now writes to a temp dir. The 10 leftover demo rows were removed from raw/ (backup patch kept outside the repo); no paper number changed (paper_tables.py 17/17).
