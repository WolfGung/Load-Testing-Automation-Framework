# Load Testing Automation Framework

API load testing that identifies a catalogue bottleneck, measures its repair, and produces evidence a client can inspect.

[![CI](https://github.com/WolfGung/Load-Testing-Automation-Framework/actions/workflows/ci.yml/badge.svg?branch=main&event=push)](https://github.com/WolfGung/Load-Testing-Automation-Framework/actions/workflows/ci.yml)
[![Live report](https://img.shields.io/badge/live%20report-GitHub%20Pages-brightgreen)](https://wolfgung.github.io/Load-Testing-Automation-Framework/)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[Live measured report](https://wolfgung.github.io/Load-Testing-Automation-Framework/) · [Report preview](docs/report-preview.png) · [Raw evidence](measurements/)

<!-- results:start -->
| Measured operation | Broken | Fixed |
| --- | ---: | ---: |
| Catalogue p95 (ms) | 737.1 | 15.4 |
| Checkout p95 (ms) | 31.1 | 16.2 |
| Completed requests / second | 79.3 | 719.0 |
| Failed requests (%) | 0.0 | 0.0 |
| Price-service calls (whole run) | 13,594.0 | 7,625.0 |

Measured locally with Python 3.12.14 and Locust 2.46.7. The `comparison` profile excludes 3 seconds of warm-up. Both processes share one host; these are demo measurements, not production capacity.
Reproduce: `make compare`. Source: [measurements/comparison.json](measurements/comparison.json).
<!-- results:end -->

## What this shows

- **Find why an API slows down.** Correlate catalogue latency with downstream pool contention, then measure the same workflow after batching.
- **Test business flows under load.** Isolated sessions and carts, checkout totals, order retrieval, response validation, and cleanup.
- **Deliver usable evidence.** Per-operation percentiles, errors, stage summaries, resource charts, raw CSV, and an explicit performance gate.

## Try it

Use Python 3.12. Each run starts its own local shop and removes its database on exit.

```bash
python3.12 -m venv .venv
make install
make test
make smoke
make compare
```

`make compare` prints the before/after table and writes `results/comparison-<timestamp>/report/index.html`.
Open that file in a browser. The report includes interactive resource charts and links to raw evidence.
`make report` renders the committed measurement to `site/index.html` without running a load test.
The preview comes from this report. The live report is built from the committed measurement on each push to main.

The scripts refuse a nonempty output directory. Run outputs remain separate from the committed baseline.
All reported RPS and latency values come from real HTTP requests to the local stand.
The price service's I/O is deliberately simulated; this is a testing demonstration, not a production benchmark.

## Choose a workload

| Command | Purpose | Interpretation |
| --- | --- | --- |
| `make smoke` | Check the complete flow with a small workload | Fails on configured thresholds |
| `make load` | Ramp up and hold expected concurrency | Review the plateau and each critical operation |
| `MODE=broken make stress` | Increase concurrency past the bottleneck | Inspect the first stage with errors or excessive latency |
| `MODE=broken make spike` | Apply a burst, then return to low concurrency | Compare the recovery stage with the initial stage |
| `make soak` | Hold load for a short demonstration | Inspect latency, memory and database growth |
| `make compare` | Run broken and fixed with one profile | Compare identical configuration, with a fresh database per run |

[Saved workload results](docs/workload-results.md) include raw evidence for every profile.

Definitions and illustrative thresholds live in [profiles/](profiles/). They are not inferred from production traffic.
`loadtest/config.py` validates stage boundaries. Increase soak duration for a real endurance investigation.
Profiles set **concurrent users**, not arrival rate or RPS. Task weights are four browsing tasks to one purchase task;
a purchase makes several HTTP requests. Think time applies after each task, not each request.

Run a profile directly:

```bash
.venv/bin/python -m tools.run --profile load --mode fixed --out results/my-load --gate
.venv/bin/python -m tools.run --profile stress --mode broken --out results/my-stress
.venv/bin/python -m tools.report --input results/my-load/summary.json --out results/my-report
```

`--gate` returns a nonzero exit code on excessive per-route p95 or error ratio, missing critical routes,
insufficient samples, or Locust's generator CPU warning. A stress run can fail these thresholds as intended.
Without `--gate`, the verdict stays visible in the report and JSON without failing the command.
The performance workflow reports measurements; the main CI checks correctness without timing assertions.

## Inspect the shop and Locust

```bash
make app                         # shop: http://127.0.0.1:8120/docs
```

For the Locust UI, in another terminal:

```bash
LOAD_PROFILE=load LOAD_OUTPUT=results/manual .venv/bin/locust \
  -f loadtest/locustfile.py --host http://127.0.0.1:8120
```

Open <http://127.0.0.1:8089>, then start the shaped run. Finish the Locust process to flush `run.json`.
Native Locust HTML/CSV statistics include warm-up. The project summary applies its own documented measurement window.

With Docker, both services run in a dedicated Compose project:

```bash
mkdir -p results
docker compose up --build -d --wait
# API: http://127.0.0.1:8120/docs; Locust: http://127.0.0.1:8089
# Choose Start in the Locust UI.
docker compose down
```

`APP_MODE=broken LOAD_PROFILE=stress docker compose up --build -d --wait` selects the slow implementation.
The default commands load only this repository's own shop. To adapt it, change endpoint paths and response checks
for an agreed staging environment; agree on workload, test data, load limits and thresholds with the owner.

## How the bottleneck works

The catalogue returns a page of products. Both implementations use the same product data and prices.
The broken path fetches each price sequentially; the fixed path fetches the page in one batch.
The dependency holds one slot per call while waiting for simulated I/O. Pool contention is observable via `/metrics`.
Checkout uses the same pool, so catalogue traffic can delay a critical write flow.

[Diagnosis](docs/diagnosis.md) explains the measured result and its limits.
[Methodology](docs/methodology.md) defines the sampling window, percentiles, thresholds, workload and resource signals.
[Test plan](docs/test-plan.md) maps each profile to a question and an acceptance decision.

## Repository layout

```text
app/          local FastAPI shop, SQLite orders, bounded price dependency
loadtest/     Locust journeys, shapes, request capture, validated profile loader
profiles/     smoke, load, stress, spike, soak, and comparison definitions
tools/        isolated stand lifecycle, runner, analysis, comparison, HTML report
measurements/ measured baseline with raw requests, server samples and environment
tests/        correctness, isolation, concurrency, profile and evidence checks
docs/         methodology, diagnosis, test plan and client handoff
.github/      deterministic CI and manually triggered performance measurements
```

The app uses one worker and an in-process session store. It is a small test stand, not an application deployment template.
Each purchase owns a new cart. Checkout enforces an idempotency key and correct totals, and the task deletes its cart.
Orders remain until the run ends. Soak growth includes this deliberate retention policy.

## Reproduce the baseline

The first table is generated from [measurements/comparison.json](measurements/comparison.json).
It is pinned by a repository test. Latency is never typed into the README manually.

```bash
make compare
# After reviewing the new run, replace the baseline with its evidence directories
# and comparison.json, then update the README table from that JSON:
.venv/bin/python -m tools.reproduce --directory measurements --update-readme
make test
make report
```

`tools.reproduce` recalculates every request metric from raw CSV and checks the saved summary before rendering.
Numbers will differ across machines. Use repeated measurements on isolated hardware before describing a speedup as stable.
This baseline is one local pair. In-flight requests crossing the window end are excluded, which biases long-tail estimates;
use a longer plateau when that matters. No claim about production capacity follows from the table.

## CI and reports

[ci.yml](.github/workflows/ci.yml) runs on push and pull request. It checks lint, tests, baseline evidence,
and real HTTP journeys on a fresh local stand. It asserts request correctness and critical-route coverage.
It does not compare latency across runners. On `main`, it builds the committed report and deploys it via GitHub Pages.
Publishing requires a repository with Pages configured to use GitHub Actions.

[performance.yml](.github/workflows/performance.yml) runs only by manual dispatch. It collects workload evidence
as a downloadable artifact. It does not replace the committed baseline or the published report. There is no schedule.


## Adding this to a client pipeline

[Client handoff](docs/client-handoff.md) describes adapting journeys, choosing thresholds, running a baseline,
and delivering a bottleneck report with a repeatable pipeline check.

## Related work

- [Test Suite Rescue](https://github.com/WolfGung/Test-Suite-Rescue) — diagnose unstable tests and measure repairs.
- [Marketplace Test Automation](https://github.com/WolfGung/Marketplace-Test-Automation-Framework) — API and end-to-end checks against a local stand.
- [API Test Generator](https://github.com/WolfGung/API-Test-Generator) — turn OpenAPI or Postman documents into pytest suites.

Built by **Pavel Zhukov Atum**. [Hire me on Guru](https://www.guru.com/freelancers/pavel-zhukov-atum).
Central European Time (CET/CEST); working hours overlap with Central European business hours.
