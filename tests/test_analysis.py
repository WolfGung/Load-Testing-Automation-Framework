import csv
from pathlib import Path

import pytest

from loadtest.config import Profile
from tools.analyze import analyze, percentile


@pytest.mark.parametrize("name", [p.stem for p in Path("profiles").glob("*.json")])
def test_profile_boundaries(name):
    profile = Profile.read(name)
    assert profile.users_at(0) == profile.stages[0]["users"]
    assert profile.users_at(profile.duration) is None
    assert profile.users_at(profile.duration - 0.001) == profile.stages[-1]["users"]


def test_nearest_rank_and_no_samples():
    assert percentile(list(range(1, 101)), 0.95) == 95
    assert percentile([1, 2, 99], 0.95) == 99
    assert percentile([], 0.95) is None


def test_route_gate_catches_slow_checkout_hidden_by_aggregate(tmp_path):
    rows = [[10, "GET", "/products", 1, 0, ""] for _ in range(100)]
    rows += [[11, "POST", "/checkout", 800, 0, ""] for _ in range(5)]
    with (tmp_path / "requests.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp", "method", "route", "latency_ms", "failed", "error"])
        writer.writerows(rows)
    meta = {
        "measurement_start": 10,
        "finished": 20,
        "generator_cpu_warning": False,
        "stages": [{"until_seconds": 10, "users": 20}],
        "thresholds": {
            "min_requests": 30,
            "max_error_ratio": 0.01,
            "max_p95_ms": 500,
            "required_routes": ["POST /checkout"],
        },
    }
    result = analyze(tmp_path, meta)
    assert result["total"]["p95_ms"] == 1
    assert not result["gate"]["passed"]
    assert result["gate"]["reasons"] == ["p95 exceeds threshold: POST /checkout"]


def test_empty_run_fails_instead_of_reporting_success(tmp_path):
    (tmp_path / "requests.csv").write_text("timestamp,method,route,latency_ms,failed,error\n")
    meta = {
        "measurement_start": 10,
        "finished": 20,
        "generator_cpu_warning": False,
        "stages": [{"until_seconds": 10, "users": 2}],
        "thresholds": {
            "min_requests": 30,
            "max_error_ratio": 0.01,
            "max_p95_ms": 500,
            "required_routes": ["GET /products"],
        },
    }
    result = analyze(tmp_path, meta)
    assert not result["gate"]["passed"]
    assert result["total"]["p95_ms"] is None


def test_window_excludes_warmup_and_drained_completions(tmp_path):
    with (tmp_path / "requests.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["timestamp", "method", "route", "latency_ms", "failed", "error"])
        writer.writerows(
            [
                [9, "GET", "/products", 1500, 0, ""],
                [11, "GET", "/products", 100, 0, ""],
                [19.9, "GET", "/products", 300, 0, ""],
            ]
        )
    meta = {
        "measurement_start": 10,
        "finished": 21,
        "generator_cpu_warning": False,
        "stages": [{"until_seconds": 10, "users": 2}],
        "thresholds": {"min_requests": 1, "max_error_ratio": 0.01, "max_p95_ms": 500, "required_routes": []},
    }
    result = analyze(tmp_path, meta)
    assert result["total"]["requests"] == 1
    assert result["total"]["rps"] == 0.1
    assert result["total"]["p95_ms"] == 100
    meta["finished"] = 12
    assert "Incomplete measurement window" in analyze(tmp_path, meta)["gate"]["reasons"]
    meta["generator_cpu_warning"] = True
    assert any("Generator CPU" in reason for reason in analyze(tmp_path, meta)["gate"]["reasons"])
