#!/usr/bin/env python3
"""Dependency-free concurrent HTTP load generator.

Pure stdlib (urllib + ThreadPoolExecutor) so it needs no install step and is
fully inspectable — deliberate choice over hey/locust for this study.
"""
import argparse
import csv
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def one_request(url, timeout):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        status = 0
    latency = time.perf_counter() - start
    return time.time(), status, latency


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--requests", type=int, default=200)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--out", required=True, help="CSV output path")
    args = p.parse_args()

    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futures = [ex.submit(one_request, args.url, args.timeout) for _ in range(args.requests)]
        for f in as_completed(futures):
            results.append(f.result())

    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "status", "latency_seconds"])
        w.writerows(results)

    latencies = [r[2] for r in results]
    errors = sum(1 for r in results if r[1] < 200 or r[1] >= 300)
    latencies.sort()
    def pct(p):
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    print(f"requests={len(results)} errors={errors} error_rate={errors/len(results):.4f}")
    print(f"mean_latency_ms={statistics.mean(latencies)*1000:.2f} "
          f"p50_ms={pct(0.5)*1000:.2f} p95_ms={pct(0.95)*1000:.2f} p99_ms={pct(0.99)*1000:.2f} "
          f"max_ms={max(latencies)*1000:.2f}")


if __name__ == "__main__":
    main()
