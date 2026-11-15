# The Brightway installer

This folder writes BAFU's inventory into Brightway: three databases and the 25 EF 3.1 impact
methods. The build of this repository runs it (`scripts/build_release.py`, step 7), and you can
run it on its own.

It is the code of [sentier-brightway](https://github.com/sentier-dev/sentier-brightway) by
Laurenz Bougan, moved here on 15 November 2026 with its history, at commit `90d57eb`. The
package keeps its name, `sentier_brightway`, and its command, `sentier-brightway`. It has its
own environment (Python 3.12, pandas, bw2data), its own lock and its own lint settings, apart
from the patch tool's.

## What it does

| Command | What it does |
|---|---|
| `sentier-brightway coverage` | Prints how many of the inventory's elementary flows are linked, without Brightway. |
| `sentier-brightway db --project NAME` | Writes the databases and the methods into a Brightway project. |
| `sentier-brightway files --out FOLDER` | Writes the same build as parquet tables and bw_processing datapackages. |
| `sentier-brightway backtest --out FOLDER --xlsx FILE` | Scores every dataset and compares with BAFU's published LCIA results. The workbook is not in this repository. |

Run them from this folder with `uv run`, or from the repository's root:

```sh
uv run --frozen --project brightway-installer --python 3.12 --extra testing sentier-brightway coverage
```

Without `--data-root` it downloads the inventory, the flow terms, the methods and the mapping
at the commits in `src/sentier_brightway/sources.toml` and checks each file's SHA-256.
`scripts/pin_sources.py` writes that file again when a pin moves.

## What it writes

- `ef-3.1-biosphere`: one node for each flow of EF 3.1, and for each flow a link ends on.
- `<source>`: the inventory, named after its source (`bafu-2026` for BAFU's release).
- `<source>-residual`: the source's elementary flows that are not linked, without a factor.
- The methods `("sentier", "EF v3.1", <category>)`, with the factors that have no location.

## How elementary flows are linked

- **By default**, through the mapping folder `bafu-2026-v1__ef-3.1` of sentier-mappings: each
  BAFU flow goes to the EF 3.1 flow the mapping names, with the mapping's conversion factor.
- **With `--flow-links FILE`**, through Brightway Flows, with the links of patch 0010
  (`brightway_flows.py`). An amount is converted only where Brightway Flows states the
  conversion, and a flow outside EF 3.1 takes the factors of the one flow Brightway Flows
  names as their source, where the two are counted in one unit. The file is
  `scripts/release_build/brightway-flows-targets-bafu-2026-v1.csv`; `docs/brightway-build.md`
  says what this linking changes.

Two more options serve the build: `--flow-terms-of SOURCE` reads the elementary flow terms of
another source than the inventory's own (a patched copy of a release has its own name and the
release's flows), and `--report FILE` writes the linking report as JSON.

## Check a change

```sh
uv run --frozen --project brightway-installer --python 3.12 --extra testing --extra dev ruff check brightway-installer
uv run --frozen --project brightway-installer --python 3.12 --extra testing --extra dev ruff format --check brightway-installer
uv run --frozen --project brightway-installer --python 3.12 --extra testing --extra dev pytest brightway-installer
```

The tests build a made-up data root. They need none of BAFU's data and download nothing. The
checks of every pull request run these three commands.

## What it does not do

- Only factors without a location are installed, so country-specific factors (water use, for
  example) are not. Only EF 3.1.
- Uncertainty is carried into the Brightway database, not into the files export.
- The files export names the pins of `sources.toml` in its manifest even when `--data-root`
  supplies other data. The build's own record, `build.json`, holds the pins that were used.

## Licence and credit

MIT, © 2026 Départ de Sentier (`LICENSE` in this folder). BAFU's inventory is under BAFU's
Terms of Use, not under this licence; the installer prints the credit BAFU asks for.
