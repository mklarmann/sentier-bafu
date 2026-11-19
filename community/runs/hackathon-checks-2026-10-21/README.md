# Scripts for `hackathon-checks-2026-10-21.json`

Recovered unchanged from the run's working log on 26 October 2026 and re-run; outputs reproduce the record.

| Script | sha256 |
|---|---|
| `eval_forecast.py` | `03ca11acd5c50ae6d79f18eb02861e47cf3908413d8bd8dfa8dee4d6aef7e766` |
| `structural_checks.py` | `ec7c7cfadd022581186638851ed51f7f9b19350959319f6daada9d4422888f3b` |

## Invocations

```
python -I eval_forecast.py <pr-src> <pinned-inventory> <out.json>
python -I structural_checks.py <pr-src> <pinned-inventory> <inventory-main> <demo-values.parquet> <out.json>
```

## Inputs

- `<pr-src>`: `hackathon/bafu-copied-processes/src` of sentier-dev/sentier-models PR #2 at
  `a8c895d37b1ce5027733306eb95d60bb389cb31e`.
- `<pinned-inventory>`: `git archive` of sentier-dev/sentier-inventory at
  `c5aee155f0778f02e68a67fc766e23222a11686a`. Its `data` tree is
  `3490e90f2540dbb77fb0d9bfb0d849360c1d0027`. The manifest hash is
  `a3fb177509bff47dcf1f6c2e3bb72dace01e4d7100a905e2e60347f9807b1651`: the sha256 of the
  `shasum -a 256` lines for all 22 `data/**/*.parquet` files, sorted by path (LC_ALL=C).
- `<inventory-main>`: `git archive` of sentier-inventory `main` at
  `c28bcd53e3c65bf1928fe5d5a7b39de32a7c3115` (data tree `bf2927afed253c1d8e805593f827b0a33e2b33f2`).
  This was `main` on 21 October 2026 and still was on 26 October.
- `<demo-values.parquet>`: generated from the pinned inventory by the PR's own builder:
  `python -I <pr-src>/build_demo_schema_files.py --data-root <pinned-inventory> --sector 02-electricity --out <dir>`
  32,458 rows. The row count is the pin: a parquet file's sha256 moves with the writer's
  version. The 26 October output had sha256
  `1c1e664ac9dcb8f1e322dade56b0faa874087bef0c3461cd8e9e65fdf8d855f9`; on 14 November, pandas
  3.1.1 with a newer pyarrow wrote `a7da9d79…b96ea7`, with the same rows and the same counts
  from `structural_checks.py`.

## Environment (`venv-pulp3`, built with `uv`)

Python 3.12.12, pandas 3.0.6, numpy 2.5.4, pyarrow 26.0.0, pulp 3.3.2 (bundled CBC),
pycountry-convert 0.7.2, pycountry 26.2.16, python-dateutil 3.0.0, tzdata 2026.5.

The PR's requirements.txt says `pulp>=2.7`, which resolves to 4.1.0. The forecast code does not run under 4.1.0 (see `pin_deviation` in the record).

## Reproduced elsewhere

On 14 November 2026 both scripts were run again on the same pins on x86-64 Linux (pulp 3.3.2).
Every structural count and every forecast score matched, and so did the baseline, except the
block `sensitivity_aggregates_also_removed_from_training`: global MAE 0.0568 / F1 0.5941 and
regional 0.0538 / 0.5673 there, against 0.0588 / 0.6056 and 0.0553 / 0.5899 in the record.
That block depends on the solver build: CBC can break ties differently on another build or
platform. Its verdict does not change; the model stays below the baseline.

## Record fields the scripts do not produce

`zero_baseline_mae_printed` and `report_md_values` come from `forecast_superstructure.py` and REPORT.md. The `excess_rows` counts were computed separately. The per-member input sums in the forecast findings (ID 0.956 … TR 0.972) and the "2-34 rows" are also not part of either script's output.
