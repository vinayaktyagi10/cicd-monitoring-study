#!/usr/bin/env python3
"""Recomputes the statistical-methods numbers quoted in paper/paper.tex (assumption
checks, test agreement, Holm correction) from a campaign's original_vs_replication.csv
and checks that each appears verbatim in the paper. Exit status 1 on any miss.

    python stats_prose.py --campaign ../replication/<dir>
"""
import argparse
import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GREEN, RED, BOLD, RESET = "\033[32m", "\033[31m", "\033[1m", "\033[0m"


def num(x):
    return float(x) if x not in ("", "nan") else float("nan")


def claims(rows):
    t = [r for r in rows if r.get("welch_p")]
    n = len(t)
    nonnormal = sum(num(r["sw_p_orig"]) < .05 or num(r["sw_p_rep"]) < .05 for r in t)
    agree_mw = sum((num(r["welch_p"]) < .05) == (num(r["mw_p"]) < .05) for r in t)
    agree_ci = sum((r["verdict"] == "DIFFERENT") == (num(r["welch_p"]) < .05) for r in t)
    diff = [r for r in t if r["verdict"] == "DIFFERENT"]
    holm = sum(num(r["welch_p_holm"]) < .05 for r in diff)
    mttr = next(r for r in t if r["metric"] == "MTTR (s)")
    return [
        ("metrics compared", f"{n} metrics"),
        ("normality rejected", f"{nonnormal} of {n} metrics"),
        ("Welch and Mann-Whitney agree", f"agree on {agree_mw} of {n}"),
        ("interval rule and Welch agree", f"agree on {agree_ci} of {n}"),
        ("different rows surviving Holm", f"{holm} of {len(diff)} rows marked different"),
        ("MTTR rank effect", f"Cliff's $\\delta{{=}}{num(mttr['cliffs_delta']):.2f}$"),
        ("MTTR Holm-adjusted rank p", f"$p{{=}}{num(mttr['mw_p_holm']):.4f}$"),
    ]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--campaign", required=True)
    args = p.parse_args()
    with open(os.path.join(args.campaign, "results", "original_vs_replication.csv"), newline="") as fh:
        rows = list(csv.DictReader(fh))
    with open(os.path.join(ROOT, "paper", "paper.tex")) as fh:
        paper = re.sub(r"\s+", " ", fh.read())
    misses = 0
    print(f"\n{BOLD}Statistical-analysis numbers{RESET}")
    cl = claims(rows)
    for what, text in cl:
        ok = re.sub(r"\s+", " ", text) in paper
        misses += not ok
        print(f"  [{GREEN + 'MATCH' if ok else RED + 'NOT FOUND'}{RESET}] {what}: {text}")
    print(f"\n{len(cl) - misses}/{len(cl)} statistical-analysis numbers found verbatim in paper.tex")
    sys.exit(1 if misses else 0)


if __name__ == "__main__":
    main()
