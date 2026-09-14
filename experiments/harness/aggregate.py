import csv
import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"


def load_run(run_dir: Path):
    summary_file = run_dir / "summary.json"
    if not summary_file.exists():
        return None
    summary = json.loads(summary_file.read_text())
    ts = summary.get("timestamps", {})

    pods_max = 0
    ready_min = None
    v2_seen = False
    v1_seen = False
    sampler = run_dir / "sampler.csv"
    if sampler.exists():
        with sampler.open() as fh:
            for row in csv.DictReader(fh):
                try:
                    n = int(row["pods"])
                except (ValueError, KeyError):
                    continue
                pods_max = max(pods_max, n)
                ready = int(row["ready"]) if row.get("ready") else None
                if ready is not None:
                    ready_min = ready if ready_min is None else min(ready_min, ready)
                imgs = row.get("images", "")
                if "v2" in imgs:
                    v2_seen = True
                if "v1" in imgs:
                    v1_seen = True

    def dur(a, b):
        if a in ts and b in ts:
            return round(ts[b] - ts[a], 2)
        return None

    parts = run_dir.name.split("-")
    scenario = "success" if "success" in parts else "faulty"
    variant = "baseline" if run_dir.name.startswith("baseline") else "rollout"
    rep = run_dir.name.rsplit("rep", 1)[-1]

    row = {
        "variant": variant,
        "scenario": scenario,
        "rep": rep,
        "requests": summary["requests"],
        "http_fail": summary["http_fail"],
        "net_fail": summary["net_fail"],
        "fail_share_pct": round(100 * summary["fail_share"], 4),
        "latency_med_ms": summary["latency_med_ms"],
        "latency_p95_ms": summary["latency_p95_ms"],
        "latency_p99_ms": summary["latency_p99_ms"],
        "switch_s": dur("t0", "t_healthy"),
        "rollback_to_stable_s": dur("t_revert", "t_stable"),
        "max_pods_during_run": pods_max,
        "min_ready_pods": ready_min,
        "v1_and_v2_observed": v1_seen and v2_seen,
    }
    return row


def main():
    rows = []
    for run_dir in sorted(RESULTS.iterdir()):
        if not run_dir.is_dir():
            continue
        r = load_run(run_dir)
        if r:
            rows.append(r)

    out_csv = RESULTS / "aggregate.csv"
    if rows:
        with out_csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    measured = [r for r in rows if r["rep"].isdigit()]
    print(f"{'variant':9} {'scenario':8} {'rep':4} {'fails':>6} {'fail%':>7} {'med ms':>7} {'p95 ms':>7} {'switch s':>9} {'maxpods':>8} {'minready':>9}")
    for r in rows:
        print(
            f"{r['variant']:9} {r['scenario']:8} {r['rep']:>4} "
            f"{r['http_fail'] + r['net_fail']:>6} {r['fail_share_pct']:>7} "
            f"{r['latency_med_ms']:>7} {r['latency_p95_ms']:>7} "
            f"{str(r['switch_s'] if r['scenario'] == 'success' else r['rollback_to_stable_s']):>9} "
            f"{r['max_pods_during_run']:>8} {str(r['min_ready_pods']):>9}"
        )
    out_json = RESULTS / "aggregate.json"
    out_json.write_text(json.dumps(rows, indent=2) + "\n")
    print(f"\nwrote {out_csv} and aggregate.json ({len(measured)} measured runs, {len(rows) - len(measured)} unweighted)")


if __name__ == "__main__":
    main()
