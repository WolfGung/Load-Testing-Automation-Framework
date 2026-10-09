# Client handoff

A small engagement can deliver a versioned workload, a baseline report, a bottleneck diagnosis,
and a repeatable pipeline check. The client keeps plain Python scenarios and raw measurements.

1. Agree on a staging target, traffic model, critical operations, test data and cleanup. Separate
   the generator from the target when the result will inform a capacity decision.
2. Adapt `Shopper` to the API: authentication, identifiers from responses, expected totals/statuses,
   and route grouping. Add secrets through the environment, never recorded request headers.
3. Match think time, task weights, concurrency and duration to observed traffic. Validate with smoke first.
4. Define latency and error thresholds per critical operation. Extend sample counts and plateau duration
   until the tail metrics support the intended decision.
5. Record a baseline, inspect resource signals, and investigate the first degrading operation.
   Repeat after the proposed repair with the same workload and comparable hardware.
6. Deliver the HTML report, raw samples, environment metadata, findings and exact reproduction commands.
   Add correctness checks to ordinary CI and a controlled performance gate to dedicated infrastructure.

For a Guru portfolio entry:

> API load testing with Python and Locust. Stateful shopping journeys, smoke/load/stress/spike/soak profiles,
> response validation, per-operation latency and error gates, resource charts, and a measured catalogue repair.
> Includes a local stand, raw evidence, Docker and reproducible commands.

The demo's measured rate is not a capacity estimate for a client's API. A client report should state
what was measured, which environment was used, what was not exercised, and which finding needs another experiment.
