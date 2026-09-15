#!/usr/bin/env bash
# Table-by-table live demonstration: for every numeric table in the paper,
# (1) show the raw CSV it comes from, (2) recompute it live with
# aggregate.py, then (3) run a small fresh sample of the same experiment so
# a new, today-dated row appears on screen. Companion to demo.sh, which
# covers the pipeline itself (Docker/CI/CD/Prometheus/Grafana) rather than
# the tables.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BOLD=$(tput bold 2>/dev/null || echo "")
DIM=$(tput dim 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")
YELLOW=$(tput setaf 3 2>/dev/null || echo "")
RESET=$(tput sgr0 2>/dev/null || echo "")

STEP_NUM=0

pause() {
    echo
    read -rp "${DIM}Press Enter to continue...${RESET}"
}

step() {
    STEP_NUM=$((STEP_NUM + 1))
    clear
    echo "${BOLD}${GREEN}=== Step ${STEP_NUM}: $1 ===${RESET}"
    echo "${DIM}$2${RESET}"
    echo
}

run() {
    echo "${YELLOW}\$ $*${RESET}"
    eval "$@"
}

# ---------------------------------------------------------------------------

step "Prerequisite: build the app image" "Only needs to happen once. Skip if you already ran this today."
run "docker compose build app"
pause

step "The raw data behind every table" "Row counts confirm real, repeated runs -- not single-shot numbers."
run "wc -l experiments/raw/*.csv"
pause

step "Recompute every table from the raw CSVs, live" "This is the exact command that produced Tables III-VI. Watch the output match the paper."
run "python3 experiments/scripts/aggregate.py"
echo
echo "${DIM}Now open experiments/results/exp1_deploy_summary.csv (or paper.pdf page 5) --"
echo "the numbers just printed above should match Table III/IV/V exactly.${RESET}"
pause

step "Table III -- deployment time: a fresh live sample" "2 fresh runs of the Docker config. A new row lands with today's timestamp."
run "python3 experiments/scripts/exp1_deploy.py --configs docker --runs 2"
run "tail -2 experiments/raw/exp1_deploy.csv"
pause

step "Tables V & VI -- resource use, throughput, monitoring overhead" "2 fresh runs, fewer requests per run to keep this quick live."
run "python3 experiments/scripts/exp2_resource.py --cases docker --runs 2 --requests 100"
run "tail -2 experiments/raw/exp2_resource.csv"
pause

step "CPU-stress detection (MTTD)" "2 fresh runs -- watch the detection_seconds column land."
run "python3 experiments/scripts/exp3_cpu_stress.py --runs 2"
run "tail -2 experiments/raw/exp3_cpu_stress.csv"
pause

step "Memory-stress / OOM" "2 fresh runs -- a real kernel OOM-kill each time, confirmed via docker inspect."
run "python3 experiments/scripts/exp4_memory_stress.py --runs 2"
run "tail -2 experiments/raw/exp4_memory_stress.csv"
pause

step "Failure detection & recovery (MTTD/MTTR)" "2 fresh runs -- a real docker kill, then a real docker start."
run "python3 experiments/scripts/exp5_failure_recovery.py --runs 2"
run "tail -2 experiments/raw/exp5_failure_recovery.csv"
pause

step "Statistical significance, live" "The same t-tests behind the paper's significance claims, run fresh against the original 20-run data."
run ".venv-figs/bin/python3 experiments/scripts/statistical_analysis.py"
pause

step "Anything not covered above" "Full number -> raw file -> script -> method map, for any value someone asks about that wasn't demonstrated live."
run "head -40 experiments/DATA_PROVENANCE.md"
echo
echo "${DIM}Full file: experiments/DATA_PROVENANCE.md${RESET}"

echo
echo "${BOLD}${GREEN}Table walkthrough complete.${RESET}"
echo "${DIM}Note: results/*_summary.csv still reflects only the original 20-run pass --"
echo "the fresh samples just added were NOT re-aggregated into it on purpose,"
echo "so the paper's reported numbers are untouched by this demo.${RESET}"
