# Patch and build

Every change that is proposed here is applied to a copy of BAFU's release, checked and built on GitHub, where anyone can follow it. This is the last build, as it happened.

<!-- generated: last-run -->

## Builds and tags

A build is one run of the steps above: BAFU's release with the import fixes and the community patches of that day applied, checked, and written as files for LCA tools. It is a convenience for users who need a change now. The main purpose of this workspace is the [feedback to BAFU](feedback.md).

A community patch is not BAFU's correction. BAFU decides what it changes in its own releases.

GitHub makes a build when a change to the patch tool or to the build is accepted, once a month, and when a maintainer asks for one. The build at the top of this page is the last of those, also when it failed. Nothing in it is written by hand: the numbers come from the record the build kept, and the lines are the lines it printed.

Most builds are only looked at. A maintainer gives a tag to the build that others should use. The build is then made again for that tag and kept under the tag: its files for LCA tools, the record of changes, and its manifest with checksums and counts.

<!-- generated: build-files -->

**Downloads.** A file is offered here only where a tagged build holds those very bytes. A click on it first shows BAFU's Terms of Use in short, and the file comes only when you accept them; nothing about the click is recorded. The page of the tag on GitHub lists the same files, with the terms at the top. A build without a tag keeps no file: its files stay on the machine that made it.

## Before you share a build

Treat every build as *Modified Data* under BAFU's Terms of Use, whether or not it contains community patches. [Data and terms](../docs/terms-of-use.md) lists what a copy must carry when it is passed on, including BAFU's credit, the label *Modified Data* and the list of changes.

The files that the build writes for Brightway, openLCA, ILCD and SimaPro carry BAFU's credit, the label *Modified Data* and the list of changes. So does the copy in BAFU's own format, ecoSpold v1, that the build packs: every dataset in it carries the label and the credit, at the start of its comment and in a field of its own.

The patch tool alone does less. It records on each dataset which steps changed it, and its report lists the changes. It does not add BAFU's credit or the label *Modified Data* to the ecoSpold files it writes. Add both before you pass on files that only the patch tool wrote.

On what basis the full inventory may be passed on is discussed in [#1](https://github.com/sentier-dev/sentier-bafu/issues/1).

## Build the database and the files

You need [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/), a tool that installs Python programs. BAFU's Terms of Use apply to the files that the run downloads: read [data and terms](../docs/terms-of-use.md) first.

One command runs everything that the build at the top of this page shows:

```sh
git clone https://github.com/sentier-dev/sentier-bafu.git
cd sentier-bafu
uv sync
uv run --no-project --python 3.12 python scripts/build_release.py release latest output/release-run
```

- It writes the patched copy as files for Brightway, openLCA, ILCD and SimaPro, and again in BAFU's own format, ecoSpold v1. It reads each file back. [docs/exports.md](../docs/exports.md) says what each file holds and what was checked.
- It checks both databases and compares them. Each exchange that differs and each score that moves is traced to an import fix or a patch.
- It builds a Brightway database of BAFU's release and one of the patched copy. The second is named `bafu-2026-v1-patched` and labelled *Modified Data*, so that nobody takes it for BAFU's release.
- It writes a manifest: checksums, counts, and for each patch its author, the person who authorised it and the numbers of the datasets it changed. The manifest holds no inventory.

Everything is written to the folder `output/release-run`. That folder holds BAFU's inventory: keep it on your machine. The command needs about 3 GB of memory. It downloads two Sentier tools at fixed versions, and 37 MB of flow lists and impact methods.

## What works today

**Works:** the import fixes and the community patches can be applied to the files of BAFU:2026 v1. The result is a patched copy of the release in BAFU's file format (ecoSpold v1), with a report of what each step changed. From that copy, one command of this repository builds a Brightway database, checks it, compares it with a database of BAFU's release, and writes files for Brightway, openLCA, ILCD and SimaPro, and the patched copy again as ecoSpold v1. Each file is read back. The files for Brightway, openLCA and SimaPro are compared with the database exchange by exchange. In the ILCD file the datasets are counted. The ecoSpold v1 files are compared with the files the patches were applied to: nothing differs but the label and the credit.

**Downloads:** from a tagged build, after a question that asks you to accept BAFU's Terms of Use. **Not checked yet:** no file has been opened in openLCA or in SimaPro; the checks read the files with separate programs.

The steps, from the files that an LCA tool can open back to BAFU's files:

| Step | What happens | State |
|---|---|---|
| 7. Exports | Files for Brightway, openLCA, ILCD and SimaPro are written, and the patched copy again as ecoSpold v1, with BAFU's credit, the label *Modified Data* and the list of changes. Each file is read back. | Works on your own machine and in the checks of this repository. A tagged build keeps the files, and this page offers them after asking you to accept BAFU's terms. |
| 6. Checks | Each database is checked: the datasets and exchanges are counted, every input must be linked to its supplier, and every score is computed. The two databases are then compared, and each difference is traced to an import fix or a patch. | Works |
| 5. Brightway database | Two Brightway databases are built, with the EF 3.1 impact methods: one of BAFU's release and one of the patched copy. | Works |
| 4. Elementary flows | BAFU's elementary flows are linked to the flows that the impact methods use. The Brightway build does this with the Sentier mappings. Patch 0010 does it with links to Brightway Flows, and the build can follow those links too. A flow that names a country, such as *Water, CH*, takes the factor of that country where a method has one. | Two ways exist, and the build can use either. Measured on BAFU's release, the links of patch 0010 reach more flows (2,677 of 2,679, against 2,566), but 165 flows lose a factor, which moves the scores of most datasets in particulate matter, freshwater eutrophication, ecotoxicity and land use, nearly all of them downwards. The Sentier mappings stay the build's linking until those flows have factors. |
| 3. Community patches | The community patches are applied one after the other. | Works |
| 2. Import fixes | The preparations that every reader of the files needs are applied and recorded. | Works |
| 1. BAFU's release | The ecoSpold v1 files of BAFU:2026 v1 are downloaded and checked against a known checksum. Nothing is changed. | Works |

## Community patches

Changes to the data, applied one after the other. The list names for each patch what it does, the finding it answers, its author and the person who authorised it.

<!-- generated: patch-table -->

A patch that answers a finding is shown on that finding's page. Some patches answer no finding: they correct attributes of elementary flows, such as CAS numbers, names and compartments, or link elementary flows to the Brightway Flows project.

## Import fixes

Preparations that every reader of the files needs, such as schema repairs, unique exchange numbers and valid location codes. They are always applied, before any patch, and they are recorded on the datasets they change.

To apply the import fixes and the patches without building a database:

```sh
uv run bafu-fixes list
uv run bafu-fixes run latest output/ --strict --report output/report.html
```

- `list` shows the import fixes and the community patches.
- `run latest output/` downloads the files of BAFU:2026 v1, checks the download, applies the import fixes and the patches, and writes the patched files to the folder `output/`.
- `--strict` checks the files against the ecoSpold v1 schema after the import fixes and after each patch.
- `--report` writes a report that opens in a web browser. It lists each step with its author and the person who authorised it, and it shows what the step changed.

`uv run bafu-fixes-tui` offers the same run as a menu in the terminal: you choose the options, tick the patches and press Run.

## BAFU's release

Everything starts from the ecoSpold v1 files of BAFU:2026 v1. The patch tool downloads them and checks the download against a known checksum. Nothing is changed in this step.

The Brightway installer of this repository builds a Brightway database from BAFU:2026 v1 without the community patches, together with the EF 3.1 impact methods. It is the second package of this repository beside the patch tool, and it is the code of [sentier-brightway](https://github.com/sentier-dev/sentier-brightway), which was moved here with its history.

```sh
git clone https://github.com/sentier-dev/sentier-bafu.git
cd sentier-bafu
uv sync --extra brightway
uv run --no-sync sentier-brightway coverage
uv run --no-sync sentier-brightway db --project NAME
```

- `coverage` prints how many of BAFU's elementary flows are linked to an EF 3.1 flow.
- `db --project NAME` installs the database and the methods into a Brightway project with the name you give. `files --out FOLDER` writes the same build as plain files instead.

When you compare two builds, record for each one the release, the checksums of the inputs, the versions of the tools, and the flows that are not linked to an EF 3.1 flow.

[How builds are checked](../community/build-validation.md) reports what was checked on such a build. Those checks were made on a build of BAFU's release, not of the patched copy.
