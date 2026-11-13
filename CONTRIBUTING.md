# Contributing

This file is for people who change this repository: its records, its site or its scripts. To report a finding, repeat a measurement or propose a contribution, start on the site's [Take part](https://sentier-dev.github.io/sentier-bafu/take-part.html) page.

Open an issue or a pull request. For a contribution, name the BAFU release and the exact version of what you propose, and give public evidence, the steps to apply it beside BAFU's release, the results of the checks and the positions of the people involved. Start from the templates in [`community/templates/`](community/templates/). Keep objections on record.

## Check a change

Run these before you open a pull request. The [Documentation workflow](.github/workflows/pages.yml) runs the same commands.

```sh
python3 scripts/community.py check
uv run --no-project --python 3.12 --with markdown==3.7 python -m unittest discover -s community/tests
python3 scripts/build_checks.py community/templates/build-audit.json
```

- `check` validates every finding record, every contribution record and the list of community patches. It names the file and the rule that a record breaks.
- The unit tests need [uv](https://docs.astral.sh/uv/). Without the `markdown` package the tests of the site are skipped.
- `build_checks.py` checks a build audit. The template is an example of the format, not a measured build.

The tests of the export audit run apart, because they need other packages:

```sh
uv run --no-project --python 3.12 --with pandas==2.2.3 --with pyarrow==19.0.1 python -m unittest discover -s tests
```

## Build the site

```sh
uv run --no-project --python 3.12 --with markdown==3.7 python scripts/build_site.py --offline --out _site
python3 scripts/check_site.py _site
python3 -m http.server 8765 --bind 127.0.0.1 --directory _site
```

The build refuses to write anything while a record is invalid. `--offline` builds from the records alone; without it the build also reads the comment counts of the issues from GitHub. `check_site.py` checks every local link and refuses data files in the output. [site/README.md](site/README.md) describes the build.

## Add or change a record

- **A finding** is one file in [`community/findings/`](community/findings/README.md). A pull request that adds a finding adds that one file. Evidence is added with the commands `repeat`, `send`, `answer`, `fixed` and `close` of `scripts/community.py`; that README shows each of them. Nobody writes a status: it is computed from the evidence.
- **A contribution** is one file in `community/contributions/`. [community/workflow.md](community/workflow.md) describes the record, the steps and the comparison of two builds.
- **A community patch** is listed in [`community/patches.json`](community/patches.json), which `scripts/patches_snapshot.py` writes from the patch tool. Do not copy a patch into a finding record.

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

## Package work

Changes to the `bafu_community_fixes` package (import fixes, patches, report, TUI) run in
its locked environment on Python 3.14, separately from the checks above:

```sh
uv sync --locked
uv run pytest
uv run ruff check && uv run ruff format --check
```

These run on a small fixture. A pull request that touches the package is also run on
BAFU's full release, and its checks show what it changes there; see
[Full release run](community/ci/README.md#full-release-run) for what the job does and how
to run the same locally.

Start a patch from its finding with `uv run python scripts/new_patch.py NAME --finding F14`;
it creates the patch and its test, and there is no list of patches to update. How to write
the patch, record who authored and authorised it and add supporting data is explained in
the README under [Writing a patch](README.md#writing-a-patch). Leave `authorised_by` out
until the patch is approved; the pipeline runs it and warns. Rebuild the Brightway Flows data with its script rather than
editing it (see [its README](src/bafu_community_fixes/data/README.md)).

## Work done with an AI agent

These rules are stated in this repository today.

- Work done with an AI agent says so.
- People review and merge. A person reviews every pull request that adds or changes a record.
- A community patch names its author and the person who authorised it. The authorisation is a named person's recorded approval.
- Nobody is named as a reviewer or contact without their agreement.
- An agent reads [AGENTS.md](AGENTS.md) and [CONTEXT.md](CONTEXT.md) before it changes this repository.

## Data and confidential material

BAFU's data stays under BAFU's Terms of Use: read [docs/terms-of-use.md](docs/terms-of-use.md). Commit no inventory files. Keep restricted exports, generated datasets and confidential notes in local folders that are not committed: `.local/`, `inputs/`, `output/`, `cache/` and `notes/private/` are ignored.
