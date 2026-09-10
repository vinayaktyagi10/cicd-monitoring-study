#!/usr/bin/env bash
# Guided, step-by-step demo of the CI/CD monitoring study.
# Each step prints what it's about to do and why, runs it, then waits for
# Enter before moving on. Run from anywhere; it cd's to the repo root itself.

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

step "Repo identity" "Prove this is a real, pushed repository with real history — not something assembled in one sitting."
run "git remote -v"
run "git log --oneline"
run 'git log -1 --format="Last commit: %ai"'
pause

step "The actual machine" "Confirms the hardware matches Table II in the paper exactly."
run "lscpu | grep -E 'Model name|CPU\(s\):|Thread|Core'"
run "free -h"
run "docker --version"
run "docker compose version"
pause

step "App running in Docker" "Bring up the subject application as a real container and hit its real HTTP endpoints."
run "docker compose up -d app"
sleep 2
run "docker compose ps"
run "curl -s localhost:8000/health"
echo
run "curl -s localhost:8000/metrics | grep app_ | head -10"
pause

step "CI/CD in progress (real GitHub Actions)" "Trigger a real workflow run on GitHub's servers and watch it execute live. Open https://github.com/vinayaktyagi10/cicd-monitoring-study/actions in a browser now to watch it in the UI at the same time."
run "gh workflow run ci.yml --ref master"
echo "Waiting for the run to register..."
sleep 6
RUN_ID=$(gh run list --workflow=ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')
echo "${YELLOW}\$ gh run watch $RUN_ID --exit-status${RESET}"
gh run watch "$RUN_ID" --exit-status
pause

step "Prometheus collecting real metrics" "Prometheus's own view of what it's scraping, and a live query against real data."
run "docker compose --profile prometheus up -d"
sleep 5
run "curl -s localhost:9090/api/v1/targets | python3 -m json.tool | grep -E 'job|health'"
echo
echo "${DIM}Open http://localhost:9090/targets in a browser — both targets should read UP.${RESET}"
pause

step "Grafana with real data" "The dashboard is auto-provisioned — no manual setup. Generate visible load so a panel moves on screen."
run "docker compose --profile full up -d"
sleep 5
echo "${DIM}Open http://localhost:3000 -> Dashboards -> 'CI/CD Monitoring Study — App Dashboard'.${RESET}"
pause
echo "Generating live traffic — watch the request-rate panel move..."
run "for i in \$(seq 1 60); do curl -s localhost:8000/health > /dev/null; done"
echo "${GREEN}Done — check the dashboard now.${RESET}"
pause

step "The experiment scripts" "Every experiment is a real, readable Python script, not a black box."
run "ls -la scripts/"
run "head -40 scripts/exp1_deploy.py"
pause

step "The raw data" "Every number in the paper traces back to one of these CSV files."
run "ls -la experiments/raw/"
run "head -5 experiments/raw/exp1_deploy.csv"
run "wc -l experiments/raw/*.csv"
pause

step "Fresh experimental runs, live, right now" "Re-run a handful of real deployments and watch new rows land with today's timestamp."
run "python3 scripts/exp1_deploy.py --configs docker --runs 5 --out experiments/raw/exp1_deploy_live_demo.csv"
run "cat experiments/raw/exp1_deploy_live_demo.csv"
pause

step "Derive the result from that raw file, live" "The paper's numbers are just this computation on the CSV — nothing hidden."
python3 -c "
import csv, statistics
with open('experiments/raw/exp1_deploy_live_demo.csv') as f:
    rows = list(csv.DictReader(f))
vals = [float(r['wall_seconds']) for r in rows]
print('n =', len(vals))
print('mean =', round(statistics.mean(vals), 3), 's')
print('stdev =', round(statistics.pstdev(vals), 3), 's')
print()
print('Compare to Table III in the paper: Docker mean 1.454s')
"
pause

step "Cleanup" "Tear everything down. The freshly generated demo file is left in place as further evidence, unless you'd rather remove it."
run "docker compose --profile full down"
echo
read -rp "Delete experiments/raw/exp1_deploy_live_demo.csv ? [y/N] " ans
if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
    rm -f experiments/raw/exp1_deploy_live_demo.csv
    echo "Removed."
else
    echo "Kept — it's genuine data either way."
fi

echo
echo "${BOLD}${GREEN}Demo complete.${RESET}"
