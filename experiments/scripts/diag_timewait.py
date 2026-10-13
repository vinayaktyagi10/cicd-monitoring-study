#!/usr/bin/env python3
"""Experiment 6 diagnostic -- why does throughput collapse run to run?

Per-second time series of throughput, host TIME_WAIT sockets, and user vs.
system CPU of docker-proxy and of this load generator, under the Experiment 6
client (new TCP connection per request) and a keep-alive client (one
connection per worker). Each rep starts with TIME_WAIT drained, app-only stack.
"""
import argparse
import csv
import os
import threading
import time

import exp6_overhead as e6
import hostmetrics as hm

HZ = os.sysconf("SC_CLK_TCK")


def user_sys(pids):
    u = s = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as fh:
                f = fh.read().rsplit(")", 1)[1].split()
            u += int(f[11])
            s += int(f[12])
        except OSError:
            pass
    return u / HZ, s / HZ


def wait_drained(limit, timeout=300):
    deadline = time.time() + timeout
    while hm.read_timewait() > limit:
        if time.time() > deadline:
            raise RuntimeError("TIME_WAIT did not drain")
        time.sleep(2)


def one_rep(mode, duration, concurrency, interval):
    count = [0]
    lock = threading.Lock()
    deadline = time.perf_counter() + duration

    def worker():
        client = e6.KeepAliveClient() if mode == "keepalive" else None
        while time.perf_counter() < deadline:
            st, _ = client.request() if client else e6.one_request()
            if 200 <= st < 300:
                with lock:
                    count[0] += 1
        if client:
            client.close()

    pids = e6.proxy_pids()
    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    t0 = time.perf_counter()
    last_t, last_n, last_p, last_c = t0, 0, user_sys(pids), os.times()
    for t in threads:
        t.start()
    rows = []
    while any(t.is_alive() for t in threads):
        time.sleep(interval)
        now, n, p, c = time.perf_counter(), count[0], user_sys(pids), os.times()
        dt = now - last_t
        rows.append({"t_s": now - t0, "ok_rps": (n - last_n) / dt, "timewait": hm.read_timewait(),
                     "proxy_user_cores": (p[0] - last_p[0]) / dt, "proxy_sys_cores": (p[1] - last_p[1]) / dt,
                     "loadgen_user_cores": (c.user - last_c.user) / dt,
                     "loadgen_sys_cores": (c.system - last_c.system) / dt})
        last_t, last_n, last_p, last_c = now, n, p, c
    for t in threads:
        t.join()
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--duration", type=float, default=40.0)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--drained", type=int, default=200, help="start a rep only below this many TIME_WAIT sockets")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    with open("/proc/sys/net/ipv4/ip_local_port_range") as fh:
        lo, hi = map(int, fh.read().split())
    print(f"ephemeral ports {lo}-{hi} ({hi - lo + 1})")

    e6.teardown()
    e6.bring_up(["app"])
    time.sleep(5)
    fields = ["rep", "mode", "concurrency", "port_range_size", "t_s", "ok_rps", "timewait", "proxy_user_cores",
              "proxy_sys_cores", "loadgen_user_cores", "loadgen_sys_cores"]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for rep in range(1, args.reps + 1):
            for mode in ("per_request", "keepalive"):
                wait_drained(args.drained)
                rows = one_rep(mode, args.duration, args.concurrency, args.interval)
                for r in rows:
                    w.writerow({"rep": rep, "mode": mode, "concurrency": args.concurrency,
                                "port_range_size": hi - lo + 1,
                                **{k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()}})
                fh.flush()
                tail = rows[-max(1, len(rows) // 4):]
                print(f"rep {rep} {mode:11s} first5s {sum(r['ok_rps'] for r in rows[:5]) / 5:7.0f} rps  "
                      f"last-quarter {sum(r['ok_rps'] for r in tail) / len(tail):7.0f} rps  "
                      f"max TIME_WAIT {max(r['timewait'] for r in rows)}  "
                      f"last-quarter proxy sys {sum(r['proxy_sys_cores'] for r in tail) / len(tail):.2f}",
                      flush=True)
    e6.teardown()


if __name__ == "__main__":
    main()
