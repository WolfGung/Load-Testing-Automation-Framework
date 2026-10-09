# Catalogue bottleneck: hypothesis, evidence, repair

## Trigger

Several shoppers browse the catalogue while others order a product.
The catalogue returns identical data in both implementations. The broken version makes a separate price request
for every displayed product. All calls contend for a bounded dependency pool shared with checkout.

The hypothesis is that batching catalogue prices reduces dependency work per page and therefore waiting under concurrency.
Correctness checks first confirm identical prices, isolated carts, accurate checkout totals and concurrent idempotency.

## Experiment

`make compare` starts the broken shop, runs the comparison profile, shuts it down, and repeats for fixed.
Both use a fresh SQLite database, identical dependency settings, the same task weights and think time, and one app worker.
All requests go over real HTTP. The price dependency is simulated I/O; no third-party service is involved.
The committed result is one measured local pair. The exact profile, thresholds and environment are saved with it.

Read [the generated README table](../README.md) and [comparison.json](../measurements/comparison.json).
The table uses raw request metrics; the source CSV and pool samples are stored beside each mode's summary.
`python -m tools.reproduce` verifies the saved request metrics directly from those raw files.

## Findings

The broken catalogue exceeds the configured p95 threshold. The fixed catalogue meets it in this pair.
Pool samples show the repeated dependency work in broken mode. Total dependency-call counts include warm-up,
so compare them with the same full-run configuration rather than dividing them by measured request counts.

Checkout is read separately because catalogue traffic can contend with it for pool slots.
The comparison workload does not produce request errors in either mode. Do not describe this pair as an error-rate improvement.
The stress and spike profiles use higher concurrency to investigate rejection and recovery.
Their reports must be reviewed from actual runs; a configured user count is not evidence of capacity.

## Repair

`GET /products` changes from sequential `prices.fetch([id])` calls to `prices.fetch(ids)` once per catalogue page.
It does not alter pool size, simulated downstream latency, timeout, returned prices or checkout behavior.
The functional test checks both output and dependency calls, tying the change to the causal hypothesis.

## Interpretation limits

Higher completed RPS after repair is expected under a closed workload: users wait less before issuing more work.
It is not proof of the maximum rate this API can sustain. A real price service may have batch-size costs,
network overhead, cache behavior and different limits from this model.
Generator and server share a machine. The report flags a generator CPU warning, but CPU headroom alone
cannot rule out generator, network or disk limits. Longer plateaus, repeated pairs and separate hardware
are needed for a client capacity conclusion.
