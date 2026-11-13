# Exports of the patched release

`scripts/export_release.py` turns a Brightway build of the patched release into files for
openLCA, SimaPro and Brightway, each with its provenance. It is the last step of a build and
runs outside the package project, on its own pinned requirements.

The writers come from [bw-interchange-export](https://gitlab.com/eos-lci/bw-interchange-export)
(MIT), pinned by commit in the script. The step adds what BAFU's
[Terms of Use](terms-of-use.md) ask of anything passed on: the credit, the *Modified Data*
label and the record of modifications.

## Run it

```sh
# 1. The patch run writes the record of modifications as data.
uv run bafu-fixes run latest output/ --summary output/run-summary.json

# 2. Build the Brightway database from output/ (a separate step), in a folder of its own.

# 3. Export. Name every database the inventory links to, the elementary flows too.
uv run scripts/export_release.py \
    --brightway-dir path/to/brightway-folder --project NAME \
    --database INVENTORY --database ELEMENTARY-FLOWS \
    --summary output/run-summary.json --release "BAFU:2026 v1" \
    --source-url https://files.brightway.dev/bafu-2026-v1-ecospold.zip \
    --source-sha256 cbaeed4ae79c0be98709c854211cd72725d4f22f8b9b3fe334b7f343fca152f5 \
    --out output/exports
```

`--brightway-dir` is required: the step reads only the Brightway folder you name and never
the projects in the default location. The output folder must be new or empty. The step runs
on Python 3.12 and 3.14.

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
changed it when the record has exactly one dataset of that name and location.
`manifest.json` counts how many datasets were matched.

None of the three formats has a place for the full record inside the file, so it travels
beside them. Keep the folder together when passing it on.

## What the step checks

After writing, every file is read back with an independent reader (`olca_schema`,
`bw_simapro_csv`, `bw2io`) and compared with the database: the same datasets, exchanges,
amounts and units; every link resolves, by provider in openLCA and by product name in
SimaPro; the credit and the label are present. The result is in `manifest.json` under
`checks`. If anything differs the step exits 1 and the manifest says `"status": "failed"`.

Before writing, the step refuses:

- exchanges that point at a database you did not name (the writers would drop the rows);
- units the JSON-LD writer has no quantity for. `Nm3`, `kmy` and `hr` are among them, and
  BAFU's files use all three. Give a label with `--openlca-unit-label Nm3=m3`: the amount
  is written unchanged under that label, and the manifest records it. openLCA's reference
  data lists `Nm3` as a synonym of `m3`, `kmy` of `km*a` and `hr` of `h`.

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
