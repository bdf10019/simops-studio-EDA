# Simulation risk model card

## Intended use

The Random Forest classifier predicts the probability that a configured PDN parameter set
will exceed the target impedance. SimOps Studio uses the probability to prioritize the
simulation queue and provide an early risk preview.

## Prohibited interpretation

The prediction is not an electrical sign-off result. Only a completed simulator result can
produce the final PASS/FAIL decision. Inputs outside the training range receive a neutral
score of `0.5` instead of an extrapolated prediction.

## Training data

Training rows are generated from completed, deterministic simulations in the local SQLite
database. The bundled example produces a balanced synthetic parameter sweep. No external,
private, or production design data is included.

## Evaluation

Training records a deterministic stratified holdout accuracy, balanced accuracy, confusion
matrix, feature importance, class balance, library version, and training bounds. The model
is then refit on all validated rows for local use.

## Known limitations

- The example covers one lumped PDN topology and a bounded parameter range.
- Random train/test splitting does not represent a production time split.
- A topology, specification, solver, or parameter-range change requires retraining.
- A production deployment needs independent validation data and drift monitoring.

