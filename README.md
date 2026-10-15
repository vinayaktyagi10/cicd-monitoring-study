# Four Pitfalls in Measuring Container and Observability Overhead

Data, scripts and paper for *Four Pitfalls in Measuring Container and Observability
Overhead: A Replicated Case Study* (Vinayak Tyagi, Manipal University Jaipur).

We measured a small pipeline (a FastAPI service, Docker, GitHub Actions, Prometheus and
Grafana) against uncontainerized and unmonitored baselines, then repeated the study on the
same hardware after reinstalling the operating system. The paper reports which findings
survived and four measurement pitfalls that explain the ones that did not:

- **P1. Zero pages are not memory pressure.** A zero-filled memory-stress test stopped
  causing OOM kills on the replication kernel because the transparent-huge-page shrinker
  reclaimed the zeroed pages.
- **P2. The load client measures the socket layer.** A client that opens a new connection
  per request exhausted ephemeral ports, so throughput tracked `docker-proxy`, not the
  application.
- **P3. The sampling window outlasts the load.** `docker stats` samples longer than a
  0.11 s load produced an apparent CPU-contention effect that kernel counters did not
  confirm.
- **P4. Absolute numbers do not travel.** Most values moved by 12–173% across the
  reinstall.

The paper is [`paper/paper.pdf`](paper/paper.pdf).

## Reproduce every table, statistic and figure

No Docker is needed. This rebuilds everything in the paper from the committed raw data:

```bash
make reproduce
```

Requirements: Python 3.12 or later, `pdftoppm` (poppler) and a TeX Live installation
with `latexmk`. The first run creates `.venv/` and installs the pinned packages from
`experiments/requirements.txt` and `app/requirements.txt`. After that it takes about a
minute.

`make reproduce` fails if anything does not match. It runs:

| Step | What it checks |
|---|---|
| `test` | Unit tests for the statistics library, the analysis scripts and the app |
| `tables` | Recomputes the summary tables from `experiments/raw/` and checks every table line appears verbatim in `paper/paper.tex` |
| `overhead`, `e6-prose`, `e7-prose` | Recomputes the Experiment 6 and 7 analyses and checks every number the paper quotes |
| `stats`, `validate` | Confidence intervals, effect sizes and tests for every headline number |
| `replication-check` | Rebuilds the original-versus-replication tables and checks they match the committed ones |
| `verify-figures` | Re-renders every data figure and compares it pixel for pixel with the committed PDF |
| `paper` | Builds `paper/paper.pdf` |

## What is not reproducible from this repository

- **Collecting new data reproduces the procedure, not the numbers.** The replication shows
  that absolute values change with the software environment (P4).
- **The Grafana screenshots (Fig. 3) cannot be reproduced pixel for pixel.** They capture a
  live dashboard. The Prometheus series behind them are saved in
  `experiments/raw/grafana_panels.json`.
- **The original host no longer exists.** Its runs cannot be re-executed under their
  original conditions (kernel, THP setting).

## Repository layout

| Path | Contents |
|---|---|
| `app/` | The FastAPI service under test, with `/health`, CPU-bound and memory-allocating endpoints and native `/metrics` |
| `docker-compose.yml`, `monitoring/` | The stack: app, cAdvisor, Prometheus and Grafana, with the provisioned dashboard |
| `.github/workflows/ci.yml` | The CI/CD workflow measured in Experiment 1 |
| `experiments/raw/` | Raw per-run CSVs for every experiment and diagnostic |
| `experiments/replication/2026-10-06_1653/` | The replication campaign: raw data, host snapshots before and after each experiment, logs |
| `experiments/results/` | Summary and analysis CSVs derived from the raw data |
| `experiments/scripts/` | Experiment, analysis and check scripts ([`experiments/README.md`](experiments/README.md) describes each one) |
| `experiments/log.md` | Append-only log of every experiment run |
| `paper/` | LaTeX source, generated tables, figures and the figure scripts |

## Collecting new data

This needs Docker, Docker Compose and the host conditions described in the paper.

```bash
make image          # build the app image
make campaign       # all experiments except CI/CD, into experiments/replication/<timestamp>/ (~3 h)
make campaign-cicd  # the same plus 8 real GitHub Actions runs (needs an authenticated gh CLI)
```

`campaign.py` checks its preconditions before starting. It refuses to run on battery
power or when the host is busy. It records the kernel, Docker version, power profile and
background load before and after each experiment.

## License

- **Code** (`app/`, `experiments/scripts/`, `experiments/tests/`, `paper/figures/*.py`,
  `scripts/`, build and configuration files): MIT, see [`LICENSE`](LICENSE).
- **Data and paper** (`experiments/raw/`, `experiments/replication/`,
  `experiments/results/`, `experiments/log.md`, and everything else under `paper/`):
  CC BY 4.0, see [`LICENSE-DATA`](LICENSE-DATA).
