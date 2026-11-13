# From a release to a Brightway database

This page maps the path from BAFU's release to a Brightway database with the EF 3.1 methods,
says where each tool reads and writes, and records what a full run measured on 13 November
2026. It covers the provider release (BAFU:2026 v1 as BAFU ships it) and the patched release
(the same release with the import fixes and community patches of this repository).

The path uses three tools that were written separately. It runs end to end, with one adapter
between the patch tool and the importer. It is not yet a complete build of the patched release:
four elementary flows that patch 0007 renames lose their EF 3.1 flow, and with them most of the
fossil resource score. The audit reports this as a finding. See
[What is missing](#what-is-missing).

**Which flow links the scores use.** Scores come through sentier-mappings, the route
sentier-brightway installs: each BAFU flow is relinked to the EF 3.1 flow the mapping names,
with the mapping's conversion factor. The Brightway Flows identifiers that patch 0010 writes
on every elementary exchange are identity links. They are not used for scores, and they are
never joined to a factor table keyed by EF 3.1 identifiers: many of them name flows outside
EF 3.1. The mapping is taken at sentier-mappings `179aab3`, one commit after
sentier-brightway's pin, because it corrects BAFU's `Chlorine` to air (high population).

## Run it

```sh
python3 scripts/build_release.py build path/to/bafu-2026-v1 output/provider --no-patches
python3 scripts/build_release.py build path/to/bafu-2026-v1 output/patched
python3 scripts/build_release.py compare output/provider output/patched --out output/comparison.json
```

`build` needs Python 3.12 or newer, `uv` and `git`. It clones sentier-importers and
sentier-brightway at the commits in `scripts/release_build/pins.toml` (or uses checkouts given
with `--tools`), runs each in its own `uv` environment, and writes everything under the output
folder. `build latest OUT` lets the patch tool download and check BAFU's release first.
`--pinned-data` lets several builds share one copy of the pinned flow terms, methods and
mapping. `--fail-on-findings` turns the audit's findings into a failed build, for a CI job.

The output folder holds BAFU's inventory as EcoSpold files, as tables and as a Brightway
database. It is under [BAFU's Terms of Use](terms-of-use.md): keep it local (`output/` is
ignored by git). A CI job may keep `build.json`, `audit/audit.json` and the comparison, which
hold counts, dataset codes, names and single scores. It must not upload the folder.

Tests: `python3 -m unittest discover -s release-build-tests`. They use synthetic data. Tests
that need pandas, SciPy or bw2data are skipped where those are missing; run them in the
sentier-brightway environment to run all but one, and in this package's environment to run
the one that checks the adapter against the patch tool's output.

## The chain

| Step | Tool | Reads | Writes |
|---|---|---|---|
| 1. patch | `bafu-fixes run` (this repository) | folder of EcoSpold 1 files | folder of EcoSpold 1 files with extensions, HTML report |
| 2. adapt | `scripts/release_build/adapter.py` | that folder | zip the importer can read, receipt |
| 3. import | `sentier-importers run bafu-processes`, `run bafu-exchanges` | zip at a fixed path below its data root | `processes.parquet`, `exchanges.parquet` |
| 4. data | `scripts/release_build/data_root.py` | sentier-brightway's pins | flow terms, methods and mapping, checked by SHA-256 |
| 5. install | `sentier-brightway db` | a data root with four folders | three Brightway databases, 25 methods |
| 6. audit | `scripts/release_build/audit_brightway.py` | the Brightway project | `audit.json`, `scores.csv` |

File and line references below are to sentier-importers at `28b28ed`, sentier-brightway at
`90d57eb` and this repository's package as merged with #40.

### 1. The patch tool

- `bafu-fixes run SOURCE DESTINATION` takes a file, a folder, or `latest`
  (`src/bafu_community_fixes/cli.py:22-64`). `latest` downloads
  `https://files.brightway.dev/bafu-2026-v1-ecospold.zip`, checks its SHA-256 and unpacks it
  into the user cache folder (`download.py:13-17`, `:69-81`). This is the only place the
  release is named.
- It parses each file and removes the EcoSpold namespace (`xml.py:136-148`), applies the 14
  import fixes, builds strict models, applies the patches in order, and writes each file again
  under the same name (`pipeline.py:234-290`, `xml.py:336-351`).
- Two things in the output matter to the next tool:
  - elements are written in the namespace `http://www.EcoInvent.org/EcoSpold01`
    (`xml.py:279-287`); BAFU's files have none;
  - the import fix `renumber-exchanges` gives every exchange that shares a number within its
    dataset a dummy number of 1,000,000,000 or more, and keeps the original in
    `bcf:extensions/bcf:exchange/@originalNumber` (`import_fixes.py:646`, `:683`).
- The import fix `location-codes` writes `EURwoCH` for `Europe without Switzerland`
  (`import_fixes.py:117-120`).
- Each dataset's extension block lists the import fixes and patches that changed it. There is
  no machine-readable list of the changed values; the HTML report keeps the complete list for
  the first ten datasets of each step (`changes.py:9-15`).

### 2. The adapter

sentier-importers reads BAFU's files as BAFU ships them:

- it looks for `<dataset>` without a namespace
  (`app/sentier_importers/sources/bafu/ecospold.py:196-199`). On the patched release as
  written it stops with `error: no <dataset> element in ecospold/process_….xml`;
- a dataset's identifier is the part of its file name after `process_` (`ecospold.py:205-213`);
- a technosphere input is linked by its exchange `number`, which is the supplying dataset's
  number (`sources/bafu/inventory_exchanges.py:33`, `:47-49`). A dummy number names no
  dataset.

`adapter.py` writes a copy of the release without the namespace, with the original numbers
restored and without the extension block, as a zip with sorted members and fixed dates (the
same input gives the same zip). It changes no name, amount, unit, compartment or location. The
copy is an intermediate file, not a release. The receipt lists, per dataset, the import fixes
and patches recorded on it.

### 3. The importer

- The registry hard-codes where the release is:
  `file://${SENTIER_DATA_ROOT}/sources/bafu-2026/BAFU-2026 v1_ecoSpold v1.zip`
  (`app/sentier_importers/registry.yaml:419`, `:431`). The build puts the adapter's zip there,
  below its own data root.
- `SOURCE_ID = "bafu-2026"`, `SOURCE_VERSION = "v1"` and the folder name `bafu-2026-v1` are
  constants (`ecospold.py:29-36`). Every dataset row gets them, so the importer cannot name a
  patched release differently.
- Exchange kinds: output group 0 is the product, group 4 is an elementary exchange, everything
  else is a technosphere exchange (`inventory_exchanges.py:18-23`).
- An elementary flow's identifier is a UUID version 5 of `name|category|subCategory|unit`
  (`ecospold.py:139-147`). A patch that changes one of those four changes the identifier.
  CAS numbers are not part of it.
- The folder's `metadata.json` is written only by `scripts/run_bafu_local.py`, which runs
  every `bafu*` source, including mapping sources whose inputs are not public
  (`scripts/run_bafu_local.py:130-137`). The build therefore calls the two inventory sources
  through the command line and writes `metadata.json` itself
  (`scripts/release_build/inventory_metadata.py`), with the same keys. For a patched release
  it adds `modified: true` and the patch run; the schema allows further keys.

### 4. The pinned data

sentier-brightway reads four folders below one data root (`constants.py:29-33`):
`sentier-inventory`, `sentier-vocab` (flow terms), `sentier-methods` and `sentier-mappings`.
Its `sources.toml` pins each file by commit and SHA-256. Without `--data-root` it downloads
them into its cache (`fetch.py:120-139`); with `--data-root` it reads local folders and checks
nothing. The build uses sentier-brightway's own reader to fetch and check the three folders
that are not the inventory (`fetch.py:92-113`), and puts the importer's output in the fourth.

`pins.toml` can move one of the three to another commit, with the SHA-256 of each file that
differs and a reason. It does so for sentier-mappings (see above). `build.json` lists the
commit of each data source and says whether sentier-brightway or this build pinned it.

Where BAFU is hard-coded in sentier-brightway: the default source `bafu-2026`
(`constants.py:9`), the mapping folder `bafu-2026-v1__ef-3.1` (`:18`), the methods folder
`01-ef-3.1` (`:20`) and the citation (`:23-27`). `--source` selects the inventory folder and
names the databases; the flow terms must carry the same source identifier (`flows.py:85-88`).

### 5. The install

- `load_inventory` picks the folder whose `metadata.json` names the source
  (`inventory.py:141-161`). `load_bridge` reads the mapping's `replace` entries in package
  order, first entry wins (`bridge.py:125-136`). `load_methods` reads the factors that have no
  location (`methods.py:80`), so country-specific factors, for water use for example, are not
  installed.
- Every exchange is linked while the nodes are built (`build.py:219-235`): the product to its
  own dataset, a technosphere input to the dataset its `flow` names, an elementary exchange to
  the EF 3.1 flow the mapping gives for its flow identifier, multiplied by the mapping's
  conversion factor. An elementary flow the mapping does not know is kept in a second database,
  `bafu-2026-residual`, without a factor.
- A technosphere input that names no dataset stops the build (`build.py:241-276`).
- `writer.write` writes `ef-3.1-biosphere`, `bafu-2026-residual` and `bafu-2026`, then the 25
  methods under `("sentier", "EF v3.1", …)` (`writer.py:45-69`, `:81-102`).
- `sentier-brightway files` writes the same build as parquet tables and bw_processing
  datapackages (`files.py:111-130`). `scripts/audit_registry.py` in this repository audits
  that export.

### What the backtest compares

`sentier-brightway backtest` scores every dataset in the 25 categories from the files export
with one transposed solve per category (`backtest/scorer.py:145-175`) and compares with BAFU's
LCIA results workbook, sheet `BAFU_2026 v1` (`backtest/reference.py:62-120`). Rows are joined
by dataset name and location (`backtest/compare.py:23`, `:191`); the workbook's
`RER without CH` is read as `Europe without Switzerland` (`:72`). The patched release writes
`EURwoCH`, so 26 datasets would not be joined until that alias is added. The build's audit
does not use the backtest.

### 6. The audit and the comparison

`audit_brightway.py` reads the Brightway project, not the files it was built from. It counts
datasets and exchanges by kind, looks for exchanges whose input does not exist, counts the
elementary exchanges that stayed without an EF 3.1 flow, and reports per method how many of the
flows in use carry a factor. A factor of zero counts as a factor.

Scores come from one factorisation of the technosphere matrix: one solve per sample dataset,
and one transposed solve per method for all datasets. The two must agree to 1e-6, every solve
is checked by its residual (1e-8, with refinement), and three sample scores are recomputed
with bw2calc's own `LCA`. Brightway stores amounts and factors as 32-bit floats, so scores are
exact to about seven digits. The solver is SciPy's SuperLU; UMFPACK is used where it is
installed (it has no binary package, so a CI job would have to build it).

The sample (`scripts/release_build/score_sample.json`) holds 28 dataset codes with broad
plausible ranges for EF 3.1 climate change. The ranges are general LCA knowledge, not BAFU's
results. A score outside its range is a finding to look at, not proof of an error.

`compare_builds.py` compares the importer's tables of two builds row by row (a row is a
dataset and an exchange position), attributes each changed row to a step recorded on that
dataset, and attributes each moved score to the changed datasets in its supply chain. It fails
if a changed row or a moved score has no explanation. The table of what each step may change
is in the script; a step that starts to change something else shows up as unexplained.

## What the runs of 13 November 2026 measured

Three full runs of both builds gave the same counts and scores. The numbers below are from the
last one, with the tools and data in `pins.toml`.

Both builds: 11,947 datasets; 11,947 production, 114,369 technosphere and 293,747 elementary
exchanges; no unlinked exchange; audit passed. The provider release's inventory tables equal
the ones sentier-inventory publishes at the commit sentier-brightway pins, row for row, so the
adapter changes nothing the importer reads.

### Rows

Of 420,063 exchange rows, 213 differ between the two builds, and every one is explained:

| Step | Rows | Datasets | What changes |
|---|---|---|---|
| patch 0001 | 3 | 3 | the amount of polyethylene disposal in three strawberry datasets |
| patch 0002 | 25 | 25 | the declared supplier location; the link does not change |
| patch 0007 | 129 | 117 | the name of an elementary flow, and with it the flow's identifier |
| patch 0008 | 25 | 25 | the compartment of `Carbon dioxide, in air`, and with it the identifier |
| import fix `location-codes` | 31 | 26 | `Europe without Switzerland` becomes `EURwoCH` (also on 26 datasets) |

Patches 0003 to 0006 and 0009 to 0011 change nothing the importer reads: CAS numbers and
extension attributes are not part of a flow's identifier, and the importer writes every
dataset as a unit process.

Patch 0002 does not change a link on this path, because the importer links by number: all
114,369 technosphere inputs are linked in both builds. What it changes is how many inputs
declare a location that differs from the linked dataset's: 37 in the provider release, 12 in
the patched release. A further 1,399 inputs declare no location in either.

### Elementary flows

| | Provider release | Patched release |
|---|---|---|
| BAFU flows in use | 2,679 | 2,677 |
| linked to an EF 3.1 flow | 2,566 | 2,560 |
| elementary exchanges on an EF 3.1 flow | 284,443 | 284,314 |
| elementary exchanges without one | 9,304 | 9,433 |
| flows that the pinned flow terms don't hold (audit finding) | 0 | 4 |

The 25 exchanges of patch 0008 stay linked: they move onto the main `Carbon dioxide, in air`
flow, which the mapping knows and which leads to the same EF 3.1 flow.

The 129 exchanges of patch 0007 lose their EF 3.1 flow. The renamed flows have new identifiers
that the mapping does not hold:

| Flow after the patch | Exchanges | EF 3.1 flow before | Method that loses a factor |
|---|---|---|---|
| `Gas, natural` | 115 | Natural Gas | Resource use, fossils |
| `Gas, mine, off-gas, process, coal mining` | 12 | Natural Gas | Resource use, fossils |
| `Wood, unspecified, standing` (two compartments) | 2 | Wood | none |

### Scores

- In 24 of the 25 methods, three datasets move: the strawberry datasets of patch 0001. For
  climate change they go from 383.2, 55.47 and 55.51 to 0.659, 0.783 and 0.829 kg CO2 eq per
  kg. The provider release's values are outside the sample's plausible range; the patched
  values are inside.
- In Resource use, fossils, 11,659 of 11,947 datasets move. All of them have a dataset with a
  renamed natural gas flow in their supply chain. `Natural gas, at production` (NO), for
  example, goes from 37.14 to 0.28 MJ. This is the lost link, not a correction: in the patched
  build the method no longer sees natural gas taken from the ground.
- No other score moves. Below the tolerance of 1e-6, the largest difference between two builds
  of the same release was 8e-12.
- sentier-brightway documents one score, 0.0320835 kg CO2 eq per kWh for
  `Electricity, low voltage, production CH, at grid`. Both builds reproduce it.

### The mapping commit

Moving the mapping from sentier-brightway's pin (`5ba4acd`) to `179aab3` changes one entry,
`Chlorine` to air (high population), used by 410 exchanges. On the provider release it moves
scores in the three freshwater ecotoxicity methods and in no other: by more than 1 % for 3
datasets in the total, 20 in the inorganics part and 1,120 in the organics part.

### Against BAFU's published results

`sentier-brightway backtest` was run on both builds against BAFU's corrected LCIA results
workbook (July 2026). Matching those results is not a goal; the comparison shows what changes.

| | Provider release | Patched release |
|---|---|---|
| datasets joined by name and location | 11,947 | 11,921 (26 are now `EURwoCH`) |
| climate change within 1 % | 99.98 % | 99.96 % |
| Resource use, fossils within 1 % | 97.75 % | 11.56 % |
| Resource use, fossils, median difference | −0.07 % | −22.78 % |

### Time and memory

Measured on one machine (Apple silicon, macOS) while other jobs were running, so the times
are upper bounds for that machine. Peak memory is the largest resident size of the step's
process tree. Last run, with the range over the three runs in brackets.

| Step | Provider release | Patched release |
|---|---|---|
| patch (`--xsd-check every-step`) | not run | 171 s (171 to 218), 1.56 GB |
| adapt | 12 s (12 to 18) | 11 s (11 to 18) |
| import | 14 s (14 to 26), 0.88 GB | 13 s (13 to 21), 0.89 GB |
| data (files already present) | 3 s | 1 s |
| install | 83 s (83 to 126), 1.44 GB | 85 s (83 to 98), 1.30 GB |
| audit | 12 s, 0.83 GB | 11 s, 0.82 GB |
| whole build | 124 s (124 to 194), 1.5 GB | 294 s (294 to 370), 1.6 GB |

The first `data` step downloads about 37 MB. The tools' environments take further time to
create on a fresh machine; that was not measured.

## What is missing

1. **The renamed flows need a mapping.** Three ways, each a decision for the maintainers:
   - sentier-importers learns the corrected names. Its energy contents and one alias are keyed
     by BAFU's original names (`sources/bafu/ef_units.py:160-163`,
     `matching/aliases.yaml:100`). Regenerating the matched package on the patched release
     today drops the entries for the renamed flows and adds none (measured: 628 entries, 633
     on the provider release, which reproduces the published package exactly). With the
     corrected names added, the mapping would need entries for both spellings.
   - The build links on the flow as BAFU declared it (the source observation) and keeps the
     corrected name as a label. This needs the original name, compartment and unit of each
     changed elementary exchange in the patched release, as `originalNumber` is kept today.
   - The build links through the Brightway Flows identifier that patch 0010 writes on every
     elementary exchange. This needs factors and unit conversions for those identifiers, which
     neither sentier-brightway nor patch 0010 carries today.
2. **A patched release has no name of its own in the database.** The importer writes
   `bafu-2026` and `v1` on every dataset, and sentier-brightway names the database after the
   source. The build names the Brightway project `bafu-2026-v1-patched` and marks the
   inventory folder as modified, but the database inside is still called `bafu-2026` and
   carries no record of the changes.
3. **The importer cannot read the patch tool's output.** The adapter bridges this. It would
   not be needed if the importer ignored the namespace and read `originalNumber`; a change of
   that kind to `ecospold.py` gave tables identical to the adapter's when tried.
4. **The importer writes no `metadata.json` from its command line**, and has no way to point
   at a release file other than the fixed path below its data root.
5. **The patch tool has no machine-readable list of changes.** The comparison attributes
   changed rows with a table of what each step may change, checked against the data on every
   run. A list of changed values per step and dataset would replace that table.
6. **sentier-brightway's export manifest names its own pins** even when `--data-root` supplies
   other data, so a files export of this build would misstate the inventory and the mapping
   commit. The build does not use the files export; `build.json` holds the pins that were used.
7. **The comparison with BAFU's published results is not part of the build.** It needs BAFU's
   workbook, and for a patched release the location alias `EURwoCH`.
8. **Only global factors are installed**, and only EF 3.1. Uncertainty is carried into the
   Brightway database but not into the files export.
