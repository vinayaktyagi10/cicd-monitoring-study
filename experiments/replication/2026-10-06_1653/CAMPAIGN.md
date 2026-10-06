# Replication campaign 2026-10-06_1653

Invocation: `experiments/scripts/campaign.py`

## 2026-10-06T16:53:48+05:30 - e1
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp1_deploy.py --configs manual docker full_pipeline --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp1_deploy.csv`
Exit code: 0, duration 2.0 min, background CPU before start 0.05 cores
Log: logs/e1.log

## 2026-10-06T16:57:02+05:30 - e2
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp2_resource.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp2_resource.csv`
Exit code: 0, duration 3.0 min, background CPU before start 0.22 cores
Log: logs/e2.log

## 2026-10-06T17:01:14+05:30 - e3
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp3_cpu_stress.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp3_cpu_stress.csv`
Exit code: 0, duration 2.7 min, background CPU before start 0.05 cores
Log: logs/e3.log

## 2026-10-06T17:05:08+05:30 - e4
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp4_memory_stress.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp4_memory_stress.csv`
Exit code: 0, duration 10.8 min, background CPU before start 0.05 cores
Log: logs/e4.log

## 2026-10-06T17:17:07+05:30 - e5
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp5_failure_recovery.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp5_failure_recovery.csv`
Exit code: 0, duration 2.8 min, background CPU before start 0.05 cores
Log: logs/e5.log

## 2026-10-06T17:21:09+05:30 - e6
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp6_overhead.py --runs 20 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp6_overhead.csv`
Exit code: 0, duration 73.3 min, background CPU before start 0.05 cores
Log: logs/e6.log

## 2026-10-06T18:35:41+05:30 - e6x4
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp6_overhead.py --runs 10 --cases docker docker_full --loadgen-procs 4 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp6_overhead_loadgen4.csv`
Exit code: 0, duration 24.4 min, background CPU before start 0.05 cores
Log: logs/e6x4.log

## 2026-10-06T23:47:23+05:30 - e1cicd: NOT RUN
Preconditions failed: background CPU 0.79 cores > --max-busy-cores 0.5

## 2026-10-06T23:47:47+05:30 - e1cicd: NOT RUN
Preconditions failed: background CPU 0.80 cores > --max-busy-cores 0.5

## 2026-10-06T23:55:45+05:30 - e1cicd
Command: `/home/vinayak/Research/cicd-monitoring-study/.venv/bin/python /home/vinayak/Research/cicd-monitoring-study/experiments/scripts/exp1_deploy.py --configs docker_cicd --runs 8 --out /home/vinayak/Research/cicd-monitoring-study/experiments/replication/2026-10-06_1653/raw/exp1_deploy.csv`
Exit code: 0, duration 8.4 min, background CPU before start 0.18 cores
Log: logs/e1cicd.log

