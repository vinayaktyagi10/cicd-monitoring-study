# cicd-monitoring-study — working context

## The bet

Most papers evaluate CI/CD automation, containerization, or observability in
isolation. This study experimentally measures their *combined* operational
impact — deployment performance, resource utilization, and failure detection
— across three configurations (no containerization → Docker only → Docker +
GitHub Actions + Prometheus + Grafana), under normal load and under
controlled CPU/memory/failure fault injection. The contribution is the
empirical evidence (tables, graphs, ≥20 runs per config with mean/std/min/max),
not the pipeline itself — the pipeline is just the measurement apparatus.

## Constraints

- Target: conference/journal paper. No fixed CFP deadline yet — pace
  accordingly but don't let scope creep stall a submittable draft.
- Solo work, professor advising/reviewing — decisions should be defensible
  to that professor and to interview panels, not just "made to work."
- Zero infra budget: no cloud VM. CI runs on GitHub-hosted Actions runners;
  deployment, load generation, and monitoring run on the local machine
  (AMD Ryzen 7 8845HS, 8c/16t, 14GB RAM — confirmed sufficient headroom to
  run app + Prometheus + Grafana + load generator concurrently without the
  host itself becoming the bottleneck).

## Stack

- Subject application: small **FastAPI** service, hand-built, with 2-3
  endpoints designed as clean experimental levers (a cheap health route, a
  CPU-bound route, a memory-allocating route) and native `/metrics` via
  `prometheus_client` (no side-car exporter).
- CI: GitHub Actions (build, test, Docker build/push).
- Deployment: Docker / docker-compose, local host.
- Monitoring: Prometheus + Grafana, local host.
- Load generation: TBD at experiment-design time (likely `hey` or `locust`).

## Working defaults

Decision log convention and working defaults (explain-before-code, TDD for
algorithmic work, append-only DECISIONS.md, etc.) are in `~/.claude/CLAUDE.md`
— this file holds only what's specific to this project.

## Project-specific notes

- Every experiment run must be logged to `experiments/log.md` (or similar,
  append-only) as it happens — mean/std/min/max tables in the paper are
  derived from that raw log, never typed in by hand.
- Keep code comments minimal per user instruction — the paper carries the
  explanation, not inline comments.
