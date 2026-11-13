# From a release to a Brightway database

This page maps the path from BAFU's release to a Brightway database with the EF 3.1 methods,
says where each tool reads and writes, and records what full runs measured on 13 November
2026. It covers the provider release (BAFU:2026 v1 as BAFU ships it) and the patched release
(the same release with the import fixes and community patches of this repository).

The path uses three tools that were written separately. It runs end to end, with one adapter
between the patch tool and the importer. Both builds pass their audit. In the patched build
the scores of three datasets differ from the provider build, in every method: the strawberry
datasets that patch 0001 corrects.

**The two databases cannot be taken for one another.** The provider release is installed as
`bafu-2026`, BAFU's name. A patched release is installed as `bafu-2026-v1-patched`, and its
metadata carries the label "Modified Data", the patch ids and the import fix ids.

**Which flow links the scores use.** Scores come through sentier-mappings, the route
sentier-brightway installs: each BAFU flow is relinked to the EF 3.1 flow the mapping names,
with the mapping's conversion factor. Each elementary exchange is linked on the flow as BAFU
declared it. Where a patch corrects a flow's name or compartment, the corrected name becomes
the exchange's label and both are listed beside the data; the link does not change. The
Brightway Flows identifiers that patch 0010 writes on every elementary exchange are identity
links. They are not used for scores, and they are never joined to a factor table keyed by
EF 3.1 identifiers: many of them name flows outside EF 3.1. The mapping is taken at
sentier-mappings `179aab3`, one commit after sentier-brightway's pin, because it corrects
BAFU's `Chlorine` to air (high population).

## Run it

```sh
python3 scripts/build_release.py build path/to/bafu-2026-v1 output/provider --no-patches
python3 scripts/build_release.py build path/to/bafu-2026-v1 output/patched
python3 scripts/build_release.py compare output/provider output/patched --out output/comparison.json
```

`build` needs Python 3.12 or newer, `uv` and `git`. It clones sentier-importers and
sentier-brightway at the commits in `scripts/release_build/pins.toml` (or uses checkouts given
with `--tools`), runs each in its own `uv` environment, and writes everything under the output
folder. Options:

- `build latest OUT` lets the patch tool download and check BAFU's release first.
- `--published-results FILE` adds the comparison with BAFU's published LCIA results. The
  workbook is not in this repository; without it, or if the file is missing, the step is
  skipped and says so.
- `--pinned-data` lets several builds share one copy of the pinned flow terms, methods and
  mapping.
- `--fail-on-findings` turns the audit's findings into a failed build.
- `--sample FILE` names other datasets for the audit to score.

The output folder holds BAFU's inventory as EcoSpold files, as tables and as a Brightway
database. It is under [BAFU's Terms of Use](terms-of-use.md): keep it local (`output/` is
ignored by git). A CI job may keep `audit/audit.json` and the comparison, which hold counts,
dataset codes, names and single scores. It must not upload the folder.

`OUT/build.json` records the tool commits, the data pins, each step's time and peak memory,
the audit's errors and findings, and under `export` what an export of the database needs:
the Brightway folder, the project, the three database names, and `build-steps.json`, the
build's own changes in the shape of the patch tool's steps.

### Tests

`python3 -m unittest discover -s release-build-tests` runs the tests on synthetic data. Tests
that need pandas, SciPy or bw2data are skipped where those are missing; run them in the
sentier-brightway environment to run all but one, and in this package's environment to run
the one that checks the adapter against the patch tool's output.

The whole path runs on a made-up release of seven datasets (`synthetic_release.py`): patch
tool, adapter, importer, install and audit, for both builds, with scores checked against
hand-worked values. It needs `uv`, `git` and, the first time, the network, so it runs only
when asked:

```sh
RELEASE_BUILD_WHOLE_PATH=1 python3 -m unittest discover -s release-build-tests -p test_whole_path.py
```

### In CI

`.github/workflows/release-build.yml` runs the made-up release on pull requests. On pushes to
`main` and on manual dispatch it fetches BAFU's release as the patch tool does (checked by
SHA-256, cached under the same key as the Full release workflow), builds and audits both
releases, compares them, and writes the result as the job summary. The patched build fails on
any audit finding. The job uploads the two audits and the comparison, and nothing else.

## The chain

| Step | Tool | Reads | Writes |
|---|---|---|---|
| 1. patch | `bafu-fixes run` (this repository) | folder of EcoSpold 1 files | folder of EcoSpold 1 files with extensions, HTML report |
| 2. adapt | `scripts/release_build/adapter.py` | that folder, and for a patched release the provider release | zip the importer can read, receipt |
| 3. import | `sentier-importers run bafu-processes`, `run bafu-exchanges` | zip at a fixed path below its data root | `processes.parquet`, `exchanges.parquet` |
| 4. label | `scripts/release_build/label_release.py` (patched release only) | the two tables, the receipt | the tables under the patched release's name, `source-observations.json` |
| 5. data | `scripts/release_build/data_root.py` | sentier-brightway's pins | flow terms, methods and mapping, checked by SHA-256 |
| 6. install | `sentier-brightway db` | a data root with four folders | three Brightway databases, 25 methods |
| 7. mark | `scripts/release_build/mark_database.py` | the build's record | what the database was built from, in its metadata |
| 8. audit | `scripts/release_build/audit_brightway.py` | the Brightway project | `audit.json`, `scores.csv` |
| 9. published | `sentier-brightway backtest` (with `--published-results`) | the data root, BAFU's workbook | `published-results.json` |

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
same input gives the same zip). It changes no amount, unit or location. The copy is an
intermediate file, not a release. The receipt lists, per dataset, the import fixes and patches
recorded on it.

**Elementary flows keep the identity BAFU declared.** The importer derives a flow's
identifier from its name, compartment, subcompartment and unit, and the mapping to EF 3.1 is
keyed by that identifier. A patch that corrects one of the four gives the exchange an
identifier the mapping does not hold. The glossary calls an exchange as originally declared a
source observation, kept even when corrected attributes differ. The patched release does not
carry it: per exchange its extensions hold `originalNumber`, `brightwayFlow` and
`brightwayMatch`. So the adapter reads the provider release beside the patched one, pairs
the exchanges of each dataset by position (and checks number and kind), and where the four
differ on an elementary exchange it hands the importer the declared ones. The corrected ones
go into the receipt with the dataset and the position.

### 3. The importer

- The registry hard-codes where the release is:
  `file://${SENTIER_DATA_ROOT}/sources/bafu-2026/BAFU-2026 v1_ecoSpold v1.zip`
  (`app/sentier_importers/registry.yaml:419`, `:431`). The build puts the adapter's zip there,
  below its own data root.
- `SOURCE_ID = "bafu-2026"`, `SOURCE_VERSION = "v1"` and the folder name `bafu-2026-v1` are
  constants (`ecospold.py:29-36`). Every dataset row gets them, whatever was read. For a
  patched release `label_release.py` writes `bafu-2026-v1-patched` and a version that names
  the patched files (`tree-` and the first eight digits of their fingerprint) on every
  dataset, gives the exchanges the adapter recorded their corrected name as the label, and
  writes `source-observations.json` beside the tables.
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
  it adds the label "Modified Data", `modified: true` and the patch run; the schema allows
  further keys.

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
names the databases (`constants.py:36-43`); the flow terms must carry the same source name
(`flows.py:85-88`). For a patched release the build therefore writes the provider's 2,679
elementary flow terms again under the patched name. They are the same flows, because the
exchanges are linked on the declared ones.

### 5. The install and the marker

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
- sentier-brightway writes nothing into the database about where its data came from.
  `mark_database.py` adds the key `release_build` to the metadata of the inventory database
  and of the database of flows without an EF 3.1 flow: the label ("Modified Data" or
  "Provider release"), BAFU's credit, the fingerprints of the provider release and of the
  files that were built, the patch ids and import fix ids, the build's own steps, the tool
  commits and the data pins. It refuses to put modified data under BAFU's name.

### What the comparison with BAFU's published results does

`sentier-brightway backtest` scores every dataset in the 25 categories from the files export
with one transposed solve per category (`backtest/scorer.py:145-175`) and compares with BAFU's
LCIA results workbook, sheet `BAFU_2026 v1` (`backtest/reference.py:62-120`). Rows are joined
by dataset name and location (`backtest/compare.py:23`, `:191`); the workbook's
`RER without CH` is read as `Europe without Switzerland` (`:72`). The patched release writes
`EURwoCH`, so 26 of its datasets are not joined. With `--published-results` the build runs
it and `published_results.py` writes, per category, how many datasets were compared, the
share within 1 % and within 5 %, and the median difference. Matching BAFU's published
results is not a goal; the step shows what a build changes.

### The audit and the comparison

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

Errors fail the audit: an unlinked exchange, a score that is not a number, modified data
under BAFU's name. Findings are for a person to look at: a sample score outside its range, a
database that does not say what it was built from, and elementary flows that the pinned flow
terms don't hold. The last one is how a lost link shows in a single build: such a flow has an
identity the mapping cannot know.

`compare_builds.py` compares the importer's tables of two builds row by row (a row is a
dataset and an exchange position), attributes each changed row to a step recorded on that
dataset, and attributes each moved score to the changed datasets in its supply chain. It fails
if a changed row or a moved score has no explanation. The table of what each step may change
is in the script; a step that starts to change something else shows up as unexplained.

## What the runs of 13 November 2026 measured

Four full runs of both builds. The numbers below are from the last one, with the tools and
data in `pins.toml`. The first three linked elementary exchanges on the flow as patched; what
that did is under [Before the declared flow was used](#before-the-declared-flow-was-used).

Both builds: 11,947 datasets; 11,947 production, 114,369 technosphere and 293,747 elementary
exchanges; no unlinked exchange; audit passed. The provider release's inventory tables equal
the ones sentier-inventory publishes at the commit sentier-brightway pins, row for row, so the
adapter changes nothing the importer reads.

| | Provider release | Patched release |
|---|---|---|
| database | `bafu-2026` | `bafu-2026-v1-patched` |
| label in its metadata | Provider release | Modified Data, 11 patches, 14 import fixes |
| BAFU flows linked to an EF 3.1 flow | 2,566 of 2,679 | 2,566 of 2,679 |
| elementary exchanges on an EF 3.1 flow | 284,443 | 284,443 |
| elementary exchanges without one | 9,304 | 9,304 |
| audit findings | 3 (the strawberry datasets' scores) | none |

### Rows

Of 420,063 exchange rows, 188 differ between the two builds, and every one is explained:

| Step | Rows | Datasets | What changes |
|---|---|---|---|
| patch 0001 | 3 | 3 | the amount of polyethylene disposal in three strawberry datasets |
| patch 0002 | 25 | 25 | the declared supplier location; the link does not change |
| patch 0007 | 129 | 117 | the label of an elementary exchange; its flow stays the declared one |
| import fix `location-codes` | 31 | 26 | `Europe without Switzerland` becomes `EURwoCH` (also on 26 datasets) |

Patch 0008 changes no row: the compartment is part of the flow's identity, not a column, and
the 25 exchanges stay on the declared flow. Patches 0003 to 0006 and 0009 to 0011 change
nothing the importer reads: CAS numbers and extension attributes are not part of a flow's
identifier, and the importer writes every dataset as a unit process.

Patch 0002 does not change a link on this path, because the importer links by number: all
114,369 technosphere inputs are linked in both builds. What it changes is how many inputs
declare a location that differs from the linked dataset's: 37 in the provider release, 12 in
the patched release. A further 1,399 inputs declare no location in either.

In both builds 660 technosphere inputs declare a unit that is not the linked dataset's: 619
are two spellings of one unit (`p` and `unit`), 40 declare `m3` for a dataset in `Nm3`, and
one declares `kWh` for a dataset in `MJ` (the input `Electricity, natural gas, at power plant`
of `Electricity, from natural gas`, FI). Brightway does not convert between the unit of an
exchange and the unit of its supplier, and an export that checks units refuses the last one.

### Elementary flows

154 elementary exchanges in 135 datasets carry a flow that a patch corrects. All are linked
on the declared flow and stay on the EF 3.1 flow they have in the provider release:

| Declared flow | Corrected | Patch | Exchanges | EF 3.1 flow |
|---|---|---|---|---|
| `Gas, natural/m3` (Nm3) | `Gas, natural` | 0007 | 115 | Natural Gas |
| `Gas, mine, off-gas, process, coal mining/m3` (Nm3) | name without `/m3` | 0007 | 12 | Natural Gas |
| `Wood, unspecified, standing/kg` (two compartments) | name without `/kg` | 0007 | 2 | Wood |
| `Carbon dioxide, in air` under `resources / unspecified` | `resources / in air` | 0008 | 17 | carbon dioxide (biogenic) |
| `Carbon dioxide, in air` under `resources / biotic` | `resources / in air` | 0008 | 8 | carbon dioxide (biogenic) |

### Scores

- In all 25 methods exactly three datasets move: the strawberry datasets of patch 0001. For
  climate change they go from 383.2, 55.47 and 55.51 to 0.659, 0.783 and 0.829 kg CO2 eq per
  kg. The provider release's values are outside the sample's plausible range; the patched
  values are inside.
- No other score moves. Below the tolerance of 1e-6, the largest difference between the two
  builds is 3e-16, and between two builds of the same release 8e-12.
- sentier-brightway documents one score, 0.0320835 kg CO2 eq per kWh for
  `Electricity, low voltage, production CH, at grid`. Both builds reproduce it.

### The mapping commit

Moving the mapping from sentier-brightway's pin (`5ba4acd`) to `179aab3` changes one entry,
`Chlorine` to air (high population), used by 410 exchanges. On the provider release it moves
scores in the three freshwater ecotoxicity methods and in no other: by more than 1 % for 3
datasets in the total, 20 in the inorganics part and 1,120 in the organics part.

### Against BAFU's published results

Both builds were compared with BAFU's corrected LCIA results workbook (July 2026).

| | Provider release | Patched release |
|---|---|---|
| datasets joined by name and location | 11,947 | 11,921 (26 are now `EURwoCH`) |
| climate change within 1 % | 99.98 % | 99.96 % |
| Resource use, fossils within 1 % | 97.75 % | 97.72 % |
| Resource use, fossils, median difference | −0.07 % | −0.07 % |

### Before the declared flow was used

In the first three runs the importer derived each flow's identifier from the patched
attributes. The four flows that patch 0007 renames then had identifiers the mapping does not
hold: 129 exchanges lost their EF 3.1 flow, 127 of them natural gas and mine gas with a factor
in Resource use, fossils. That method's score moved for 11,659 of 11,947 datasets
(`Natural gas, at production`, NO: 37.14 to 0.28 MJ), and the share within 1 % of BAFU's
published results fell from 97.75 % to 11.56 %. The audit of the patched build reported the
four flows as a finding. Regenerating the mapping's matched package on the patched release
did not repair it: its energy contents and one alias are keyed by BAFU's original names
(`sources/bafu/ef_units.py:160-163`, `matching/aliases.yaml:100` in sentier-importers), so
the five entries for the old names were dropped and none was added.

### Time and memory

Measured on one machine (Apple silicon, macOS) while other jobs were running, so the times
are upper bounds for that machine. Peak memory is the largest resident size of the step's
process tree, in MB of 1,048,576 bytes, as `build.json` records it. Last run.

| Step | Provider release | Patched release |
|---|---|---|
| patch (`--xsd-check every-step`) | not run | 157 s, 1,572 MB |
| adapt | 9 s | 15 s |
| import | 12 s, 883 MB | 12 s, 889 MB |
| label | not run | 1 s, 396 MB |
| data (files already present) | 1 s, 129 MB | 1 s, 157 MB |
| install | 64 s, 1,457 MB | 65 s, 1,469 MB |
| mark | 3 s, 210 MB | 3 s, 208 MB |
| audit | 9 s, 833 MB | 9 s, 822 MB |
| published | 11 s, 1,538 MB | 12 s, 1,535 MB |
| whole build | 109 s, 1,538 MB | 275 s, 1,572 MB |

Over the four runs the whole build took 109 to 194 s (provider) and 275 to 370 s (patched).
A first `data` step downloads 25 files, 37 MB; that took 12 s. The whole path on the made-up
release took 126 s and 1,005 MB, most of it the install of the EF 3.1 flows and methods.

## What is missing

1. **The mapping does not know the corrected flow names.** The build does not need it to,
   because it links on the declared flow. A consumer that reads the patched release without
   the provider release beside it does: the patched release does not carry the declared name,
   compartment and unit of an exchange it corrects. Two ways to close this: the patch tool
   keeps them as it keeps `originalNumber`; or sentier-importers and sentier-mappings learn
   the corrected names (energy contents and alias as above), with entries for both spellings.
2. **The importer cannot read the patch tool's output, nor name a patched release.** The
   adapter and the label step bridge this. A change to the importer's `ecospold.py` that
   ignores the namespace and reads `originalNumber` gave tables identical to the adapter's
   when tried.
3. **The importer writes no `metadata.json` from its command line**, and has no way to point
   at a release file other than the fixed path below its data root.
4. **sentier-brightway names the database after the source and looks up flow terms of that
   same source.** The build writes the provider's flow terms again under the patched name. A
   database name independent of the source would make that unnecessary.
5. **The patch tool has no machine-readable list of changes on this branch.** The comparison
   attributes changed rows with a table of what each step may change, checked against the
   data on every run. Where `bafu-fixes run` has `--summary`, the build passes it and keeps
   the file for an export.
6. **sentier-brightway's export manifest names its own pins** even when `--data-root` supplies
   other data, so the files export behind the comparison with BAFU's results misstates the
   inventory and the mapping commit. `build.json` holds the pins that were used.
7. **26 datasets of a patched release are not joined to BAFU's published results**, because
   the comparison does not know `EURwoCH`.
8. **Only global factors are installed**, and only EF 3.1. Uncertainty is carried into the
   Brightway database but not into the files export.
9. **Nothing has run on GitHub.** The workflow passes actionlint and its steps were run
   locally as written, on macOS.
