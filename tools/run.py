"""Start an isolated stand, run Locust, collect diagnostics and evaluate the measured window."""

import argparse
import csv
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from loadtest.config import Profile
from tools.analyze import analyze
from tools.stand import ROOT, stand


def run(mode, profile, output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output is not empty: {output}; use a fresh directory")
    output.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()
    with (output / "server.log").open("w") as server_log, stand(mode, server_log) as url:

        def sample():
            with (
                httpx.Client(timeout=2, trust_env=False) as client,
                (output / "metrics.csv").open("w", newline="") as stream,
            ):
                writer = None
                while not stop.is_set():
                    try:
                        data = {"timestamp": time.time(), **client.get(url + "/metrics").json()}
                        if writer is None:
                            writer = csv.DictWriter(stream, fieldnames=list(data))
                            writer.writeheader()
                        writer.writerow(data)
                        stream.flush()
                    except (httpx.HTTPError, ValueError):
                        pass
                    stop.wait(1)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        env = {**os.environ, "LOAD_PROFILE": profile.name, "LOAD_OUTPUT": str(output)}
        command = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            "loadtest/locustfile.py",
            "--headless",
            "--host",
            url,
            "--stop-timeout",
            "5",
            "--csv",
            str(output / "locust"),
            "--csv-full-history",
            "--html",
            str(output / "locust.html"),
        ]
        try:
            with (output / "locust.log").open("w") as stream:
                result = subprocess.run(
                    command, cwd=ROOT, env=env, stdout=stream, stderr=stream, timeout=profile.duration + 45
                )
        finally:
            stop.set()
            sampler.join(timeout=3)
        if result.returncode not in (0, 1) or not (output / "run.json").is_file():
            raise RuntimeError(
                f"Locust execution failed ({result.returncode}); inspect {output / 'locust.log'}"
            )
        with httpx.Client(trust_env=False) as client:
            final_metrics = client.get(url + "/metrics").json()
    metadata = json.loads((output / "run.json").read_text())
    metadata.update(
        {
            "mode": mode,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "locust": importlib.metadata.version("locust"),
            "app_workers": 1,
            "generator_processes": 1,
            "same_host": True,
            "locust_exit_code": result.returncode,
        }
    )
    summary = analyze(output, metadata)
    summary["server_final"] = final_metrics
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"{mode}/{profile.name}: {summary['total']['requests']} requests, "
        f"gate {'PASS' if summary['gate']['passed'] else 'FAIL'}; {output}"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["broken", "fixed"], default="fixed")
    parser.add_argument(
        "--profile", choices=[p.stem for p in (ROOT / "profiles").glob("*.json")], default="smoke"
    )
    parser.add_argument("--out", type=Path, default=Path("results") / time.strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--gate", action="store_true", help="Exit 1 when measured thresholds fail")
    args = parser.parse_args()
    summary = run(args.mode, Profile.read(args.profile), args.out)
    if args.gate and not summary["gate"]["passed"]:
        print("\n".join(summary["gate"]["reasons"]))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
