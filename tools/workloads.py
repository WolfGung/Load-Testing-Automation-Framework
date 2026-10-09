"""Render the saved profile measurements and validate their raw request evidence."""

import json
from pathlib import Path

from tools.analyze import analyze
from tools.report import fmt

NAMES = ("smoke", "load", "stress", "spike", "soak")


def render(root=Path("measurements/workloads")):
    lines = [
        "| Profile | Mode | Measured requests | Successful RPS | Failed requests % | Gate |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for name in NAMES:
        directory = root / name
        saved = json.loads((directory / "summary.json").read_text())
        computed = analyze(directory, saved["metadata"])
        for key in ("total", "routes", "stages", "gate", "latency_method"):
            if saved[key] != computed[key]:
                raise ValueError(f"{name}: raw evidence differs from summary: {key}")
        totals = saved["total"]
        verdict = "PASS" if saved["gate"]["passed"] else "FAIL"
        lines.append(
            f"| {name} | {saved['metadata']['mode']} | {totals['requests']} | "
            f"{fmt(totals['successful_rps'])} | {fmt(totals['error_ratio'] * 100)} | {verdict} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render())
