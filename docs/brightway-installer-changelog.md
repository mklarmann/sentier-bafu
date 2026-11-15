# Changelog of the Brightway installer

## In sentier-bafu (from 15 November 2026)

The package was moved into sentier-dev/sentier-bafu at commit `90d57eb`, with its history.
It first lived in a folder of its own (`brightway-installer/`, with its own project file,
lock and Python 3.12 environment) and is now the second package of the repository's one
project: `src/sentier_brightway`, with its tests in `installer-tests/`. Since the move:

- One project with the patch tool: one `pyproject.toml`, one lock, Python 3.14. The
  installer's dependencies are the project's `brightway` extra, which now includes bw2data.
  The lock keeps the versions the installer's own lock had for NumPy, SciPy, pandas, bw2calc,
  bw2data and bw_processing. The `fast` extra (pypardiso) is gone; the comparison still uses
  pypardiso where it is installed.
- The code follows the project's lint rules (ruff with `E`, `F`, `I`, `UP`, `B`, `SIM`,
  lines of 100). Every `zip` over columns of one table is strict; the one over the two
  header rows of BAFU's workbook is not, and says why.
- `sources.toml` pins sentier-mappings at `179aab3`, the commit the build used. The build no
  longer moves a data pin of its own, so the installer run on its own and the build read
  the same files.
- The version is the distribution's (`bafu-community-fixes`). Importing the package without
  the `brightway` extra says which extra is missing.

- Removed, because the build of sentier-bafu does not use them: the export of flow lists
  (`flow_lists.py`, `flow_lists_output.py`, `scripts/export_flow_lists.py`), the dashboard
  viewer (`dashboard/`) with `as_js_cats`, and the folder's own CI workflow and pre-commit
  configuration. The backtest and everything it writes stay.
- Lint and formatting with ruff alone (black and isort are gone; ruff's formatter leaves the
  files as they were). The checks of sentier-bafu run lint, formatting and the tests on
  every pull request.
- `--flow-links FILE` on `db`, `files`, `coverage` and `backtest`: link the elementary flows
  through Brightway Flows, with the links of patch 0010 (`brightway_flows.py`).
- `--flow-terms-of SOURCE` on the same commands: read the elementary flow terms of another
  source than the inventory's own.
- `--report FILE` on `db`, `files` and `coverage`: the linking report as JSON.
- The manifest of a files export and the coverage say how the flows were linked (`linking`).

## 0.1.0 (unreleased)

- sentier-vocab term layer (sentier-vocab#34): elementary flows are read from
  `terms/<release>[-NN].parquet`, filtered on `type == "elementary-flow"`, with compartment,
  sub-compartment and CAS number taken from the JSON `attributes` column. `sources.toml` pins
  the term files of the `ef-3.1` and `bafu-2026` releases instead of the seventeen
  `data/elementary-flows/` shards; the flows and the coverage are unchanged.
- sentier-inventory layout 0.3.0: one folder per source release (`data/<source>-<version>/`)
  with `sector` as a process column. `load_inventory(root, source, source_version=None)` picks
  the folder from its `metadata.json` (errors list the source/version pairs present; two
  releases of one source need `source_version`); `Inventory.sectors` and `source_version` come
  from the metadata, the `sector` column stays on the frame and on every process node.
  `source_version=` on `assemble` / `coverage` / `import_db` / `import_files` and their
  `import_bafu_*` wrappers, `--source-version` on every CLI command. `sources.toml` pins the
  three files of `data/bafu-2026-v1/` instead of thirty-three sector files.
- README opens with an architecture schema (Mermaid): Activity Browser, the two importers, the
  three Sentier data repositories they pull from, and the backtest against BAFU's openLCA results.
- Backtest module (`sentier_brightway.backtest`) and `sentier-brightway backtest` CLI: all
  11,947 processes x 25 EF 3.1 categories from the file-mode datapackages by adjoint solve,
  cross-checked against the plain bw2calc loop, compared with BAFU's published openLCA
  results per the table's unit.
- Dashboard (`dashboard/backtest_dashboard.html`, a copy of the sentier-agribalyse-4.0 page
  with 25 categories) fed by the backtest's CSV and meta files.
- Dashboard v2: box-plot main view (25 categories, symmetric-log axis, quartile boxes, 1.5 IQR
  whiskers, outlier dots), a sector facet, a per-category worst-200 drill-down and a lazily
  loaded per-process detail panel. `backtest` now also writes `boxes.json` and `worst/`; the
  summary gains quartile columns. The heatmap table, the Emissions view and the Distributions
  view are removed.
- bw2calc and openpyxl are now hard dependencies; the `fast` extra adds pypardiso.
- Parity script `scripts/parity_bafu_lcia.py` removed; the backtest supersedes it.
- bw2data mode: `import_bafu_db()` / `sentier-brightway db` installs BAFU-2026 v1, an EF 3.1
  biosphere and the 25 EF 3.1 methods into a Brightway project, relinked through the
  sentier-mappings bridge.
- File mode: `import_bafu_files()` / `sentier-brightway files` writes the same build as a
  parquet registry, the applied randonneur packages and bw_processing datapackages for
  bw2calc without bw2data. `--overwrite` only ever replaces a previous export.
- Pinned, sha256-verified data manifest (`sources.toml`), downloaded on first use; no data in
  the wheel.
- Coverage report (`sentier-brightway coverage`) with the BAFU citation.
