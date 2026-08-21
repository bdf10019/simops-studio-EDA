# Architecture

## Design goals

SimOps Studio separates project configuration, orchestration, solver integration, persistence,
AI prioritization, and presentation. A simulation adapter can change without changing the
queue, database, or reporting code; the AI model can fail safely without blocking simulation.

## Execution flow

1. `config.py` reads YAML/JSON, validates numeric bounds and worker capabilities, resolves
   paths, and creates a deterministic configuration hash.
2. `cases.py` computes the Cartesian product of sweep values. Each case receives a stable ID
   and input SHA-256.
3. `ai/risk.py` loads a trusted local model when present. Missing models use a deterministic
   heuristic; out-of-domain rows receive a neutral score.
4. `scheduler.py` orders cases by risk or FIFO, matches workers by adapter capability, writes
   attempts to SQLite, retries transient failures, and skips completed cases on resume.
5. An adapter returns frequency and impedance arrays. The shared result builder computes
   maxima, resonance proxy, violation fraction, and authoritative target-impedance decision.
6. `pcb/kicad.py` independently extracts focused board metadata and applies configured rules.
7. `reporting.py` exports portable artifacts. `dashboard.py` reads the same database without
   modifying it.

## Persistence model

SQLite uses foreign keys, WAL journaling, a 30-second busy timeout, parameterized SQL, and a
transaction per state transition.

| Table | Purpose | Important fields |
|---|---|---|
| `runs` | One configuration-derived execution | `run_id`, `config_hash`, `adapter`, `status`, timestamps |
| `cases` | Queue and retry state | `input_hash`, `priority`, `risk_score`, `worker`, `attempts`, error |
| `results` | Final simulation metrics | PASS/FAIL, impedance bounds, frequencies, complete JSON payload |
| `events` | Append-only operational audit | timestamp, level, optional case, message |

The first 12 characters of the configuration hash form the run ID. Running an unchanged
project resumes the same queue; changing a meaningful input creates a different run ID.
`--force` clears results for that run and dispatches every case again.

## Failure and trust boundaries

- Invalid configuration fails before database dispatch.
- A worker is selected only when its capability includes the chosen adapter.
- Every attempt and terminal/non-terminal error is persisted.
- AI controls queue order only; simulation output alone controls PASS/FAIL.
- External programs receive generated files in an isolated temporary directory. The adapter
  does not invoke a shell and enforces a timeout.
- Reports expose basenames and hashes rather than absolute project paths.
- The HTTP dashboard is read-only and accepts loopback binds only.

## Extension points

New solvers implement `SimulationAdapter.available()` and `SimulationAdapter.simulate()`.
Production expansion would normally add a remote worker protocol, migration-managed database,
authentication/authorization, signed model registry, structured telemetry, and native EDA DRC
result import while retaining the same configuration → queue → result contract.
