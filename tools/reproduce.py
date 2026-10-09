"""Recompute saved request metrics from raw CSV before rendering or updating documentation."""

import argparse
import json
from pathlib import Path

from tools.analyze import analyze
from tools.report import readme_table


def reproduce(directory):
    comparison = json.loads((directory / "comparison.json").read_text())
    for saved in comparison["runs"]:
        mode = saved["metadata"]["mode"]
        recomputed = analyze(directory / mode, saved["metadata"])
        for key in ("total", "routes", "stages", "gate", "latency_method"):
            if recomputed[key] != saved[key]:
                raise ValueError(f"Raw evidence differs from {mode} summary: {key}")
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("measurements"))
    parser.add_argument("--update-readme", action="store_true")
    args = parser.parse_args()
    content = readme_table(reproduce(args.directory))
    if args.update_readme:
        path = Path("README.md")
        before, remainder = path.read_text().split("<!-- results:start -->", 1)
        _, after = remainder.split("<!-- results:end -->", 1)
        path.write_text(before + "<!-- results:start -->\n" + content + "\n<!-- results:end -->" + after)
    print(content)


if __name__ == "__main__":
    main()
