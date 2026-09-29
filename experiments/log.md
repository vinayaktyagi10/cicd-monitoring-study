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
