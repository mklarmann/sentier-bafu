# The patch tool

`bafu-community-fixes` reads BAFU's release (UVEK LCI data, distributed as EcoSpold 1 XML), makes
it schema-compliant, applies the community patches, and writes EcoSpold 1 XML again, optionally
with additional fields. Its package is `src/bafu_community_fixes/`; its commands are `bafu-fixes`
and `bafu-fixes-tui`.

The [README](../README.md#the-patched-copy) has the short version for someone who wants to run
it. This page has the rest: every option, how the tool works, what it writes, and how to write a
patch. [The whole path](release-build.md) describes what is built from the tool's output: a
Brightway database, the exports and the manifest of a release.

## Usage

```sh
uv sync
uv run bafu-fixes list
uv run bafu-fixes run latest output/ --strict --report output/report.html
```

`latest` downloads the latest BAFU release
(<https://files.brightway.dev/bafu-2026-v1-ecospold.zip>, about 37 MB). It's downloaded only
once: it's checked against a known SHA-256 checksum and kept in your user cache folder (on
macOS, `~/Library/Caches/bafu-community-fixes`). You can also pass a local folder or file. A
full `--strict` run with a report takes about a minute.

Or use the terminal app, which needs no command-line knowledge. It uses the latest release
by default, or a folder you pick in its file browser. Choose the output format and options,
tick the patches to apply, and press Run. It shows each step with a progress bar, and opens
the report in your web browser at the end. That last part can be switched off.

```sh
uv run bafu-fixes-tui
```

Options for `run`:

- `--strict`: also check every document against the official EcoSpold 1 XSD after
  import, and every changed dataset after each patch
- `--only ID [ID ...]` / `--skip ID [ID ...]`: choose which patches to apply
- `--no-extensions`: leave out our additional fields, giving plain EcoSpold 1
- `--report FILE.html`: write a run report (see below)
- `--summary FILE.json`: write a summary with counts, checksums and the steps that changed
  each dataset, and no data from the release: for automated runs, for comparing runs, and
  as the record of modifications for anything built from the output (see below)
- `--placeholder-year`, `--placeholder-number`, `--placeholder-country`,
  `--placeholder-text`: values filled in where required data is missing (defaults `1111`,
  `1111`, `AQ`, `UNKNOWN`). Blank values are kept, since the schema allows them. Placeholders
  are validated before the run: the text is also used for company codes, so it can be at
  most 7 characters. The terminal app has the same settings.
- `-v`: log progress

## How it works

1. **Parse** the XML and strip the EcoSpold namespace (the raw release has none anyway).
2. **Import fixes** (`import_fixes.py`) make the raw release readable. They work on the
   raw lxml tree, always run, and run in the order they are defined. Run
   `bafu-fixes list` to see them.
3. **Build models** (`models.py`): strict pydantic models that mirror the XSD. Anything
   that doesn't fit stops the run with a list of every problem: unknown attributes or
   elements, invalid values, broken references. With `--strict`, the official XSD is
   checked as well, as an independent second check.
4. **Patches** (`patches/`) run one at a time, in order of their id. After each patch, every
   dataset is revalidated, and any error is reported against that patch. The pipeline
   records the patch id on every dataset it changed.
5. **Write** EcoSpold 1 XML, in schema element order, with canonical number and date
   formatting.

The models are strict. Values must already have the right Python type, unknown fields are
rejected, and assignments are validated as they happen:

```python
exchange.mean_value = "1.5"  # ValidationError: not a float
exchange.name = "x" * 300  # ValidationError: longer than 255 characters
exchange.uncertainty_type = 1  # ValidationError: use UncertaintyType.LOGNORMAL
person.country_code = "XX"  # ValidationError: not an ISO code in the XSD
```

## Run reports

`--report` writes a single, self-contained HTML file, with the Sentier branding and nothing
external to load. It's meant to be shared with data users. It shows:

- which import fixes and patches ran, in order, and who wrote and authorised each one
- a prominent warning for every step that changed data without recorded authorisation
- per step: datasets and values changed, an example from the data showing the XML before and
  after the step, the most common before → after changes for each field, and every
  individual change for the first 10 datasets
- the schema check results, an input fingerprint (SHA-256), options, and software versions

If a run fails, the report is still written, with the error.

`--summary` writes the record as JSON for programs: the release that was read and the
files that were written (counts and checksums), the same steps with their authors,
authorisation, findings, references and counts, and for every changed dataset its file,
its number and the ids of the steps that changed it. It holds no names and no amounts.
One file serves the full release check in CI, the Brightway build
(`scripts/build_release.py`), the export step (`scripts/export_release.py`, see
[docs/exports.md](exports.md)), which labels its files as modified and carries the
list of changes, and the release manifest.

## Additional fields

Our own data lives in `<bcf:extensions>` (namespace `urn:bafu-community-fixes:extensions:1`)
at the end of each dataset. The EcoSpold 1 schema allows foreign elements there, so the
output stays valid. Extensions record:

- which import fixes and patches changed each dataset
- the original BAFU number of each exchange that got a dummy number (`originalNumber`)

## Exchange numbers

BAFU exchange numbers are identifiers: the reference product has the dataset's own number,
a technosphere input almost always (99%) has the number of the dataset that supplies it, and
an elementary flow has a number for its substance. They aren't unique within a dataset,
which EcoSpold 1 requires, mostly because one substance emitted to several subcompartments
shares a number.

So numbers are kept wherever possible (about 73% of exchanges). Where several exchanges
share a number, the reference product keeps it, or else the first one. The others get a
dummy number, `1,000,000,000 + original number × 1,000 + occurrence`. For example,
`1000631002` is the second exchange numbered 631. Any number of 1,000,000,000 or more is
a dummy and links to nothing.

In Python they are `dataset.ext` and `exchange.ext`. `--no-extensions` leaves them out.

## Writing a patch

Start from a finding that has a record in [`community/findings/`](../community/findings/README.md):

```sh
uv run python scripts/new_patch.py fix-something --finding F14
```

This creates the patch module in `src/bafu_community_fixes/patches/`, with the next free
number, and a test for it in `tests/`. A patch is registered by being in that folder; there
is no list to add it to. The places where the finding is discussed (its issue, then threads
elsewhere) become the patch's references. A patch that answers no finding is started with
`--no-finding`. Then write it:

```python
from bafu_community_fixes import Database, data_file, patch
from bafu_community_fixes.models import UncertaintyType


@patch(
    "0012-fix-something",
    findings=("F14",),  # the recorded findings that it answers; () if none
    authored_by="Jane Doe",  # who wrote this patch
    authorised_by="Chris Mutel",  # who approved it for the release; leave out until then
    reported_by="John Roe, Example AG",  # optional: who found the problem
    confirmed_by="BAFU, 1 November 2026",  # optional: the data owner's confirmation
    references=("https://github.com/sentier-dev/sentier-bafu/issues/1",),
)
def fix_something(db: Database) -> None:
    """One-line description, shown by `bafu-fixes list` and in the report.

    The rest of the docstring explains why the change is needed. It appears in the
    run report, so write it for data users.
    """
    for dataset in db:
        for exchange in dataset.exchanges:
            if exchange.name == "Sulfur dioxide" and exchange.uncertainty_type is None:
                exchange.uncertainty_type = UncertaintyType.LOGNORMAL
```

- Field names are the EcoSpold names in snake_case (`meanValue` becomes `mean_value`).
  `Dataset` also has shortcuts: `name`, `location`, `reference_function`, `exchanges`.
  `db.exchanges()` yields `(dataset, exchange)` pairs.
- Check the value you are about to replace, and raise `ValueError` if it isn't what you
  expect. The run then stops and names the patch, rather than changing data that has
  changed since the patch was written.
- Put supporting data in `src/bafu_community_fixes/data/`, prefixed with the patch id, and
  read it with `data_file(name)`.
- Don't record your changes yourself. The pipeline compares every dataset before and after
  your patch and reports each changed value.
- Complete the test. `tests/conftest.py` provides an imported fixture database.
- Run `python3 scripts/patches_snapshot.py`. It writes `community/patches.json` from the
  patches in the repository; the site reads the patches from that file, and the check of
  the records fails while the file differs from the patches. Never edit it by hand.
- Open a pull request with the patch, its test and `community/patches.json`. Its checks run
  the patch on BAFU's full release and show what it changes there: see
  [Full release run](../community/ci/README.md#full-release-run).

## Patches

`uv run bafu-fixes list` prints the import fixes and patches of this checkout, with who
authorised each patch and the findings it answers; `list --json` gives the same to other
tools. How many datasets, exchanges and values each one changes in BAFU's release is
measured by the [Full release run](../community/ci/README.md#full-release-run) on every
change, and listed in its job summary.

Patches 0004–0008 change BAFU's own flow attributes and don't depend on 0010, which
only adds links. The Brightway Flows data in `src/bafu_community_fixes/data/` is used
with its author's permission (see
[the README there](../src/bafu_community_fixes/data/README.md)); rebuild it from public sources
with `uv run python scripts/build_brightway_flows_data.py`.

## Development

```sh
uv sync --locked
uv run pytest
BAFU_ECOSPOLD_DIR=path/to/bafu-2026-v1 uv run pytest   # also checks the full release
uv run ruff check && uv run ruff format
```

[CONTRIBUTING.md](../CONTRIBUTING.md#check-a-change) lists every check of the repository, the
tool's and the others, with the environment each needs.

## Where the tool came from

The tool was written in `sentier-dev/bafu-community-fixes` and brought into this repository with
its Git history ([#19](https://github.com/sentier-dev/sentier-bafu/issues/19)). Its package, its
commands and its XML extension namespace are unchanged. The
[file-disposition receipt](plans/bafu-community/integration-receipt.md) accounts for every file of
both repositories, and [migration-history](migration-history/README.md) keeps the README of each
as it was. The [reconciliation](../community/reconciliation.md) of 21 October 2026 compared the
findings with the patches by hand; the patches now name their findings themselves.

## Licences of the bundled files

The code and the documentation are under the MIT licence ([LICENSE](../LICENSE)). Three kinds of
files in the package keep their own terms:

- The EcoSpold 1 XSD files in `src/bafu_community_fixes/schemas/ecospold1/` are under the
  EcoSpold Public License 1.0 (see their file headers and
  [README](../src/bafu_community_fixes/schemas/ecospold1/README.md)).
- The Brightway Flows data in `src/bafu_community_fixes/data/` is under the Open Database
  License 1.0, not MIT (see [its README](../src/bafu_community_fixes/data/README.md)).
- The Rubik font embedded in run reports is under the SIL Open Font License 1.1
  ([Rubik-OFL.txt](../src/bafu_community_fixes/report_assets/Rubik-OFL.txt)).
