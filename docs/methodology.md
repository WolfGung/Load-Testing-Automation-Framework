# Measurement methodology

## The question and the tool

Can a catalogue remain responsive while customers also place orders? What changes after batching price requests?
Locust keeps the workload in Python, exposes stateful HTTP clients and response validation, and supports shaped concurrency.
The same language covers the stand, scenarios, analysis and checks, making the example easy to inspect and adapt.
See the official [HTTP user documentation](https://docs.locust.io/en/stable/writing-a-locustfile.html)
and [request event hooks](https://docs.locust.io/en/stable/extending-locust.html).

This portfolio values a complete experiment over a large collection of nearly identical scenarios.
A visible bottleneck and its diagnosis are useful evidence of testing skill. A high user count alone is not.
The dependency is explicitly simulated so the example needs no external service and has a clear causal hypothesis.

## Workload

One authenticated shopper class chooses browsing with weight four and a purchase with weight one.
Each purchase reads a product, creates a private cart, adds an item, checks out, retrieves the order and deletes the cart.
The task checks status codes and response content. A wrong price is a failed request even with HTTP 200.
Dynamic identifiers are grouped into stable route names. Authentication occurs once per spawned user.
Random task choices are deliberately not seeded across processes; repeated runs will vary.

Think time follows tasks. Stages set target user counts and spawn rates, excluding warm-up in stage times.
Warm-up uses the first stage's user target. Stage changes are checked by Locust approximately once per second;
ramping can take time. Native history CSV contains observed user counts. A stage target is not achieved concurrency.

This is a closed workload. Users wait for a response before issuing the next request.
As the server slows down, the offered request rate falls. This can conceal overload relative to a real arrival-rate workload.
Do not turn measured RPS into an unconditional capacity promise.

## Sampling window

`requests.csv` records the start timestamp, method, grouped route, elapsed milliseconds, failure flag and error text.
A request begun during warm-up is excluded even if it ends in the plateau.
The analyzer also excludes requests ending after the planned measurement window.
The raw CSV retains completions drained after the window, up to the configured stop timeout.
Requests still unfinished when the runner stops are absent. Window-edge censoring can bias percentiles downward.
A longer stable plateau reduces that influence.

Duration for RPS is the configured measured window, not process lifetime or drain time.
Percentiles use nearest rank on completed requests, including failed responses. Errors are reported independently.
Both total and per-operation p50, p95, p99 and error counts are available.
Stages group by request start time. Stage p95 combines operations; inspect per-operation metrics for critical paths.
Native Locust CSV and HTML include warm-up and may use rounded latency histograms; they need not match the custom table.

## Thresholds and validity

The profile files contain illustrative thresholds. They require enough samples, critical route coverage,
small error ratios and a maximum p95 for each route. These are examples of a release gate, not customer SLOs.
A generator CPU warning makes the gate fail: a limited generator cannot establish server capacity.
The minimum route count prevents a quiet or incomplete run from looking successful.
A small sample is still insufficient for a stable tail estimate; report sample size alongside p99.

Main CI checks functionality and sufficient workload coverage. Timing remains report-only there because
shared runner performance varies. The separate performance workflow records the verdict without a schedule.
Use `--gate` for a dedicated, stable benchmark environment when thresholds have been agreed.

## Server signals

`metrics.csv` samples the shop approximately once per second. It includes process RSS, process CPU percentage,
active pool calls, waiters, timeouts, cumulative calls and wait seconds, cart/order counts and database size.
CPU is process CPU, not whole-host utilization. Metrics endpoint calls consume a small amount of server work.
Pool counters and the final snapshot include warm-up; request percentiles exclude it.

The pool has eight slots, each call has 10 ms of simulated I/O and a 100 ms acquisition timeout.
The broken catalogue uses one call per product; fixed uses one batch. Nothing is cached.
Both still perform real HTTP, parsing, validation and SQLite writes. SQLite uses one process and local disk.

Orders accumulate for the run, while carts are cleaned after each purchase. Rising database size is therefore expected.
A soak chart can reveal drift; a five-minute demonstration cannot prove absence of leaks or long-term stability.

## Reproducibility and limits

Each automatic run owns its server, loopback port and temporary database, and tears them down on exit.
Package versions are pinned in requirements.lock. Metadata records Python, Locust, platform, worker count,
profile, think time, thresholds, start/finish timestamps and generator CPU warning state.
Broken and fixed run sequentially on the same host, with fresh databases. They share hardware with the generator.
One pair does not establish a confidence interval; thermal load, disk and background processes can move the result.
For client conclusions, repeat in alternating order, retain all runs, separate generators from the target,
monitor host saturation and model real dependencies and arrival rates.
