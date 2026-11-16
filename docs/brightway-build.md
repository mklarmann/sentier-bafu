# From a release to a Brightway database

This page maps the path from BAFU's release to a Brightway database with the EF 3.1 methods,
says where each tool reads and writes, and records what full runs measured on 13 November
2026. It covers the provider release (BAFU:2026 v1 as BAFU ships it) and the patched copy
(the same release with the import fixes and community patches of this repository).

The path uses three tools that were written separately: the patch tool and the Brightway
installer, which are now the two packages of this repository, and sentier-importers. It runs
end to end, with one adapter between the patch tool and the importer. Both builds pass their audit. In the patched build
the scores of three datasets differ from the provider build, in every method: the strawberry
datasets that patch 0001 corrects.

**The two databases cannot be taken for one another.** The provider release is installed as
`bafu-2026`, BAFU's name. A patched copy is installed as `bafu-2026-v1-patched`, and its
metadata carries the label "Modified Data", the patch ids and the import fix ids.

**Which flow links the scores use.** Scores come through sentier-mappings, the route the
installer takes by default: each BAFU flow is relinked to the EF 3.1 flow the mapping names,
with the mapping's conversion factor. Each elementary exchange is linked on the flow as BAFU
declared it. Where a patch corrects a flow's name or compartment, the corrected name becomes
the exchange's label and both are listed beside the data; the link does not change. The
Brightway Flows identifiers that patch 0010 writes on every elementary exchange are identity
links. By default they are not used for scores, and they are never joined to a factor table
keyed by EF 3.1 identifiers: many of them name flows outside EF 3.1. The mapping is taken at
sentier-mappings `179aab3`, which corrects BAFU's `Chlorine` to air (high population). The
installer's pins (`src/sentier_brightway/sources.toml`) name that commit, so the installer
run on its own and the build read the same mapping.

**A flow that names a country takes that country's factor** (since 15 November 2026). BAFU
has 238 elementary flows with a country in their name, such as `Water, CH`. The mapping
states the country, and the methods hold factors of single countries, for water use mostly.
The build brings the two together for 184 of those flows; every other flow takes the factor
without a location. See "Flows that name a country" below.

**The build can also link through those identifiers** (`build --linking brightway-flows`,
since 15 November 2026). It is a second way to build. The whole path runs under it, and it
is not the build's own: 165 flows lose a factor under it, and nothing built with it is kept
under a tag. See "The second linking: through Brightway Flows" below.

## Run it

```sh
python3 scripts/build_release.py release path/to/bafu-2026-v1 output/run
```

runs the whole path in one command: both builds, the checks of the patch run, the
comparison, the exports and the manifest ([The whole path](release-build.md)). The builds
and the comparison can also be run one by one:

```sh
python3 scripts/build_release.py build path/to/bafu-2026-v1 output/provider --no-patches
python3 scripts/build_release.py build path/to/bafu-2026-v1 output/patched
python3 scripts/build_release.py compare output/provider output/patched --out output/comparison.json
```

`build` needs Python 3.12 or newer, `uv` and `git`. It clones sentier-importers at the commit
in `scripts/release_build/pins.toml` (or uses a checkout given with `--tools`) and runs it in
an environment of its own. The patch tool and the Brightway installer are this repository's
two packages (`src/bafu_community_fixes`, `src/sentier_brightway`; the installer is the code
of sentier-brightway, moved here on 15 November 2026 with its history up to `90d57eb`). The
build runs both, and its own helpers, in the repository's one locked environment with the
`brightway` extra. Everything is written under the output folder. Both packages are at this
repository's commit: a build from a tree with local changes says so in `build.json`, and
`--allow-unpinned` is about the checkout of sentier-importers only. Options:

- `build latest OUT` lets the patch tool download and check BAFU's release first.
- `--published-results FILE` adds the comparison with BAFU's published LCIA results. The
  workbook is not in this repository; without it, or if the file is missing, the step is
  skipped and says so.
- `--pinned-data` lets several builds share one copy of the pinned flow terms, methods and
  mapping.
- `--linking brightway-flows` links the elementary flows the second way (below). `release`
  takes it too and hands it to both builds.
- `--fail-on-findings` turns the audit's findings into a failed build.
- `--sample FILE` names other datasets for the audit to score.
- `--contribution LAYER` builds the patched copy plus one contribution, as a database of
  the contribution's own name ([Building a contribution](contribution-builds.md)).
- `--labels FILE` gives the audit and the export another table of unit labels and of known
  differences of declared units (default: `scripts/release_build/export_labels.toml`).

The output folder holds BAFU's inventory as EcoSpold files, as tables and as a Brightway
database. It is under [BAFU's Terms of Use](terms-of-use.md): keep it local (`output/` is
ignored by git). A CI job may keep `audit/audit.json` and the comparison, which hold counts,
dataset codes, names and single scores. It must not upload the folder.

`OUT/build.json` records the tool commits, the data pins, how the flows were linked
(`linking`) and the installer's options (`install`), each step's time and peak memory,
the audit's errors and findings, and under `export` what an export of the database needs:
the Brightway folder, the project, the three database names, the run summary of the patch
tool (`release-summary.json`, which the build asks for and keeps), the table of labels, and
`build-steps.json`, the build's own changes in the shape of the patch tool's steps.

### Tests

`python3 -m unittest discover -s release-build-tests` runs the tests on synthetic data. Tests
that need pandas, SciPy, bw2data or the patch tool are skipped where those are missing. In
this repository's environment with the `brightway` extra none of them is missing
(`uv sync --locked --extra brightway`, then `uv run --no-sync python -m unittest discover -s
release-build-tests`).

The whole path runs on a made-up release of eight datasets (`synthetic_release.py`), from
the one command to the manifest: both builds with scores checked against hand-worked values,
the checks of the patch run, the comparison, the exports with their read-back, and a made-up
contribution built beside the patched copy. It needs `uv`, `git` and, the first time,
the network, so it runs only when asked:

```sh
RELEASE_BUILD_WHOLE_PATH=1 python3 -m unittest discover -s release-build-tests -p test_whole_path.py
```

### In CI

On pull requests `.github/workflows/full-release.yml` runs the made-up release and these
tests. On pushes to `main`, on request and for a tag, `.github/workflows/release-build.yml`
runs the one command on BAFU's full release, fetched as the patch tool does (checked by
SHA-256, cached), and writes the result as the job summary. The patched build fails on any
audit finding. The job uploads the manifest, the run summary, the audits and the
comparisons, and nothing that holds the inventory. See [The whole path](release-build.md).

## The chain

| Step | Tool | Reads | Writes |
|---|---|---|---|
| 1. patch | `bafu-fixes run` (this repository) | folder of EcoSpold 1 files | folder of EcoSpold 1 files with extensions, HTML report |
| 2. adapt | `scripts/release_build/adapter.py` | that folder, and for a patched copy the provider release | zip the importer can read, receipt |
| 3. import | `sentier-importers run bafu-processes`, `run bafu-exchanges` | zip at a fixed path below its data root | `processes.parquet`, `exchanges.parquet` |
| 4. label | `scripts/release_build/label_release.py` (patched copy only) | the two tables, the receipt | the tables under the patched copy's name, `source-observations.json` |
| 5. data | `scripts/release_build/data_root.py` | the installer's pins (`sources.toml`) | flow terms, methods and mapping, checked by SHA-256 |
| 6. install | `sentier-brightway db` | a data root with four folders | three Brightway databases, 25 methods |
| 7. mark | `scripts/release_build/mark_database.py` | the build's record | what the database was built from, in its metadata |
| 8. audit | `scripts/release_build/audit_brightway.py` | the Brightway project | `audit.json`, `scores.csv` |
| 9. published | `sentier-brightway backtest` (with `--published-results`) | the data root, BAFU's workbook | `published-results.json` |

File and line references below are to sentier-importers at `28b28ed`, to the installer as it
was moved here (sentier-brightway at `90d57eb`; later changes shift the lines) and to this
repository's patch tool as merged with #40.

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
  (`app/sentier_importers/sources/bafu/ecospold.py:196-199`). On the patched copy as
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
source observation, kept even when corrected attributes differ. The patched copy does not
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
  patched copy `label_release.py` writes `bafu-2026-v1-patched` and a version that names
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
  (`scripts/release_build/inventory_metadata.py`), with the same keys. For a patched copy
  it adds the label "Modified Data", `modified: true` and the patch run; the schema allows
  further keys.

### 4. The pinned data

The installer reads four folders below one data root (`constants.py:29-33`):
`sentier-inventory`, `sentier-vocab` (flow terms), `sentier-methods` and `sentier-mappings`.
Its `sources.toml` pins each file by commit and SHA-256. Without `--data-root` it downloads
them into its cache (`fetch.py:120-139`); with `--data-root` it reads local folders and checks
nothing. The build uses the installer's own reader to fetch and check the three folders
that are not the inventory (`fetch.py:92-113`), and puts the importer's output in the fourth.

`sources.toml` is the one place a data pin lives, and `build.json` lists the commit of each
data source. While the installer was another repository, the build's `pins.toml` could move
one of the three to another commit and did so for the mapping; two pins of one file could
disagree, and a measurement of 15 November 2026 was first made on the wrong one. Since that
day the installer's own pin names the mapping the build uses, and `pins.toml` names no data.

Where BAFU is hard-coded in the installer: the default source `bafu-2026`
(`constants.py:9`), the mapping folder `bafu-2026-v1__ef-3.1` (`:18`), the methods folder
`01-ef-3.1` (`:20`) and the citation (`:23-27`). `--source` selects the inventory folder and
names the databases (`constants.py:36-43`). By default the flow terms are looked up under the
same source name (`flows.py:85-88`). A patched copy has its own name and the flows of BAFU's
release, because its exchanges are linked on the declared ones; the build tells the installer
so (`--flow-terms-of bafu-2026`), and the installer reads BAFU's 2,679 flow terms as they are
pinned. Until 15 November 2026 the build wrote those terms a second time under the patched
name.

### 5. The install and the marker

- `load_inventory` picks the folder whose `metadata.json` names the source
  (`inventory.py:141-161`). `load_bridge` reads the mapping's `replace` entries in package
  order, first entry wins (`bridge.py:125-136`). `load_methods` reads the factors that have no
  location, which every flow takes, and the factors of single countries, which a flow takes
  only where it names the country (`located.py`; see "Flows that name a country").
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
- The installer writes nothing into the database about where its data came from: it
  installs any source, and what a build did to BAFU's release is the build's to say.
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
`RER without CH` is read as `Europe without Switzerland` (`:72`). The patched copy writes
`EURwoCH` for that location, and its 26 datasets there are joined under BAFU's spelling
(since 15 November 2026; before, they were left out). With `--published-results` the build
runs it and `published_results.py` writes, per category, how many datasets were compared, the
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
data that were pinned then. The first three linked elementary exchanges on the flow as patched; what
that did is under [Before the declared flow was used](#before-the-declared-flow-was-used).

Both builds: 11,947 datasets; 11,947 production, 114,369 technosphere and 293,747 elementary
exchanges; no unlinked exchange; audit passed. The provider release's inventory tables equal
the ones sentier-inventory publishes at the commit the installer pins, row for row, so the
adapter changes nothing the importer reads.

| | Provider release | Patched copy |
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
the patched copy. A further 1,399 inputs declare no location in either.

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
- sentier-brightway's README documented one score, 0.0320835 kg CO2 eq per kWh for
  `Electricity, low voltage, production CH, at grid`. Both builds reproduce it.

### The mapping commit

Moving the mapping from `5ba4acd`, the installer's pin until 15 November 2026, to `179aab3`
changes one entry,
`Chlorine` to air (high population), used by 410 exchanges. On the provider release it moves
scores in the three freshwater ecotoxicity methods and in no other: by more than 1 % for 3
datasets in the total, 20 in the inorganics part and 1,120 in the organics part.

### Against BAFU's published results

Both builds were compared with BAFU's corrected LCIA results workbook (July 2026).

| | Provider release | Patched copy |
|---|---|---|
| datasets joined by name and location | 11,947 | 11,921 (26 are `EURwoCH`, and were not joined then) |
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
four flows as a finding. Regenerating the mapping's matched package on the patched copy
did not repair it: its energy contents and one alias are keyed by BAFU's original names
(`sources/bafu/ef_units.py:160-163`, `matching/aliases.yaml:100` in sentier-importers), so
the five entries for the old names were dropped and none was added.

### Time and memory

Measured on one machine (Apple silicon, macOS) while other jobs were running, so the times
are upper bounds for that machine. Peak memory is the largest resident size of the step's
process tree, in MB of 1,048,576 bytes, as `build.json` records it. Last run.

| Step | Provider release | Patched copy |
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

## Flows that name a country

BAFU's elementary exchanges carry no location. 238 of BAFU's 2,679 elementary flows carry
one in their name instead: `Water, CH`, `Water, AT`,
`Occupation, traffic area, rail network, CH`. The mapping of sentier-mappings links such a
flow to its EF 3.1 flow and states the country beside it. sentier-methods holds, beside the
factors without a location, 42,689 factors of single countries in 11 of the 25 methods.

Until 15 November 2026 the installer read only the factors without a location, so `Water,
CH` was scored like water anywhere. Now a linked flow that names a country for which a
method has that country's factor is linked to the flow of that country: a node of its own
in `ef-3.1-biosphere`, named like the flow with the country added, with the country as its
`location`. It takes the country's factor in every method that has one, and the flow's
factor without a location in every other method.

A flow that names no country keeps the factor without a location, whatever the location
of the dataset it is in. Nothing says where such an exchange takes place, and BAFU's own
results read it the same way: in acidification and terrestrial eutrophication, where the
methods hold factors of 36 countries, 99.33 % and 99.05 % of the build's scores equal
BAFU's published ones to 0.01 %.

### What it changes, measured on 15 November 2026

`scripts/compare_located_factors.py` builds BAFU's release with and without the factors of
countries and scores all 11,947 datasets. The record is
`community/runs/factors-of-countries-2026-11-15.json`.

| | |
|---|---:|
| Flows that name a country | 238 |
| of which take a factor of their country | 184 (4,251 exchanges, 74 countries) |
| of which name a country no method has a factor for | 54 |
| Flows of a country they end on (an EF 3.1 flow in one country) | 183 |
| of which have the country's factor in water use | 181 |
| of which have the country's factor in land use | 2 |

- **Water use moves for 5,197 of the 11,947 datasets** by more than 1 %, for 854 of them by
  more than 10 %. 5,146 go down: a country's factor is mostly lower than the factor without
  a location.
- **Land use moves for 5 datasets**, all upwards and by more than 10 %: two flows of rail
  land in Switzerland.
- **No other category moves.**

Against BAFU's corrected results workbook (July 2026), which is not a goal to match and is
a second reading of what such a flow means:

| | Factors without a location only | With the factors of countries |
|---|---:|---:|
| Water use within 1 % of BAFU's | 30.94 % | 53.84 % |
| Water use within 5 % | 65.45 % | 79.52 % |
| Water use, median difference | +2.20 % | +0.86 % |
| Land use within 1 % | 99.09 % | 99.05 % |

Water use comes much closer. Land use moves away for the five datasets: for the two flows
of rail land, BAFU's results follow the factor without a location.

`sentier-brightway db --skip-located` builds as before. The build has no such option: a
build records under `install` that its flows took the factors of countries.

## The second linking: through Brightway Flows

`build --linking brightway-flows` links every elementary exchange to the flow of Brightway
Flows that patch 0010's crosswalk names for it, in place of the mapping of sentier-mappings.
The installer does it (`src/sentier_brightway/brightway_flows.py`,
`sentier-brightway db --flow-links FILE`); the rest of the build is the same. Three
statements are kept apart, each taken from where it is made:

| Statement | Taken from | Where it is not stated |
|---|---|---|
| Which flow it is | the crosswalk of patch 0010, with the identifier the flow has in Brightway Flows 1.1.0 | the flow stays on BAFU's flow, without a factor |
| How an amount converts | the multiplier Brightway Flows 1.1.0 states for the link (192 links; 159 of them Bq to kBq) | two spellings of one unit need none; otherwise the conversion is unknown and the flow is not linked |
| What the flow costs | the build's own methods (sentier-methods). A flow outside EF 3.1 takes the build's factors of the one flow that Brightway Flows' own implementation of EF 3.1 names as their source, where the two are counted in one unit | the flow has no factor |
| Which country the flow names | the mapping of sentier-mappings. The links end `Water, CH` and `Water` on one flow and state no country | the flow takes the factor without a location |

No factor is read from Brightway Flows. What the installer needs beside the crosswalk is in
`scripts/release_build/brightway-flows-targets-bafu-2026-v1.csv`, written by
`scripts/build_brightway_flows_targets.py` from two files of Brightway Flows 1.1.0 on Zenodo,
checked by their MD5. The file is derived from Brightway Flows and is under the Open Database
License 1.0, like the crosswalk.

A flow of EF 3.1 that the pinned flow terms and methods do not hold (38 of BAFU's flows end
on one) gets a node with the name the link gives it. A node of a flow that is reached from
several of BAFU's flows says where the flow goes as far as those flows agree.

### What it changes, measured on 15 November 2026

`scripts/compare_flow_linkings.py` builds BAFU's release both ways, on the data the build
uses (the mapping at `179aab3`), and scores all 11,947 datasets in the 25 categories. The
record is `community/runs/flow-linking-in-the-build-2026-11-15.json`. A flow "has a factor"
in a method when the flow it is linked to has one there that is not zero. Both ways give a
flow that names a country its country's factor (184 flows under the mapping, 183 under the
links).

| | Mapping of sentier-mappings | Links of patch 0010 |
|---|---:|---:|
| Flows linked, of 2,679 | 2,566 | 2,677 |
| Elementary exchanges linked, of 293,747 | 284,443 | 293,636 |
| Flows with a factor in at least one method | 1,950 | 1,794 |

- **The links reach more flows.** Only two stay unlinked: mine gas in m3 and in Nm3, whose
  target is in sm3, with no conversion stated.
- **Fewer flows end on a factor.** 165 flows (13,868 exchanges, 4.7 % of all) lose a factor
  in at least one method, 164 of them in every method; 8 gain one.
- **Those flows are in most supply chains.** 11,801 of the 11,947 datasets move by more than
  1 % in at least one category: particulate matter (11,446 datasets), freshwater
  eutrophication (11,636), freshwater ecotoxicity (10,144) and land use (11,132). Nearly all
  move downwards; in land use, 1,374 of the 11,132 move up. Acidification and terrestrial
  eutrophication do not move for any dataset; climate change moves for 20.

Why the 165 lose a factor:

| Flows | Exchanges | Why |
|---:|---:|---|
| 92 | 7,602 | The flow is outside EF 3.1, and Brightway Flows names no flow as the source of factors. BAFU's own land classes are among them. |
| 55 | 4,086 | Brightway Flows adopts or restates a factor from another implementation's list. The source it names is a flow of that list, which the build's methods do not hold. |
| 13 | 1,891 | The link ends on an EF 3.1 flow that has no factor there in the build's methods. |
| 2 | 111 | Not linked: the conversion is unknown. |
| 2 | 90 | Brightway Flows names two flows as the source. |
| 1 | 88 | The named source has no factor there in the build's methods. |

So the mapping stays the build's linking. What would let the links take over is listed
under "What is missing".

A first run of this measurement, shown on the page for some hours on 15 November, used the
installer's own pin of the mapping (`5ba4acd`) and gave 166 flows; the entry that differs
is BAFU's chlorine to air.

## What is missing

0. **The links of patch 0010 are not the build's linking yet.** 165 flows lose a factor
   (above). 92 of them need a source of factors in Brightway Flows, which is a change there.
   55 depend on which factors count for a flow outside EF 3.1: the build's own, as now, or
   those of Brightway Flows' own implementation. That is a decision for people. The whole
   path runs under the second linking since 15 November 2026 (`release --linking
   brightway-flows`): the comparison of two builds explains each score with the links that
   were installed, whichever linking that was, and the exports are written and read back.
   Nothing built with it is kept under a tag. The data file of the second linking is derived
   from Brightway Flows 1.1.0 (ODbL); the permission recorded for the crosswalk has not been
   asked for it.
1. **The mapping does not know the corrected flow names.** The build does not need it to,
   because it links on the declared flow. A consumer that reads the patched copy without
   the provider release beside it does: the patched copy does not carry the declared name,
   compartment and unit of an exchange it corrects. Two ways to close this: the patch tool
   keeps them as it keeps `originalNumber`; or sentier-importers and sentier-mappings learn
   the corrected names (energy contents and alias as above), with entries for both spellings.
2. **The importer cannot read the patch tool's output, nor name a patched copy.** The
   adapter and the label step bridge this. A change to the importer's `ecospold.py` that
   ignores the namespace and reads `originalNumber` gave tables identical to the adapter's
   when tried.
3. **The importer writes no `metadata.json` from its command line**, and has no way to point
   at a release file other than the fixed path below its data root.
4. *(Closed on 15 November 2026.)* The installer looked up flow terms under the name of the
   inventory's source, so the build wrote the provider's flow terms again under the patched
   name. The installer now takes the source of the flow terms as an option, and the build
   reads its linking report from a file the installer writes, not from what it printed.
5. **The patch tool's run summary says which fields a step changed, not which rows.** The
   comparison attributes changed rows with a table of what each known step may change,
   checked against the data on every run; a step that is not in the table (a new patch) is
   explained from the fields the run summary says it changed. A list of the changed rows
   themselves would make the attribution exact.
6. *(Closed on 15 November 2026.)* The manifest of a files export named the installer's own
   pins even when `--data-root` supplied other data, so the export behind the comparison
   with BAFU's results misstated the inventory. The installer now records which files it
   reads. The manifest names a source's commit only where every file read is a pinned file
   with the pinned SHA-256; for any other source it lists the files read with their SHA-256
   and no commit. For a build that means: flow terms, methods and mapping as pinned, and the
   inventory as the three files the build made.
7. *(Closed on 15 November 2026.)* 26 datasets of a patched copy were not joined to BAFU's
   published results, because the comparison did not know `EURwoCH`, the patched copy's
   spelling of `Europe without Switzerland`. They are joined now, and the run report counts
   them (`own_location_spellings_joined`).
8. *(Closed in part on 15 November 2026.)* Only factors without a location were installed.
   A flow that names a country now takes that country's factor ("Flows that name a
   country"). What stays: a flow that names no country takes the factor without a location
   whatever the location of its dataset, because nothing says where such an exchange takes
   place; only EF 3.1 is installed; and uncertainty is carried into the Brightway database
   but not into the files export.
9. *(Closed.)* The build's workflow has run on GitHub's runners since 13 November 2026, in a
   fork: fifteen runs on BAFU's full release up to 15 November. In this repository it is not
   on `main` yet.
