# Load test plan

| Profile | Question | Evidence | Decision |
| --- | --- | --- | --- |
| Smoke | Can every critical flow run with valid data? | Response checks, request failures, route sample counts | Fix correctness before adding load |
| Load | Do critical operations meet agreed thresholds at expected concurrency? | Per-operation p95, error ratio, observed users | Compare the plateau with the baseline |
| Stress | When does service quality first degrade? | Stage latency/errors, waiting calls, pool timeouts | Report the first violating stage and generator limits |
| Spike | Can the service recover after a sudden burst? | Initial and recovery stages, pool queue drain | Look for recovery, not only peak latency |
| Soak | Do latency and resources drift at sustained load? | RSS, CPU, database size, order growth, errors | Separate expected retention from unexplained growth |
| Comparison | Does the proposed repair address the measured bottleneck? | Identical profiles, fresh stands, raw evidence | Correlate fewer dependency calls with catalogue latency |

All data is synthetic. No external shop is required. Default automatic commands start a fresh local stand.
The acceptance thresholds are illustrative and versioned with the workload.
These profiles demonstrate distinct questions; they do not claim exhaustive performance coverage.

Before a client run, establish expected traffic, peak traffic, the critical user journey, write cleanup,
allowed duration and concurrency, dependencies, environment similarity and acceptance thresholds.
A user target is not an RPS target. Derive task mix from traffic evidence rather than copying this demo.

The experiment assumes batching reduces pool occupancy per catalogue response. Verify correctness first:
both modes must return the same prices, carts must be isolated, and concurrent idempotent checkout must create one order.
Then inspect pool samples beside latency and confirm the generator did not saturate.
