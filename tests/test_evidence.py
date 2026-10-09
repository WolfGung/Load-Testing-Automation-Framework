import json
from pathlib import Path

from tools.report import build, readme_table


def test_readme_table_matches_committed_measurement():
    comparison = json.loads(Path("measurements/comparison.json").read_text())
    actual = Path("README.md").read_text().split("<!-- results:start -->")[1].split("<!-- results:end -->")[0]
    assert actual.strip() == readme_table(comparison)


def test_saved_report_is_standalone_and_contains_actual_routes(tmp_path):
    comparison = json.loads(Path("measurements/comparison.json").read_text())
    build(comparison, tmp_path)
    html = (tmp_path / "index.html").read_text()
    assert "{{" not in html
    assert "POST /carts/[id]/checkout" in html
    assert "<script src=" not in html
    assert json.loads((tmp_path / "comparison.json").read_text()) == comparison


def test_every_saved_request_metric_recomputes_from_raw_evidence():
    from tools.reproduce import reproduce

    reproduce(Path("measurements"))


def test_workload_results_recompute_from_raw_requests():
    from tools.workloads import render

    assert render() in Path("docs/workload-results.md").read_text()
