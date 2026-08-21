# Limitations and next work

## Current engineering limits

- The built-in solver uses one idealized lumped RLC topology. It omits distributed planes,
  package/connector models, S-parameters, coupling, temperature, tolerances, and nonlinear
  behavior.
- The KiCad parser performs focused metadata/manufacturing checks only. It is not a complete
  S-expression implementation and cannot replace native DRC, stackup analysis, or extraction.
- Logical workers execute as local threads. There is no remote agent heartbeat, leasing,
  cancellation protocol, resource quota, or distributed lock.
- SQLite is appropriate for a local workbench, not a high-concurrency multi-user service.
- The dashboard has no authentication or TLS and deliberately accepts loopback binds only.
- The external adapter expects one CSV schema and a fixed 300-second timeout; production
  wrappers need tool-specific error mapping, cancellation, log retention, and license checks.

## AI limits

- The bundled model learns from 24 deterministic synthetic rows and evaluates on a six-row
  stratified holdout. Its perfect baseline score reflects the simple example boundary.
- Random splitting does not represent time, product family, topology, or process shifts.
- Range checks catch numeric extrapolation but not semantic topology or specification drift.
- Joblib model files must be treated as trusted executable artifacts; no signature or registry
  is implemented.
- Predictions only prioritize work. They cannot waive a simulation, change the engineering
  target, or produce a sign-off decision.

## Public-data decision

No external dataset is required for the first complete version because public PCB datasets
rarely provide the paired, licensed simulation setup and trustworthy SI/PI labels needed for
this workflow. The original synthetic board and deterministic labels keep the demo legal,
small, reviewable, and fully reproducible. A later data expansion should document provenance,
license, preprocessing, and leakage controls before any files enter Git.

## Production-oriented next steps

1. Add an authorized native-tool wrapper and golden-result comparison against a validated
   solver or measurement set.
2. Introduce schema migrations, PostgreSQL/queue-backed workers, leases, cancellation, and
   structured observability.
3. Add tolerance/Monte Carlo studies, stackup/model versioning, and result acceptance gates.
4. Evaluate by unseen product family or time split, add calibration/drift metrics, and sign
   trusted model artifacts.
5. Add authenticated role-based web access only if the dashboard moves beyond localhost.

These are explicitly future items; they are not represented as completed functionality.
