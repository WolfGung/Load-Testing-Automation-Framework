"""Analyze raw samples. A fast failure never hides a slow checkout behind an aggregate."""

import csv
import math
from collections import defaultdict


def percentile(values, fraction):
    if not values:
        return None
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def summarize(rows, duration):
    latencies = [float(row["latency_ms"]) for row in rows]
    failures = sum(int(row["failed"]) for row in rows)
    return {
        "requests": len(rows),
        "failures": failures,
        "error_ratio": failures / len(rows) if rows else None,
        "rps": len(rows) / duration if duration > 0 else 0,
        "successful_rps": (len(rows) - failures) / duration if duration > 0 else 0,
        "p50_ms": percentile(latencies, 0.50),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
    }


def analyze(directory, metadata):
    with (directory / "requests.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    start = metadata["measurement_start"]
    end = start + metadata["stages"][-1]["until_seconds"]
    rows = [
        r
        for r in rows
        if start <= float(r["timestamp"]) and float(r["timestamp"]) + float(r["latency_ms"]) / 1000 <= end
    ]
    duration = end - start
    groups = defaultdict(list)
    for row in rows:
        groups[row["method"] + " " + row["route"]].append(row)
    routes = {name: summarize(samples, duration) for name, samples in sorted(groups.items())}
    thresholds = metadata["thresholds"]
    reasons = []
    if metadata["finished"] < end - 0.5:
        reasons.append("Incomplete measurement window")
    total = summarize(rows, duration)
    if total["requests"] < thresholds["min_requests"]:
        reasons.append("Insufficient measured requests")
    if metadata["generator_cpu_warning"]:
        reasons.append("Generator CPU warning: repeat with separate or larger generators")
    if total["error_ratio"] is not None and total["error_ratio"] > thresholds["max_error_ratio"]:
        reasons.append("Total error ratio exceeds threshold")
    for name in thresholds["required_routes"]:
        if name not in routes or routes[name]["requests"] < 5:
            reasons.append(f"Insufficient route samples: {name}")
    for name, metrics in routes.items():
        if metrics["p95_ms"] > thresholds["max_p95_ms"]:
            reasons.append(f"p95 exceeds threshold: {name}")
        if metrics["error_ratio"] > thresholds["max_error_ratio"]:
            reasons.append(f"Error ratio exceeds threshold: {name}")
    stages, lower = [], 0
    for stage in metadata["stages"]:
        samples = [r for r in rows if lower <= float(r["timestamp"]) - start < stage["until_seconds"]]
        stages.append({**stage, "from_seconds": lower, **summarize(samples, stage["until_seconds"] - lower)})
        lower = stage["until_seconds"]
    return {
        "metadata": metadata,
        "total": total,
        "routes": routes,
        "stages": stages,
        "gate": {"passed": not reasons, "reasons": reasons},
        "latency_method": "nearest-rank; requests started and completed within planned window; all outcomes",
    }
