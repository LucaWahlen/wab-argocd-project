import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_ts(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def main(run_dir: str) -> None:
    run_dir = Path(run_dir)
    buckets = {}
    latencies = []

    with (run_dir / "k6.json").open() as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "Point":
                continue
            metric = rec["metric"]
            data = rec["data"]
            tags = data.get("tags", {})
            sec = int(parse_ts(data["time"]))
            b = buckets.setdefault(sec, {"reqs": 0, "ok": 0, "http_fail": 0, "net_fail": 0, "codes": {}})
            if metric == "http_reqs":
                b["reqs"] += 1
                status = str(tags.get("status", "0"))
                b["codes"][status] = b["codes"].get(status, 0) + 1
                if status == "0":
                    b["net_fail"] += 1
                elif status.startswith("2"):
                    b["ok"] += 1
                else:
                    b["http_fail"] += 1
            elif metric == "http_req_duration":
                latencies.append(data["value"])

    rows = ["epoch,reqs,ok,http_fail,net_fail,codes"]
    total = {"reqs": 0, "ok": 0, "http_fail": 0, "net_fail": 0}
    for sec in sorted(buckets):
        b = buckets[sec]
        for k in total:
            total[k] += b[k]
        codes = ";".join(f"{code}:{n}" for code, n in sorted(b["codes"].items()))
        rows.append(f"{sec},{b['reqs']},{b['ok']},{b['http_fail']},{b['net_fail']},{codes}")
    (run_dir / "timeseries.csv").write_text("\n".join(rows) + "\n")

    lat = sorted(latencies)
    n = len(lat)

    def pct(p):
        return lat[min(n - 1, int(n * p))] if n else 0.0

    ts = {}
    tfile = run_dir / "timestamps.csv"
    if tfile.exists():
        for pair in tfile.read_text().strip().split(","):
            k, v = pair.split("=")
            ts[k] = float(v)

    summary = {
        "requests": total["reqs"],
        "ok": total["ok"],
        "http_fail": total["http_fail"],
        "net_fail": total["net_fail"],
        "fail_share": round((total["http_fail"] + total["net_fail"]) / max(total["reqs"], 1), 4),
        "http_fail_share": round(total["http_fail"] / max(total["reqs"], 1), 4),
        "net_fail_share": round(total["net_fail"] / max(total["reqs"], 1), 4),
        "latency_med_ms": round(pct(0.5), 3),
        "latency_p95_ms": round(pct(0.95), 3),
        "latency_p99_ms": round(pct(0.99), 3),
        "avg_rps": round(total["reqs"] / max(len(buckets), 1), 1),
        "timestamps": ts,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
