"""Build a standalone report from measured files, without third-party scripts or assets."""

import argparse
import csv
import html
import json
import shutil
from pathlib import Path


def fmt(value, decimals=1):
    return "—" if value is None else f"{value:,.{decimals}f}"


def readme_table(comparison):
    lines = ["| Measured operation | Broken | Fixed |", "| --- | ---: | ---: |"]
    broken, fixed = comparison["runs"]
    metrics = [
        ("Catalogue p95 (ms)", lambda r: r["routes"].get("GET /products", {}).get("p95_ms")),
        ("Checkout p95 (ms)", lambda r: r["routes"].get("POST /carts/[id]/checkout", {}).get("p95_ms")),
        ("Completed requests / second", lambda r: r["total"]["rps"]),
        ("Failed requests (%)", lambda r: (r["total"]["error_ratio"] or 0) * 100),
        ("Price-service calls (whole run)", lambda r: r["server_final"]["price_calls"]),
    ]
    for label, getter in metrics:
        lines.append(f"| {label} | {fmt(getter(broken))} | {fmt(getter(fixed))} |")
    meta = fixed["metadata"]
    lines += [
        "",
        f"Measured locally with Python {meta['python']} and Locust {meta['locust']}. "
        f"The `{meta['profile']}` profile excludes {meta['warmup_seconds']:g} seconds of warm-up. "
        "Both processes share one host; these are demo measurements, not production capacity.",
        "Reproduce: `make compare`. Source: [measurements/comparison.json](measurements/comparison.json).",
    ]
    return "\n".join(lines)


def table(headers, rows):
    head = "".join(f'<th scope="col">{html.escape(str(h))}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def build(comparison, output, evidence=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sections = []
    chart_runs = []
    for run in comparison["runs"]:
        mode = run["metadata"]["mode"]
        reasons = run["gate"]["reasons"]
        routes = [
            [
                name,
                m["requests"],
                m["failures"],
                fmt(m["p50_ms"]),
                fmt(m["p95_ms"]),
                fmt(m["p99_ms"]),
                fmt(m["rps"]),
            ]
            for name, m in run["routes"].items()
        ]
        stages = [
            [
                f"{s['from_seconds']}–{s['until_seconds']} s",
                s["users"],
                s["requests"],
                fmt(s["p95_ms"]),
                fmt((s["error_ratio"] or 0) * 100),
            ]
            for s in run["stages"]
        ]
        links = ""
        source = (
            (Path(evidence[mode]) if isinstance(evidence, dict) else Path(evidence) / mode)
            if evidence
            else None
        )
        if source and source.is_dir():
            destination = output / "evidence" / mode
            shutil.copytree(source, destination, dirs_exist_ok=True)
            links = " · ".join(
                f'<a href="evidence/{mode}/{f}">{f}</a>'
                for f in ("requests.csv", "metrics.csv", "summary.json", "locust.html", "locust.log")
            )
        chart_data = []
        metrics = source / "metrics.csv" if source else None
        if metrics and metrics.exists():
            with metrics.open() as stream:
                chart_data = [
                    {
                        "seconds": float(r["timestamp"]) - run["metadata"]["measurement_start"],
                        "active": int(r["pool_active"]),
                        "waiting": int(r["pool_waiting"]),
                        "rss": float(r["rss_bytes"]) / 1024**2,
                        "cpu": float(r["cpu_percent"]),
                    }
                    for r in csv.DictReader(stream)
                ]
        chart_runs.append({"mode": mode, "metrics": chart_data})
        verdict = "Within configured thresholds" if run["gate"]["passed"] else "Thresholds exceeded"
        explanation = " · ".join(reasons) or "No configured threshold was exceeded in this measurement."
        sections.append(
            f'<section id="{mode}"><p class="eyebrow">{mode.upper()} IMPLEMENTATION</p>'
            f"<h2>{html.escape(verdict)}</h2><p>{html.escape(explanation)}</p>"
            + table(["Operation", "Requests", "Failures", "p50 ms", "p95 ms", "p99 ms", "RPS"], routes)
            + "<h3>Stages</h3>"
            + table(["Window", "Target users", "Requests", "p95 ms", "Errors %"], stages)
            + f'<p class="files">{links}</p></section>'
        )
    summary_rows = [
        [
            r["metadata"]["mode"],
            r["total"]["requests"],
            fmt(r["total"]["rps"]),
            fmt(r["routes"].get("GET /products", {}).get("p95_ms")),
            fmt((r["total"]["error_ratio"] or 0) * 100),
        ]
        for r in comparison["runs"]
    ]
    metadata = comparison["runs"][-1]["metadata"]
    template = (Path(__file__).with_name("report.html")).read_text()
    page = template.replace(
        "{{SUMMARY}}",
        table(["Implementation", "Requests", "RPS", "Catalogue p95 ms", "Errors %"], summary_rows),
    )
    page = page.replace("{{SECTIONS}}", "".join(sections))
    page = page.replace("{{PROFILE}}", html.escape(metadata["profile"]))
    page = page.replace("{{METADATA}}", html.escape(json.dumps(metadata, indent=2)))
    page = page.replace("{{CHART_DATA}}", json.dumps(chart_runs).replace("<", "\\u003c"))
    (output / "index.html").write_text(page)
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("site"))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    content = json.loads(args.input.read_text())
    evidence = args.evidence
    if "runs" not in content:
        evidence = {content["metadata"]["mode"]: args.input.parent}
        content = {"runs": [content]}
    build(content, args.out, evidence)


if __name__ == "__main__":
    main()
