# Experiment log

Append-only, raw. One entry per run (or batch of runs) as they happen — the
mean/std/min/max tables in the paper are computed from this, never typed by
hand.

Entry shape:

```
## YYYY-MM-DD HH:MM — <experiment name> — run <n>/<total>
Config: <Manual | Docker | Docker+CI/CD | Full pipeline>
Command: <exact command run>
Raw output / metrics: <pasted numbers or path to raw file>
Notes: <anything anomalous>
```
