# Exports of the patched release

`scripts/export_release.py` turns a Brightway build of the patched release into files for
openLCA, SimaPro and Brightway, each with its provenance. It is the last step of a build and
runs outside the package project, on its own pinned requirements.

The writers come from [bw-interchange-export](https://gitlab.com/eos-lci/bw-interchange-export)
(MIT), pinned by commit in the script. The step adds what BAFU's
[Terms of Use](terms-of-use.md) ask of anything passed on: the credit, the *Modified Data*
label and the record of modifications.

## Run it

As the last steps of the whole path, for the patched release and for every contribution
built beside it (see [The whole path](release-build.md)):

```sh
python3 scripts/build_release.py release path/to/bafu-2026-v1 output/run
```

Or on its own, on a database that `build_release.py build` wrote. The build's `build.json`
names everything the step needs under `export`:

```sh
uv run --python 3.12 scripts/export_release.py \
    --brightway-dir output/patched/brightway --project bafu-2026-v1-patched \
    --database bafu-2026-v1-patched --database ef-3.1-biosphere \
    --database bafu-2026-v1-patched-residual \
    --summary output/patched/release-summary.json \
    --extra-steps output/patched/build-steps.json \
    --release "BAFU:2026 v1" --name bafu-2026-v1-patched --out output/exports
```

`--brightway-dir` is required: the step reads only the Brightway folder you name and never
the projects in the default location. The output folder must be new or empty. `--summary`
is the run summary of the patch tool (`bafu-fixes run --summary`); the address and the
checksum of BAFU's release are taken from it. The step runs on Python 3.12.

The step exports only a database that says what it is. It refuses, before it writes
anything:

- a database without the build's marker (`release_build` in its metadata, label
  *Modified Data*), or one whose marker says it was built from other files than the run
  summary describes;
- a record that names a changed dataset the database does not have;
- exchanges that point at a database you did not name (the writers would drop the rows).

The export files are produced and read back in CI but are not published until a download
exists that asks for acceptance of BAFU's terms.

## What it writes

| File | For | Read with |
|---|---|---|
| `<name>.bw2package` | Brightway | `bw2io.BW2Package.import_file(path)` |
| `<name>-openlca.zip` | openLCA | its JSON-LD import |
| `<name>-ilcd.zip` | ILCD readers | written by the same call; counted, not compared |
| `<name>-simapro.csv` | SimaPro | its CSV import |
| `MODIFICATIONS.md`, `MODIFICATIONS.json` | everyone | the record of modifications |
| `manifest.json`, `SHA256SUMS` | everyone | provenance, tool versions, checksums, checks |

The Brightway file is a `.bw2package` because it installs the datasets, with names and
metadata, into a Brightway project of the user's choice (tested with bw2data 4.8), and
because the two other writers read exactly this file: all three exports come from one
checksummed source. It does not replace the `registry/` and `bw_package/` files that
sentier-brightway writes for calculating without a project.

## Where the provenance is

| | Credit and label | Ids of the modifications | Per dataset | Full record |
|---|---|---|---|---|
| Brightway | database metadata `provenance` | same | not written | `MODIFICATIONS.*` beside it; checksum in the metadata |
| openLCA | each process: restrictions | same | each process: description | `MODIFICATIONS.*` beside it |
| ILCD | each process: access restrictions | same | not written | `MODIFICATIONS.*` beside it |
| SimaPro | header, one literature reference | same | each process: comment | `MODIFICATIONS.*` beside it |

The per-dataset note says *Modified Data* on every dataset and names the steps that
changed it. The run summary names a changed dataset by its file, `process_<code>.xml`, and
the build gives the dataset that code, so the two are joined exactly; `MODIFICATIONS.json`
adds the name and location the database has. `manifest.json` counts how many datasets were
joined (11,601 of 11,947 in BAFU:2026 v1: every changed dataset).

None of the three formats has a place for the full record inside the file, so it travels
beside them. Keep the folder together when passing it on.

## Labels: units and compartments

The step gives the writers the labels of a declared table,
`scripts/release_build/export_labels.toml`. A label is a name. No amount is multiplied,
divided or dropped because of the table, and the manifest says so
(`labels.amounts_converted: 0`).

**Units.** One row per unit of BAFU's files (20 strings, two of them, `p` and `unit`, for
one thing), with what the Brightway build writes and what each format is given:

- openLCA and ILCD get the Brightway spelling, which their writer knows, for every unit but
  one. It has no unit named `normal cubic meter` or `Nm3` and refuses both. openLCA's
  reference data lists `Nm3` as a synonym of its unit `m3`, so these files write `cubic
  meter` and each such dataset's description says: "Unit in BAFU's release: Nm3. It is
  written here as cubic meter; the amounts are unchanged." 669 datasets are in `Nm3`.
- SimaPro gets BAFU's own unit symbols (`kg`, `kWh`, `Nm3`, `personkm`, …), each declared in
  the file's Units block.
- The Brightway package keeps the database's own spelling.

A unit that the table does not have and the JSON-LD writer does not know fails the openLCA
and ILCD formats; the other formats are still written.

**An input whose declared unit is another quantity than its supplier's** is written with
the amount the database holds, in the supplier's unit, with the declared unit in the
exchange's comment, and is listed in the manifest with the finding it belongs to. BAFU:2026
v1 has one: `Electricity, from natural gas` (FI) declares 0.0156738 kWh of a dataset whose
unit is MJ (finding F13). It is not converted and not dropped. 40 more inputs declare `m3`
for a dataset in `Nm3`: the same quantity by the table, counted in the manifest.

**Compartments.** The elementary flows of the build carry the three-level compartments of
the EF 3.1 flow list (`Emissions / Emissions to water / Emissions to fresh water`) or, for
flows without an EF 3.1 flow, BAFU's own (`emissions to water / river`). The SimaPro CSV
has one section per compartment. The table declares the section of each compartment; the
subcompartment written is the rest of the flow's compartment as the database has it. A
flow in use whose compartment is not declared fails the SimaPro format.

**Flows that share a name and a compartment.** SimaPro tells elementary flows apart by name
and compartment. 206 of the 1,927 elementary flows in use in BAFU:2026 v1 share both with
another flow in the build's flow list (for example five flows `Waste Heat` to `air`); in
the CSV each of them carries its code after its name, so that they stay different flows.

**Flows in use.** The build's flow databases hold 93,154 elementary flows; the inventory
uses 1,927. The openLCA, ILCD and SimaPro files hold the flows in use. The Brightway
package holds the databases whole.

## What the step checks

After writing, every file is read back with an independent reader (`olca_schema`,
`bw_simapro_csv`, `bw2io`) and compared with the database: the same datasets, exchanges,
amounts and units; every link resolves, by provider in openLCA and by product name in
SimaPro; each elementary flow is in the section of its compartment; the credit and the
label are present; an input with a declared unit of another quantity carries its note.

Each format is written and checked on its own. One that can't be written, or that reads
back differently, is recorded in `manifest.json` under `formats` with the stage (`write` or
`read back`) and the reason; a file that could not be written is removed; the other formats
are still written and checked. If any format failed the step exits 1 and the manifest says
`"status": "failed"`.

## Measured on BAFU:2026 v1

The export of the patched database built by the whole path on 13 November 2026 (11,947
datasets, 420,063 exchanges, 1,927 elementary flows in use):

| File | Size | Read back |
|---|---:|---|
| `bafu-2026-v1-patched.bw2package` | 16.1 MB | every node of the three databases equal to the database; credit and label in the metadata |
| `bafu-2026-v1-patched-openlca.zip` | 48.3 MB | 11,947 processes and 13,874 flows; every exchange with its flow, unit, provider and amount; credit and label in every process |
| `bafu-2026-v1-patched-ilcd.zip` | 54.8 MB | 11,947 process datasets counted; the credit and the label searched in each. Not compared exchange by exchange |
| `bafu-2026-v1-patched-simapro.csv` | 50.9 MB | 11,947 processes; 114,291 input rows, each resolving to one product; 293,747 elementary rows with section, name, subcompartment, unit and amount |
| `MODIFICATIONS.json`, `MODIFICATIONS.md` | 4.3 MB, 19 kB | |

No difference was found in any of the four. The step took 188 s and 3.0 GB at its peak.
The SimaPro file has 78 input rows fewer than the database has technosphere exchanges: an
input of a dataset's own product is not a row, it is subtracted from the product amount.

## What an export does not do yet

Read these before relying on a file. Each is pinned by a test in `export-tests/`.

- **Elementary flows keep Brightway's identity.** In openLCA they get ids minted from the
  database name and the node code; in SimaPro they get the Brightway names and
  subcompartments. They do not merge with EF 3.1 or with a tool's reference flows.
- **Units and flow properties are the file's own**, with minted ids. Imported into an
  openLCA database that has reference data, they sit beside it.
- **Every elementary exchange is written as an input** in the JSON-LD, emissions too.
- **An activity with a second product** is written as an allocated co-product, where
  Brightway credits the second product against its other producer. Scores differ. The
  BAFU:2026 v1 files have none: every dataset has one reference product and no co-product.
- **SimaPro product names** are `product | activity | location` (the writer's "linked"
  naming). With its default naming an input cannot be linked to one provider wherever two
  activities share a name, as 4,526 of the 11,947 BAFU:2026 v1 datasets do.
- **SimaPro's own names** for elementary flows, subcompartments and units are not used:
  the file keeps the names of the build, so it does not merge with SimaPro's flows.
- **The EF 3.1 methods are not in the files.** The step can write impact factors into the
  openLCA archive (`--methods-cf`); the build does not hand them over yet.
- **Checksums differ between two runs** for the Brightway package and the openLCA archive:
  both carry the time the patch run finished. The ILCD package and the SimaPro CSV of two
  runs on the same revision are byte for byte the same.
- **Formulas** of parameterised amounts are not written; the amounts are.
- **No file has been imported into openLCA or SimaPro.** The checks read the files with
  independent parsers. Scores recomputed from the files equal Brightway's on the test
  database; that is a reading of the files, not a run of either tool.

## Tests

```sh
uv run --no-project --python 3.12 --with-requirements export-tests/requirements.txt \
    pytest export-tests
```

The tests build a small made-up database (`export-tests/synthetic.py`), export it, read it
back and compare. Tests marked `xfail` state what the writers do not do yet; they fail the
day a writer closes the gap.
