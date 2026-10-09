"""CI checks correctness and sufficient evidence, leaving timing to the performance workflow."""

import json
import sys
from pathlib import Path


def verify(summary):
    if (
        summary["total"]["requests"] < 30
        or summary["total"]["failures"] != 0
        or summary["metadata"]["locust_exit_code"] != 0
    ):
        raise ValueError("Smoke workload has too few requests or request/content failures")
    for route in summary["metadata"]["thresholds"]["required_routes"]:
        if summary["routes"].get(route, {}).get("requests", 0) < 5:
            raise ValueError(f"Smoke workload did not exercise {route}")


if __name__ == "__main__":
    verify(json.loads(Path(sys.argv[1]).read_text()))
