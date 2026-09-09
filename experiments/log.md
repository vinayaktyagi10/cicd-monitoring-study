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
