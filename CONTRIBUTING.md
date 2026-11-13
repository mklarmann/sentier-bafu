# Contributing

This file is for people who change this repository: its records, its site or its scripts. To report a finding, repeat a measurement or propose a contribution, start on the site's [Take part](https://sentier-dev.github.io/sentier-bafu/take-part.html) page.

Open an issue or a pull request. For a contribution, name the BAFU release and the exact version of what you propose, and give public evidence, the steps to apply it beside BAFU's release, the results of the checks and the positions of the people involved. Start from the templates in [`community/templates/`](community/templates/). Keep objections on record.

## Check a change

Run the checks that fit your change before you open a pull request. This section is the one place that lists them. The workflows run the same commands, and a test compares the two lists. [docs/automation.md](docs/automation.md) says which workflow runs what.

The checks use three environments, and each keeps its own. All of them need [uv](https://docs.astral.sh/uv/).

- The records, the site and their tests need Python 3.12 and the `markdown` package. They run outside the package project, with `uv run --no-project --python 3.12`.
- The patch tool needs Python 3.14 and its locked environment, which `uv sync --locked` installs.
- The build of a Brightway database and of the exports makes its own environments from the versions pinned in `scripts/release_build/pins.toml`.

### Records, site and unit tests

```sh
uv run --no-project --python 3.12 python scripts/community.py check
uv run --no-project --python 3.12 --with markdown==3.7 --with pyyaml==6.0.2 python -m unittest discover -s community/tests
uv run --no-project --python 3.12 python scripts/build_checks.py community/templates/build-audit.json
uv run --no-project --python 3.12 --with pandas==2.2.3 --with pyarrow==19.0.1 python -m unittest discover -s registry-tests
uv run --no-project --python 3.12 --with markdown==3.7 python scripts/build_site.py --offline --out _site
uv run --no-project --python 3.12 python scripts/check_site.py _site
uv run --no-project --python 3.12 --with markdown==3.7 --with pyyaml==6.0.2 python community/tests/lifecycle_steps.py
```

- `check` validates every finding record and every contribution record, and it compares [`community/patches.json`](community/patches.json) with the patches in `src/bafu_community_fixes/patches/`. It names the file and the rule that a record breaks.
- The unit tests read frozen copies of the records, so that a real finding can move on without a test being edited. Without the `markdown` package the tests of the site are skipped.
- `build_checks.py` checks a build audit. The template is an example of the format, not a measured build.
- The tests in `registry-tests/` check the export audit. They need other packages, so they run apart.
- The site is built from the records alone and then checked: every local link, and no data file in the output.
- `lifecycle_steps.py` takes each step of a finding's life on a copy of the repository (a new record, a second measurement, a report, an answer, a correction, a withdrawal, a new release, a new patch) and runs the unit tests on the copy.

### The patch tool

```sh
uv sync --locked
uv run ruff check
uv run ruff format --check
uv run pytest
uv run python scripts/community.py check
rev="$(git log -1 --format=%H -- docs/plans/bafu-community/integration-receipt.json)"
uv run --no-project --python 3.12 python scripts/check_integration_receipt.py --rev "$rev"
```

- The tests run on a small made-up dataset. They need none of BAFU's data.
- The second `check` runs where the patch tool is installed. It compares `community/patches.json` with the patches as the tool itself lists them. The first one reads the patch files without the tool.
- The last two lines check the receipt that accounts for every file of the two repositories that were brought together here. The check needs the whole history (`git fetch --unshallow` in a shallow clone).

### The build, on a made-up release

These tests build a Brightway database and the exports from eight made-up datasets. They need none of BAFU's data. The first command clones [sentier-importers](https://github.com/sentier-dev/sentier-importers) and [sentier-brightway](https://github.com/sentier-dev/sentier-brightway) at their pinned versions into `output/tools` and downloads 37 MB of pinned flow lists and impact methods. The three variables belong to that command alone: with them set, the second command would build everything a second time.

```sh
RELEASE_BUILD_WHOLE_PATH=1 RELEASE_BUILD_TOOLS=output/tools RELEASE_BUILD_PINNED_DATA=output/pinned-data \
  uv run --no-project --python 3.12 python -m unittest discover -s release-build-tests -p test_whole_path.py
uv run --frozen --project output/tools/sentier-brightway --python 3.12 --extra testing python -m unittest discover -s release-build-tests
uv run --no-project --python 3.12 --with-requirements export-tests/requirements.txt pytest export-tests
uv run --no-sync python -m unittest discover -s release-build-tests -p test_adapter.py
```

### On BAFU's release

These commands download BAFU's release (about 37 MB) and check it against a known checksum. BAFU's Terms of Use apply to it and to everything built from it: read [docs/terms-of-use.md](docs/terms-of-use.md), and keep `output/` on your machine.

```sh
uv run --no-sync bafu-fixes run latest output/patched --strict --summary output/summary.json
uv run --no-sync python scripts/check_patched_release.py output/patched --summary output/summary.json
uv run --no-sync python scripts/full_release_table.py output/summary.json --check
uv run --no-project --python 3.12 python scripts/build_release.py release latest output/release-run
```

- The first three lines apply the import fixes and every community patch, check the files that were written, and print what each patch changed. A pull request that touches the patch tool runs them for its own version and for the version it starts from.
- The last line runs everything: a Brightway database of BAFU's release and one of the patched release, their checks and their comparison, the exports with a read-back of each file, and a manifest. It starts in an empty folder. [docs/release-build.md](docs/release-build.md) describes each step.

## Build the site

```sh
uv run --no-project --python 3.12 --with markdown==3.7 python scripts/build_site.py --offline --out _site
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

The build refuses to write anything while a record is invalid. `--offline` builds from the records alone; without it the build also reads the comment counts of the issues from GitHub. [site/README.md](site/README.md) describes the build.

## Add or change a record

- **A finding** is one file in [`community/findings/`](community/findings/README.md). A pull request that adds a finding adds that one file. Evidence is added with the commands `repeat`, `send`, `answer`, `fixed` and `close` of `scripts/community.py`; that README shows each of them. Nobody writes a status: it is computed from the evidence.
- **A contribution** is one file in `community/contributions/`. [community/workflow.md](community/workflow.md) describes the record, the steps and the comparison of two builds. A contribution that changes the inventory also has a file in [`community/layers/`](community/layers/README.md), which its record names.
- **A community patch** is one file in `src/bafu_community_fixes/patches/`, with its test. The next section says how to start one. Do not copy a patch into a finding record.

## Write a community patch

```sh
uv run python scripts/new_patch.py storage-pump-wind --finding F14
python3 scripts/patches_snapshot.py
```

The first command creates the patch and its test with the next free number. The patch names the finding it answers; a patch that answers no finding is started with `--no-finding`. [docs/patch-tool.md](docs/patch-tool.md#writing-a-patch) explains how to write the patch, how to name its author and the person who authorised it, and where supporting data goes. Leave `authorised_by` out until the patch is approved: the tool applies the patch and marks it as not yet authorised, and a release is not published while such a patch changes data.

The second command writes [`community/patches.json`](community/patches.json) from the patches in the repository. The site reads the patches from that file. Never edit it by hand: `check` fails while it differs from the patches.

A pull request for a patch holds three files: the patch, its test and `community/patches.json`. Its checks run the patch on BAFU's release and show what it changes there.

The Brightway Flows data in `src/bafu_community_fixes/data/` is rebuilt with its script, not edited (see [its README](src/bafu_community_fixes/data/README.md)).

## House style for records

Records are published: the site shows their text, and the JSON files carry it. New records follow this style. Older records are brought in line when they are next edited.

### Title of a finding

1. The form is `<what it is about>: <what the data says>`. The subject comes first, in plain words.
2. One observation per title. A second observation is a second finding.
3. At most 80 characters.
4. The title states what was observed. It names no cause, no remedy and no status.
5. No dataset codes. The record lists the datasets, and the site shows them under the title.
6. At most two numbers, as plain decimals with a unit.
7. A question mark only when the finding is a question to BAFU.
8. Sentence case, no full stop.

Example, the title of F2: `Refrigerant R134a: HFC, HCFC and CFC emissions exactly 10× the ecoinvent process`.

### Observation

1. Only the observation. BAFU's answer, the community patch, the history and the next step have their own fields.
2. Four parts, in this order, in full sentences: what the data says (value, unit, where); what it was compared with; what it affects, if known; the question to BAFU, if there is one.
3. One idea per sentence. At most about 120 words. Longer material goes into the notes.
4. Several datasets: one value per dataset with its location. Do not write values as a slashed row.
5. Names of datasets and flows in code style, with the dataset code in brackets after the name.
6. Present tense for the data ("The dataset declares …"), past tense for what was done.
7. Say what was not measured.
8. Quote dataset codes, names and single values. Never quote text from BAFU's LCI reports.

### Next step

One or two sentences that start with what happens next, for example: "A second person repeats the measurement on BAFU's release files. Then the finding is reported to BAFU." Name no label and no internal state.

### Title of a contribution

A noun phrase that names the thing proposed, at most 90 characters. No verb of intent such as "validate" or "integrate", and no person's name.

### Dates, numbers and spelling

- Date fields hold `2026-10-12`. In text, write "12 October 2026".
- Numbers are plain decimals with a unit: "0.00043 tkm/kg", not "4.3E-4". Write "5%" without a space. Write CO₂, SO₂, m³ and Nm³.
- British spelling: authorised, characterisation, behaviour, licence (the noun).
- Full sentences. No "we" and no "our": a record does not say who "we" is.

### Words

| For | Write |
|---|---|
| Where a finding stands | its **status**, in the words the site shows, such as "Needs a second measurement" |
| A community change to the files | a **community patch** ("patch 0001") |
| A preparation that every reader of the files needs | an **import fix** |
| What BAFU publishes to put something right | a **correction** ("corrected by BAFU") |
| The whole | **the database** (first mention: the BAFU/UVEK life-cycle inventory database) |
| One process in it | a **dataset** |
| A release | **BAFU:2026 v1** |
| Repeating a measurement | a **second measurement**; to **repeat the measurement** |
| Telling BAFU | to **report to BAFU** |
| What BAFU said | **BAFU's answer** |

These words are not used in a record or on the site: stage, triage, ledger, layer, upstream, provider, candidate, and fix or fixed for anything but an import fix.

### People and sources

- BAFU's answer is summarised, never quoted. It is attributed to BAFU and names no person. Do not mention private correspondence.
- A record names a person only as the reporter, as the person who repeated a measurement, or as the author or the authoriser of a community patch.
- Record text is Markdown. It holds no raw HTML, no image and no heading, and every link is a full `https://` address. `check` refuses anything else.

## Work done with an AI agent

These rules are stated in this repository today.

- Work done with an AI agent says so.
- People review and merge. A person reviews every pull request that adds or changes a record.
- A community patch names its author and the person who authorised it. The authorisation is a named person's recorded approval.
- Nobody is named as a reviewer or contact without their agreement.
- An agent reads [AGENTS.md](AGENTS.md) and [CONTEXT.md](CONTEXT.md) before it changes this repository.

## Data and confidential material

BAFU's data stays under BAFU's Terms of Use: read [docs/terms-of-use.md](docs/terms-of-use.md). Commit no inventory files. Keep restricted exports, generated datasets and confidential notes in local folders that are not committed: `.local/`, `inputs/`, `output/`, `cache/` and `notes/private/` are ignored.
