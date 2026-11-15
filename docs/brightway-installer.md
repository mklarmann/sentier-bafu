# The Brightway installer

The installer writes BAFU's inventory into Brightway: three databases and the 25 EF 3.1 impact
methods. The build of this repository runs it (`scripts/build_release.py`, step 7), and you can
run it on its own.

It is the second package of this repository's project, beside the patch tool:

| | Patch tool | Brightway installer |
|---|---|---|
| Package | `src/bafu_community_fixes` | `src/sentier_brightway` |
| Command | `bafu-fixes` | `sentier-brightway` |
| Needs | the project's dependencies | the same, and the `brightway` extra (pandas, bw2calc, bw2data and others) |
| Tests | `tests/` | `installer-tests/` |

The two share one `pyproject.toml`, one lock (`uv.lock`), Python 3.14 and one set of lint
rules. The patch tool runs without the extra.

The code is that of [sentier-brightway](https://github.com/sentier-dev/sentier-brightway) by
Laurenz Bougan. It was moved here on 15 November 2026 with its history, at commit `90d57eb`,
and keeps its package name and its command. [Its changelog](brightway-installer-changelog.md)
says what changed since.

## What it does

| Command | What it does |
|---|---|
| `sentier-brightway coverage` | Prints how many of the inventory's elementary flows are linked, without Brightway. |
| `sentier-brightway db --project NAME` | Writes the databases and the methods into a Brightway project. |
| `sentier-brightway files --out FOLDER` | Writes the same build as parquet tables and bw_processing datapackages. |
| `sentier-brightway backtest --out FOLDER --xlsx FILE` | Scores every dataset and compares with BAFU's published LCIA results. The workbook is not in this repository. |

Run them from a checkout of this repository:

```sh
uv run --extra brightway sentier-brightway coverage
```

Without `--data-root` the installer downloads the inventory, the flow terms, the methods and
the mapping at the commits in `src/sentier_brightway/sources.toml` and checks each file's
SHA-256. That file is the one place a data pin lives: the build reads the same commits.
`scripts/pin_sources.py` writes it again when a pin moves.

## What it writes

- `ef-3.1-biosphere`: one node for each flow of EF 3.1, and for each flow a link ends on. A
  flow in one country (`Water, CH`) has a node of its own, with the country as its location.
- `<source>`: the inventory, named after its source (`bafu-2026` for BAFU's release).
- `<source>-residual`: the source's elementary flows that are not linked, without a factor.
- The methods `("sentier", "EF v3.1", <category>)`: the factors that have no location, and
  for the flows of one country that country's factor.

## How elementary flows are linked

- **By default**, through the mapping folder `bafu-2026-v1__ef-3.1` of sentier-mappings: each
  BAFU flow goes to the EF 3.1 flow the mapping names, with the mapping's conversion factor.
- **With `--flow-links FILE`**, through Brightway Flows, with the links of patch 0010
  (`brightway_flows.py`). An amount is converted only where Brightway Flows states the
  conversion, and a flow outside EF 3.1 takes the factors of the one flow Brightway Flows
  names as their source. [The build's page](brightway-build.md) says what that changes.

**A flow that names a country** takes that country's factor in the methods that have one,
under either linking (`located.py`). BAFU has 238 such flows, `Water, CH` among them, and
the mapping states the country of each. `--skip-located` gives them the factor without a
location, as before 15 November 2026.

Two more options serve the build: `--flow-terms-of SOURCE` reads the elementary flow terms of
another source than the inventory's own (a patched copy of a release has its own name and the
release's flows), and `--report FILE` writes the linking report as JSON.

## Check a change

```sh
uv sync --locked --extra brightway
uv run --no-sync pytest installer-tests
```

The tests build a made-up data root. They need none of BAFU's data and download nothing. Lint
and formatting are the project's (`uv run ruff check`, `uv run ruff format --check`). The
checks of every pull request run all of these.

## What it does not do

- Only EF 3.1. A flow that names no country takes the factor without a location, whatever
  the location of its dataset: BAFU's exchanges carry no location of their own.
- Uncertainty is carried into the Brightway database, not into the files export.
- The comparison with BAFU's published results uses pypardiso for its solve where that
  package is installed, and SciPy's SuperLU otherwise. The project's lock does not hold
  pypardiso.

## Licence and credit

MIT, © 2026 Départ de Sentier (`src/sentier_brightway/LICENSE`). BAFU's inventory is under
BAFU's Terms of Use, not under this licence; the installer prints the credit BAFU asks for.
