#!/usr/bin/env bash

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BOLD=$(tput bold 2>/dev/null || echo "")
DIM=$(tput dim 2>/dev/null || echo "")
GREEN=$(tput setaf 2 2>/dev/null || echo "")
YELLOW=$(tput setaf 3 2>/dev/null || echo "")
RESET=$(tput sgr0 2>/dev/null || echo "")

STEP_NUM=0
LOAD_PID=""

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

show() {
    echo "${BOLD}Opening in browser:${RESET} $1"
    echo "${DIM}Look for: $2${RESET}"
    xdg-open "$1" >/dev/null 2>&1 &
}

start_load() {
    ( while true; do
        curl -s localhost:8000/health >/dev/null
        curl -s "localhost:8000/cpu?iterations=500000" >/dev/null
      done ) &
    LOAD_PID=$!
}

stop_load() {
    [[ -n "$LOAD_PID" ]] && kill "$LOAD_PID" 2>/dev/null
    LOAD_PID=""
}

trap stop_load EXIT

wait_healthy() {
    for _ in $(seq 1 30); do
        curl -sf localhost:8000/health >/dev/null && return 0
        sleep 1
    done
    echo "app did not become healthy"
}

# ---------------------------------------------------------------------------

step "Repo identity" "A real, pushed repository with its full history."
run "git remote -v"
run "git log --oneline | head -15"
run 'git log -1 --format="Last commit: %ai"'
pause

step "The machine" "Same hardware as Table II. The OS was reinstalled after data collection."
run "lscpu | grep -E 'Model name|^CPU\(s\):|Thread|Core'"
run "free -h"
run "docker --version"
pause

step "Start the full pipeline" "App + cAdvisor + Prometheus + Grafana, all as Docker containers from one docker-compose.yml."
run "docker compose --profile full up -d"
wait_healthy
sleep 3
run "docker compose --profile full ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'"
pause

step "1/5  The application" "A small FastAPI service with a cheap route, a CPU-heavy route and a memory-heavy route."
run "curl -s localhost:8000/health; echo"
run "curl -s 'localhost:8000/cpu?iterations=500000'; echo"
run "curl -s 'localhost:8000/memory?mb=5'; echo"
show "http://localhost:8000/metrics" "app_requests_total, app_process_cpu_percent, app_process_memory_bytes -- raw counters the app exposes"
pause

step "2/5  cAdvisor" "Measures CPU/memory of every container from outside, via the kernel's cgroups."
show "http://localhost:8080/docker/" "the list of running containers; click one to see its live CPU and memory graphs"
pause

step "3/5  Prometheus - what it scrapes" "Prometheus pulls /metrics from each target every 2 seconds and stores the time series."
run "curl -s localhost:9090/api/v1/targets | python3 -c \"import json,sys; [print(t['labels']['job'].ljust(12), t['health']) for t in json.load(sys.stdin)['data']['activeTargets']]\""
show "http://localhost:9090/targets" "app, cadvisor and prometheus all green / UP, with 'last scrape' ticking"
pause

step "4/5  Prometheus - live query" "Generating background traffic now so the graphs move."
start_load
show "http://localhost:9090/graph?g0.expr=app_process_cpu_percent&g0.tab=0&g0.range_input=5m" "the CPU line climbing as the traffic starts"
pause

step "5/5  Grafana dashboard" "Auto-provisioned from monitoring/grafana/provisioning -- no manual setup."
show "http://localhost:3000/d/cicd-monitoring-study-app?refresh=5s&from=now-5m&to=now" "request-rate and CPU panels moving under the live traffic; 'Target up/down' at 1"
pause
stop_load

step "Live failure: what Experiment 5 measures" "Kill the app container and watch monitoring notice, then bring it back."
show "http://localhost:9090/targets" "keep this tab and the Grafana tab side by side"
pause
run "docker kill cicd-monitoring-study-app-1"
KILL_T=$(date +%s.%N)
until [[ "$(curl -s 'localhost:9090/api/v1/query?query=up%7Bjob%3D%22app%22%7D' | python3 -c "import json,sys; r=json.load(sys.stdin)['data']['result']; print(r[0]['value'][1] if r else '')")" == "0" ]]; do sleep 0.3; done
echo "${GREEN}Prometheus reports app DOWN after $(python3 -c "print(round($(date +%s.%N) - $KILL_T, 2))")s${RESET}"
echo "${DIM}Refresh the targets tab: app is red. Grafana's up/down panel drops to 0.${RESET}"
pause
run "docker start cicd-monitoring-study-app-1"
START_T=$(date +%s.%N)
wait_healthy
echo "${GREEN}App healthy again after $(python3 -c "print(round($(date +%s.%N) - $START_T, 2))")s${RESET}"
pause

step "CI/CD (real GitHub Actions)" "Optional: triggers a real workflow run (test -> docker build -> push). ~45-65s, uses Actions minutes."
read -rp "Run this step? [Y/n] " gha_ans
if [[ "$gha_ans" == "n" || "$gha_ans" == "N" ]]; then
    echo "${DIM}Skipped.${RESET}"
else
    show "https://github.com/vinayaktyagi10/cicd-monitoring-study/actions" "the new run appearing at the top"
    run "gh workflow run ci.yml --ref master"
    echo "Waiting for the run to register..."
    sleep 6
    RUN_ID=$(gh run list --workflow=ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    echo "${YELLOW}\$ gh run watch $RUN_ID --exit-status${RESET}"
    gh run watch "$RUN_ID" --exit-status
fi
pause

step "From experiment to raw data" "Each experiment script does the thing above 20 times and writes one CSV row per run."
run "ls experiments/scripts/"
run "head -6 experiments/raw/exp5_failure_recovery.csv"
run "wc -l experiments/raw/*.csv"
pause

step "From raw data to the paper's tables" "aggregate.py averages the raw rows; paper_tables.py rebuilds every table and checks it against paper.tex."
run "python3 experiments/scripts/aggregate.py"
run "git diff --stat experiments/results/ && echo 'results/ identical to the committed tables'"
run "python3 experiments/scripts/paper_tables.py"
pause

step "Cleanup" "Tear everything down."
run "docker compose --profile full down"
echo
echo "${BOLD}${GREEN}Demo complete.${RESET}"
