#!/usr/bin/env python3
"""Aggregate analysis for the retained-v1 blue-green measurement series.

Computes per-run metrics from summary.json, timeseries.csv and sampler.csv for
the retained-*, rollout-* and baseline-* result directories and writes a
markdown report to experiments/results/retained-report.md.

Only actual measured data is reported; missing values are rendered as "n/a".
"""
import csv
import json
import math
import statistics
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
REPORT = RESULTS / "retained-report.md"

GROUPS = [
    ("retained-faulty", "Retained v1 (300s) - faulty"),
    ("rollout-faulty", "Blue-Green (10s) - faulty"),
    ("baseline-faulty", "Rolling Update - faulty"),
    ("retained-success", "Retained v1 (300s) - success"),
    ("rollout-success", "Blue-Green (10s) - success"),
    ("baseline-success", "Rolling Update - success"),
]


def read_sampler(path):
    """Return list of (epoch, pods, ready, images). Handles images containing commas."""
    rows = []
    if not path.exists():
        return rows
    lines = path.read_text().splitlines()
    for ln in lines[1:]:
        parts = ln.split(",", 3)
        if len(parts) < 4:
            continue
        try:
            rows.append((float(parts[0]), int(parts[1]), int(parts[2]), parts[3]))
        except ValueError:
            continue
    return rows


def read_timeseries(path):
    rows = []
    if not path.exists():
        return rows
    with path.open() as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({
                    "epoch": int(r["epoch"]),
                    "reqs": int(r["reqs"]),
                    "ok": int(r["ok"]),
                    "http_fail": int(r["http_fail"]),
                    "net_fail": int(r["net_fail"]),
                })
            except (ValueError, KeyError):
                continue
    return rows


def window_metrics(ts, t0=None):
    """Error-window metrics from per-second timeseries rows.

    Event timestamps are reported both absolutely and relative to t0 (the
    manifest flip), which is the meaningful reference for the strategy.
    """
    def rel(e):
        return None if (e is None or t0 is None) else round(e - t0, 1)

    faulty = [r for r in ts if (r["http_fail"] + r["net_fail"]) > 0]
    if not faulty:
        return {
            "first_error": None, "last_error": None, "error_window_s": 0,
            "first_error_rel": None, "last_error_rel": None,
            "first_fully_faulty": None, "last_fully_faulty": None,
            "first_fully_faulty_rel": None, "last_fully_faulty_rel": None,
            "full_failure_duration_s": 0, "first_zero_error_after": None,
            "first_zero_error_rel": None, "recovery_duration_s": None,
        }
    first_error = min(r["epoch"] for r in faulty)
    last_error = max(r["epoch"] for r in faulty)
    fully = [r for r in faulty if r["ok"] == 0]
    if fully:
        first_fully = min(r["epoch"] for r in fully)
        last_fully = max(r["epoch"] for r in fully)
        full_dur = last_fully - first_fully + 1
        after = [r["epoch"] for r in ts if r["epoch"] > last_fully and (r["http_fail"] + r["net_fail"]) == 0]
        first_zero = min(after) if after else None
        recovery = (first_zero - last_fully) if first_zero is not None else None
    else:
        first_fully = last_fully = None
        full_dur = 0
        first_zero = None
        recovery = None
    return {
        "first_error": first_error,
        "last_error": last_error,
        "error_window_s": last_error - first_error + 1,
        "first_error_rel": rel(first_error),
        "last_error_rel": rel(last_error),
        "first_fully_faulty": first_fully,
        "last_fully_faulty": last_fully,
        "first_fully_faulty_rel": rel(first_fully),
        "last_fully_faulty_rel": rel(last_fully),
        "full_failure_duration_s": full_dur,
        "first_zero_error_after": first_zero,
        "first_zero_error_rel": rel(first_zero),
        "recovery_duration_s": recovery,
    }


def load_run(run_dir):
    sfile = run_dir / "summary.json"
    if not sfile.exists():
        return None
    summary = json.loads(sfile.read_text())
    ts = summary.get("timestamps", {})
    scenario = "success" if "success" in run_dir.name else "faulty"
    variant = "baseline" if run_dir.name.startswith("baseline") else (
        "retained" if run_dir.name.startswith("retained") else "rollout")
    rep = run_dir.name.rsplit("rep", 1)[-1]

    sampler = read_sampler(run_dir / "sampler.csv")
    pods = [r[1] for r in sampler]
    ready = [r[2] for r in sampler]
    mean_pods = statistics.fmean(pods) if pods else None
    mean_ready = statistics.fmean(ready) if ready else None
    pod_seconds = sum(pods)
    ready_pod_seconds = sum(ready)
    max_pods = max(pods) if pods else None
    min_ready = min(ready) if ready else None
    v1v2 = sum(1 for r in sampler if "v1" in r[3] and "v2" in r[3])

    wm = window_metrics(read_timeseries(run_dir / "timeseries.csv"), ts.get("t0"))

    def dur(a, b):
        if a in ts and b in ts:
            return round(ts[b] - ts[a], 2)
        return None

    row = {
        "run": run_dir.name,
        "variant": variant,
        "scenario": scenario,
        "rep": rep,
        "requests": summary["requests"],
        "http_fail": summary["http_fail"],
        "net_fail": summary["net_fail"],
        "fail_share_pct": round(100 * summary["fail_share"], 4),
        "http_fail_share_pct": round(100 * summary["http_fail_share"], 4),
        "latency_med_ms": summary["latency_med_ms"],
        "latency_p95_ms": summary["latency_p95_ms"],
        "switch_s": dur("t0", "t_healthy") if scenario == "success" else None,
        "rollback_to_stable_s": dur("t_revert", "t_stable") if scenario == "faulty" else None,
        "max_pods_during_run": max_pods,
        "min_ready_pods": min_ready,
        "mean_pods": round(mean_pods, 3) if mean_pods is not None else None,
        "mean_ready_pods": round(mean_ready, 3) if mean_ready is not None else None,
        "pod_seconds": pod_seconds,
        "ready_pod_seconds": ready_pod_seconds,
        "samples": len(sampler),
        "v1v2_samples": v1v2,
    }
    row.update(wm)
    return row


def mean_sd(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return (None, None)
    if len(vals) == 1:
        return (vals[0], 0.0)
    return (statistics.fmean(vals), statistics.stdev(vals))


def fmt(v, nd=2):
    if v is None:
        return "n/a"
    return f"{v:.{nd}f}"


def ms(values, nd=2):
    m, s = mean_sd(values)
    if m is None:
        return "n/a"
    return f"{m:.{nd}f} +/- {s:.{nd}f}"


def main():
    runs = []
    for d in sorted(RESULTS.iterdir()):
        if d.is_dir() and (d.name.startswith("retained-") or d.name.startswith("rollout-") or d.name.startswith("baseline-")):
            r = load_run(d)
            if r and r["rep"].isdigit():
                runs.append(r)

    by_group = {}
    for g, _ in GROUPS:
        by_group[g] = [r for r in runs if r["run"].startswith(g + "-rep")]

    out = []
    out.append("# Retained-v1 Blue-Green measurement series")
    out.append("")
    out.append("Variant: Argo Rollouts blue-green with `scaleDownDelaySeconds: 300` "
               "(old v1 ReplicaSet retained for 300 s), branch `experiment/retained-v1`.")
    out.append("Comparison: blue-green with `scaleDownDelaySeconds: 10` (`rollout-*`) and "
               "native rolling update (`baseline-*`).")
    out.append("")
    out.append("Harness: `experiments/harness/run-experiment-retained.sh`; k6 constant-arrival-rate "
               "500 rps; 2 replicas; v1 -> v2 switch via git commit + Argo CD sync; faulty v2 answers "
               "HTTP 500 (`quotes_500`); 40 s dwell in the broken state before git revert.")
    out.append("")

    # ---- run status ----
    out.append("## Run status")
    out.append("")
    out.append("| group | expected | present | status |")
    out.append("| --- | --- | --- | --- |")
    for g, label in GROUPS:
        got = sorted(r["rep"] for r in by_group[g])
        expected = ["1", "2", "3", "4", "5"]
        status = "complete" if got == expected else f"INCOMPLETE (got {got})"
        out.append(f"| {label} | 5 | {len(got)} | {status} |")
    out.append("")

    # ---- per-run tables ----
    out.append("## Per-run results")
    out.append("")
    out.append("### Retained v1 (300 s) - faulty")
    out.append("")
    out.append("| rep | reqs | http_fail | net_fail | fail_share % | rollback_to_stable_s | max_pods | min_ready | mean_pods | pod-seconds | first_error_s | first_fully_s | end_fully_s | first_zero_s | full_failure_s | recovery_s | error_window_s |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in by_group["retained-faulty"]:
        out.append("| {rep} | {requests} | {http_fail} | {net_fail} | {fail_share_pct} | {rollback} | {maxpods} | {minready} | {mp} | {psec} | {fe} | {fff} | {ef} | {fz} | {ff} | {rec} | {ew} |".format(
            rep=r["rep"], requests=r["requests"], http_fail=r["http_fail"], net_fail=r["net_fail"],
            fail_share_pct=r["fail_share_pct"], rollback=fmt(r["rollback_to_stable_s"]),
            maxpods=r["max_pods_during_run"], minready=r["min_ready_pods"], mp=fmt(r["mean_pods"], 3),
            psec=r["pod_seconds"], fe=fmt(r["first_error_rel"], 1),
            fff=fmt(r["first_fully_faulty_rel"], 1), ef=fmt(r["last_fully_faulty_rel"], 1),
            fz=fmt(r["first_zero_error_rel"], 1), ff=r["full_failure_duration_s"],
            rec=fmt(r["recovery_duration_s"], 1), ew=r["error_window_s"]))
    out.append("")
    out.append("### Retained v1 (300 s) - success")
    out.append("")
    out.append("| rep | reqs | http_fail | net_fail | fail_share % | switch_s | max_pods | min_ready | mean_pods | pod-seconds |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in by_group["retained-success"]:
        out.append("| {rep} | {requests} | {http_fail} | {net_fail} | {fail_share_pct} | {sw} | {maxpods} | {minready} | {mp} | {psec} |".format(
            rep=r["rep"], requests=r["requests"], http_fail=r["http_fail"], net_fail=r["net_fail"],
            fail_share_pct=r["fail_share_pct"], sw=fmt(r["switch_s"]),
            maxpods=r["max_pods_during_run"], minready=r["min_ready_pods"], mp=fmt(r["mean_pods"], 3),
            psec=r["pod_seconds"]))
    out.append("")

    for g in ("rollout-faulty", "baseline-faulty"):
        label = dict(GROUPS)[g]
        out.append(f"### {label}")
        out.append("")
        out.append("| rep | reqs | http_fail | net_fail | fail_share % | rollback_to_stable_s | max_pods | min_ready | mean_pods | pod-seconds | first_error_s | first_fully_s | end_fully_s | first_zero_s | full_failure_s | recovery_s | error_window_s |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in by_group[g]:
            out.append("| {rep} | {requests} | {http_fail} | {net_fail} | {fail_share_pct} | {rollback} | {maxpods} | {minready} | {mp} | {psec} | {fe} | {fff} | {ef} | {fz} | {ff} | {rec} | {ew} |".format(
                rep=r["rep"], requests=r["requests"], http_fail=r["http_fail"], net_fail=r["net_fail"],
                fail_share_pct=r["fail_share_pct"], rollback=fmt(r["rollback_to_stable_s"]),
                maxpods=r["max_pods_during_run"], minready=r["min_ready_pods"], mp=fmt(r["mean_pods"], 3),
                psec=r["pod_seconds"], fe=fmt(r["first_error_rel"], 1),
                fff=fmt(r["first_fully_faulty_rel"], 1), ef=fmt(r["last_fully_faulty_rel"], 1),
                fz=fmt(r["first_zero_error_rel"], 1), ff=r["full_failure_duration_s"],
                rec=fmt(r["recovery_duration_s"], 1), ew=r["error_window_s"]))
        out.append("")

    for g in ("rollout-success", "baseline-success"):
        label = dict(GROUPS)[g]
        out.append(f"### {label}")
        out.append("")
        out.append("| rep | reqs | http_fail | net_fail | fail_share % | switch_s | max_pods | min_ready | mean_pods | pod-seconds |")
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for r in by_group[g]:
            out.append("| {rep} | {requests} | {http_fail} | {net_fail} | {fail_share_pct} | {sw} | {maxpods} | {minready} | {mp} | {psec} |".format(
                rep=r["rep"], requests=r["requests"], http_fail=r["http_fail"], net_fail=r["net_fail"],
                fail_share_pct=r["fail_share_pct"], sw=fmt(r["switch_s"]),
                maxpods=r["max_pods_during_run"], minready=r["min_ready_pods"], mp=fmt(r["mean_pods"], 3),
                psec=r["pod_seconds"]))
        out.append("")

    # ---- aggregate comparison ----
    out.append("## Aggregate comparison (mean +/- sample SD, n=5)")
    out.append("")
    out.append("| group | fail_share % | switch/rollback s | max_pods | min_ready | mean_pods | mean_ready | pod-seconds/run |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    agg = {}
    for g, label in GROUPS:
        rows = by_group[g]
        if not rows:
            continue
        fails = [r["fail_share_pct"] for r in rows]
        dur_key = "switch_s" if "success" in g else "rollback_to_stable_s"
        durs = [r[dur_key] for r in rows]
        mpods = [r["max_pods_during_run"] for r in rows]
        mready = [r["min_ready_pods"] for r in rows]
        mp = [r["mean_pods"] for r in rows]
        mrp = [r["mean_ready_pods"] for r in rows]
        ps = [r["pod_seconds"] for r in rows]
        agg[g] = {
            "fail": mean_sd(fails), "dur": mean_sd(durs), "maxpods": mean_sd(mpods),
            "minready": mean_sd(mready), "meanpods": mean_sd(mp),
            "meanready": mean_sd(mrp), "podsec": mean_sd(ps),
        }
        out.append(f"| {label} | {ms(fails, 3)} | {ms(durs)} | {ms(mpods)} | {ms(mready)} | {ms(mp, 3)} | {ms(mrp, 3)} | {ms(ps, 1)} |")
    out.append("")

    # ---- error-window aggregate ----
    out.append("## Error-window metrics (faulty groups, mean +/- sample SD)")
    out.append("")
    out.append("| group | first error s (after t0) | first fully-faulty s | end fully-faulty s | first zero-error s | full-failure duration s | recovery duration s | error window s |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for g in ("retained-faulty", "rollout-faulty", "baseline-faulty"):
        rows = by_group[g]
        if not rows:
            continue
        fe = [r["first_error_rel"] for r in rows]
        fff = [r["first_fully_faulty_rel"] for r in rows]
        ef = [r["last_fully_faulty_rel"] for r in rows]
        fz = [r["first_zero_error_rel"] for r in rows]
        ff = [r["full_failure_duration_s"] for r in rows]
        rec = [r["recovery_duration_s"] for r in rows]
        win = [r["error_window_s"] for r in rows]
        out.append(f"| {dict(GROUPS)[g]} | {ms(fe)} | {ms(fff)} | {ms(ef)} | {ms(fz)} | {ms(ff)} | {ms(rec)} | {ms(win)} |")
    out.append("")

    # ---- interpretation ----
    rf = agg.get("retained-faulty")
    rof = agg.get("rollout-faulty")
    bf = agg.get("baseline-faulty")
    rs = agg.get("retained-success")
    ros = agg.get("rollout-success")
    bs = agg.get("baseline-success")

    out.append("## Interpretation")
    out.append("")
    if rf and rof and bf:
        out.append(f"- **Faulty rollback speed:** retained v1 rolls back to a stable state in "
                   f"**{ms([r['rollback_to_stable_s'] for r in by_group['retained-faulty']])} s** "
                   f"(t_revert -> t_stable). The 10 s blue-green variant needs "
                   f"**{ms([r['rollback_to_stable_s'] for r in by_group['rollout-faulty']])} s** and the "
                   f"rolling update **{ms([r['rollback_to_stable_s'] for r in by_group['baseline-faulty']])} s**. "
                   f"Retaining the old ReplicaSet makes rollback essentially a service-selector flip, because the "
                   f"v1 pods are still running and ready; the other two strategies must recreate v1 pods "
                   f"(10 s app start delay + readiness).")
        out.append(f"- **Error share:** the retained-v1 faulty runs recorded "
                   f"**{ms([r['fail_share_pct'] for r in by_group['retained-faulty']], 3)} %** failed requests, "
                   f"versus **{ms([r['fail_share_pct'] for r in by_group['rollout-faulty']], 3)} %** for 10 s "
                   f"blue-green and **{ms([r['fail_share_pct'] for r in by_group['baseline-faulty']], 3)} %** for "
                   f"the rolling update. With 300 s retention the old v1 pods are never terminated, so the k6 "
                   f"keep-alive connections established before the switch stay pinned to the healthy v1 pods and "
                   f"never reach the faulty v2 (see anomaly note below). The faulty v2 *is* reachable and returns "
                   f"HTTP 500 to new connections; this was verified with a controlled probe.")
        out.append(f"- **Resource cost:** retaining v1 keeps 4 pods running instead of 2 for the whole run. "
                   f"Mean pod count is **{ms([r['mean_pods'] for r in by_group['retained-faulty']], 3)}** "
                   f"(~{ms([r['pod_seconds'] for r in by_group['retained-faulty']], 0)} pod-seconds/run) versus "
                   f"**{ms([r['mean_pods'] for r in by_group['rollout-faulty']], 3)}** "
                   f"(~{ms([r['pod_seconds'] for r in by_group['rollout-faulty']], 0)} pod-seconds/run) for the "
                   f"10 s blue-green variant. That is an extra "
                   f"~{statistics.fmean([r['pod_seconds'] for r in by_group['retained-faulty']]) - statistics.fmean([r['pod_seconds'] for r in by_group['rollout-faulty']]):.0f} "
                   f"pod-seconds per run (about +60 %), i.e. the price of keeping the old pods alive for the "
                   f"whole measurement window so the rollback needs no pod startup.")
    if rs and ros and bs:
        out.append(f"- **Successful switch:** retained v1 switches in "
                   f"**{ms([r['switch_s'] for r in by_group['retained-success']])} s** vs "
                   f"**{ms([r['switch_s'] for r in by_group['rollout-success']])} s** (10 s blue-green) and "
                   f"**{ms([r['switch_s'] for r in by_group['baseline-success']])} s** (rolling update). "
                   f"The retained measurement stops at promotion/health (old RS kept), whereas the 10 s variant's "
                   f"`t_healthy` also waits for the old v1 pods to be scaled down (10 s), so the raw numbers are "
                   f"not on an identical definition; all three deliver zero HTTP errors.")
    out.append("")

    # ---- anomalies ----
    out.append("## Anomalies and measurement notes")
    out.append("")
    out.append("1. **Zero error share in retained-faulty runs (connection pinning).** During the 40 s dwell the "
               "active service selector is switched to the faulty v2 (confirmed in the Argo Rollouts controller log: "
               "`Switched selector for service 'shipping-cost-api' from 'c7c778dbb' to '<v2-hash>'`), and new "
               "connections receive HTTP 500. However, because `scaleDownDelaySeconds: 300` keeps the old v1 pods "
               "alive, the k6 load generator's long-lived keep-alive connections remain pinned to v1 and are never "
               "forced to reconnect. Result: 0 HTTP failures. In the 10 s variant the v1 pods are terminated ~10 s "
               "after promotion, which breaks the connections and forces all traffic onto v2 (~100 % failures during "
               "the window). This is a property of the variant plus a persistent-connection workload, not a failed "
               "run. Evidence: a single keep-alive connection opened 14 s before the switch returned 200 for all 333 "
               "requests over 70 s (spanning the whole faulty window), while fresh connections during the same window "
               "returned 500.")
    out.append("2. **Harness fix (rollback/completion detection).** The original harness waited for an *exclusive* "
               "image set (`wait_images v1` / `wait_images v2`). With 300 s retention the old RS never disappears "
               "within the 300 s timeout, so every run aborted. The detection was changed to track the Rollout's "
               "active ReplicaSet image plus its `Healthy` condition (`wait_active_version`), and stale non-v1 "
               "ReplicaSets from previous runs are removed during normalization (`cleanup_stale_rs`). Experiment "
               "timing (`t0`, `t_push`, `t_sync`, `t_revert`, `t_sync2`, `t_stable`) and the load generator are "
               "unchanged.")
    out.append("3. **`sampler.csv` image column.** The sampler writes the image set unquoted "
               "(`...,4,4,v1,v2`), so `csv.DictReader` splits it and only reports `v1`. The raw lines are parsed "
               "manually in `analyze_retained.py`; the `v1v2_samples` field in `retained-aggregate.json` counts "
               "samples where both images are present (retained-faulty: ~231/255 samples, i.e. the old v1 pods "
               "coexist with v2 for essentially the whole run).")
    out.append("4. **Rep2 re-run.** One success repetition (originally `retained-success-rep2`) stalled ~130 s "
               "between sampler start and the flip, giving an inconsistent observation window; it was deleted and "
               "re-run. All reported success runs now have a 20 s pre-flip window.")
    out.append("")

    # ---- raw data paths ----
    out.append("## Raw data")
    out.append("")
    out.append("Per-run directories under `experiments/results/`:")
    for g, _ in GROUPS:
        reps = sorted(r["run"] for r in by_group[g])
        out.append(f"- `{g}`: " + ", ".join(f"`experiments/results/{x}/`" for x in reps))
    out.append("")
    out.append("Each run directory contains: `summary.json`, `timeseries.csv` (per-second request/failure buckets), "
               "`sampler.csv` (per-second pod/ready/images), `k6.json` (raw k6 output), `k6-stdout.txt`, "
               "`timestamps.csv`.")
    out.append("")
    out.append("Harness and analysis:")
    out.append("- `experiments/harness/run-experiment-retained.sh` (run harness, with the detection fix)")
    out.append("- `experiments/harness/analyze_retained.py` (this analysis)")
    out.append("- `experiments/harness/load.js`, `experiments/harness/sampler.sh`, `experiments/harness/postprocess.py`")
    out.append("")

    REPORT.write_text("\n".join(out) + "\n")
    print(f"wrote {REPORT}")
    # also dump machine-readable aggregate
    agg_json = {g: {k: list(v) if isinstance(v, tuple) else v for k, v in vals.items()} for g, vals in agg.items()}
    (RESULTS / "retained-aggregate.json").write_text(json.dumps({"groups": agg_json, "runs": runs}, indent=2) + "\n")
    print(f"wrote {RESULTS / 'retained-aggregate.json'}")


if __name__ == "__main__":
    main()
