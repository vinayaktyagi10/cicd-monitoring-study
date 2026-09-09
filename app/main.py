import os
import threading
import time

from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

app = FastAPI(title="cicd-monitoring-study subject app")

REQUEST_COUNT = Counter(
    "app_requests_total", "Total requests", ["endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds", "Request latency", ["endpoint"]
)
PROCESS_CPU_PERCENT = Gauge(
    "app_process_cpu_percent", "Process CPU utilization sampled every second"
)
PROCESS_MEMORY_BYTES = Gauge(
    "app_process_memory_bytes", "Process resident memory (VmRSS)"
)

_memory_ballast: list[bytearray] = []


def _read_rss_bytes():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    return 0


def _resource_monitor_loop(interval=1.0):
    last_cpu = time.process_time()
    last_wall = time.perf_counter()
    while True:
        time.sleep(interval)
        now_cpu = time.process_time()
        now_wall = time.perf_counter()
        cpu_pct = (now_cpu - last_cpu) / (now_wall - last_wall) * 100
        PROCESS_CPU_PERCENT.set(cpu_pct)
        PROCESS_MEMORY_BYTES.set(_read_rss_bytes())
        last_cpu, last_wall = now_cpu, now_wall


threading.Thread(target=_resource_monitor_loop, daemon=True).start()


@app.get("/health")
def health():
    start = time.perf_counter()
    REQUEST_COUNT.labels(endpoint="health", status="200").inc()
    REQUEST_LATENCY.labels(endpoint="health").observe(time.perf_counter() - start)
    return {"status": "ok"}


@app.get("/cpu")
def cpu_bound(iterations: int = 2_000_000):
    start = time.perf_counter()
    total = 0
    for i in range(iterations):
        total += i * i
    REQUEST_COUNT.labels(endpoint="cpu", status="200").inc()
    REQUEST_LATENCY.labels(endpoint="cpu").observe(time.perf_counter() - start)
    return {"result": total, "iterations": iterations}


@app.get("/memory")
def memory_alloc(mb: int = 10, hold: bool = False):
    start = time.perf_counter()
    block = bytearray(mb * 1024 * 1024)
    if hold:
        _memory_ballast.append(block)
    REQUEST_COUNT.labels(endpoint="memory", status="200").inc()
    REQUEST_LATENCY.labels(endpoint="memory").observe(time.perf_counter() - start)
    return {"allocated_mb": mb, "held": hold, "ballast_blocks": len(_memory_ballast)}


@app.post("/memory/reset")
def memory_reset():
    _memory_ballast.clear()
    return {"ballast_blocks": len(_memory_ballast)}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
