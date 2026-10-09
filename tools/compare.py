"""Measure both implementations with the same workload, then render the evidence."""

import argparse
import json
from pathlib import Path

from loadtest.config import Profile
from tools.report import build, readme_table
from tools.run import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", default="comparison")
    parser.add_argument("--update-readme", action="store_true")
    args = parser.parse_args()
    profile = Profile.read(args.profile)
    measurements = [run(mode, profile, args.out / mode) for mode in ("broken", "fixed")]
    comparison = {"runs": measurements}
    (args.out / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    build(comparison, args.out / "report", args.out)
    print(readme_table(comparison))
    if args.update_readme:
        path = Path("README.md")
        content = path.read_text()
        before, remainder = content.split("<!-- results:start -->", 1)
        _, after = remainder.split("<!-- results:end -->", 1)
        path.write_text(
            before + "<!-- results:start -->\n" + readme_table(comparison) + "\n<!-- results:end -->" + after
        )


if __name__ == "__main__":
    main()
