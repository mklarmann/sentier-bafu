# Patched release

The patched release is BAFU's release with import fixes and community patches applied. It is a convenience for users who need a change before BAFU's next release. The main purpose of this workspace is the [feedback to BAFU](feedback.md).

A community patch is not BAFU's correction. BAFU decides what it changes in its own releases.

## What it contains

- **BAFU's release.** The ecoSpold v1 files of BAFU:2026 v1. The patch tool downloads them and checks the download against a known checksum. Nothing is changed in this step.
- **Import fixes.** Preparations that every reader of the files needs, such as schema repairs, unique exchange numbers and valid location codes. They are always applied, and they are recorded on the datasets they change.
- **Community patches.** Changes to the data, applied one after the other. The list below names for each patch what it does, the finding it answers, its author and the person who authorised it.

<!-- generated: patch-table -->

A patch that answers a finding is shown on that finding's page. Some patches answer no finding: they correct attributes of elementary flows, such as CAS numbers, names and compartments, or link elementary flows to the Brightway Flows project.

## What works today

**Works:** the import fixes and the community patches can be applied to the files of BAFU:2026 v1. The result is a copy of the release in BAFU's file format (ecoSpold v1), with a report of what each step changed.

**Does not exist yet:** ready-made files of the patched release for Brightway, openLCA or SimaPro. A Brightway database can be built from BAFU's release without the patches, but not yet from the patched release. This site offers no downloads of the data.

The steps from BAFU's files to files that an LCA tool can open:

| Step | What happens | State |
|---|---|---|
| 1. BAFU's release | The ecoSpold v1 files of BAFU:2026 v1 are downloaded and checked against a known checksum. Nothing is changed. | Works |
| 2. Import fixes | The preparations that every reader of the files needs are applied and recorded. | Works |
| 3. Community patches | The community patches are applied one after the other. | Works |
| 4. Elementary flows | BAFU's elementary flows are linked to the flows that the impact methods use. The Brightway build does this with the Sentier mappings. Patch 0010 does it with links to Brightway Flows. | Two ways exist. They do not agree yet. |
| 5. Brightway database | A Brightway database is built, with the EF 3.1 impact methods. | Works for BAFU's release. Not yet for the patched release. |
| 6. Checks | Row accounting and factor coverage are checked on the build. | Done on a build of BAFU's release only. |
| 7. Exports | Files for Brightway, openLCA and SimaPro are written, with BAFU's credit, the label *Modified Data* and the list of changes. | Does not exist yet. |

## Run it yourself

You need [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/), a tool that installs Python programs. BAFU's Terms of Use apply to the files that the run downloads: read [data and terms](../docs/terms-of-use.md) first.

```sh
git clone https://github.com/sentier-dev/bafu-community-fixes.git
cd bafu-community-fixes
uv sync
uv run bafu-fixes list
uv run bafu-fixes run latest output/ --strict --report output/report.html
```

- `list` shows the import fixes and the community patches.
- `run latest output/` downloads the files of BAFU:2026 v1, checks the download, applies the import fixes and the patches, and writes the patched files to the folder `output/`.
- `--strict` checks the files against the ecoSpold v1 schema after the import fixes and after each patch.
- `--report` writes a report that opens in a web browser. It lists each step with its author and the person who authorised it, and it shows what the step changed.

`uv run bafu-fixes-tui` offers the same run as a menu in the terminal: you choose the options, tick the patches and press Run.

## A Brightway database from BAFU's release

[sentier-brightway](https://github.com/sentier-dev/sentier-brightway) builds a Brightway database from BAFU:2026 v1 without the community patches, together with the EF 3.1 impact methods.

```sh
git clone https://github.com/sentier-dev/sentier-brightway.git
cd sentier-brightway
uv sync
uv run sentier-brightway coverage
uv run sentier-brightway db --project NAME
```

- `coverage` prints how many of BAFU's elementary flows are linked to an EF 3.1 flow.
- `db --project NAME` installs the database and the methods into a Brightway project with the name you give. `files --out FOLDER` writes the same build as plain files instead.

When you compare two builds, record for each one the release, the checksums of the inputs, the versions of the tools, and the flows that are not linked to an EF 3.1 flow.

[How builds are checked](../community/build-validation.md) reports what was checked on such a build. Those checks were made on a build of BAFU's release, not of the patched release.

## Before you share a build

Treat every build as *Modified Data* under BAFU's Terms of Use, whether or not it contains community patches. [Data and terms](../docs/terms-of-use.md) lists what a copy must carry when it is passed on, including BAFU's credit, the label *Modified Data* and the list of changes.

The patch tool records on each dataset which steps changed it, and its report lists the changes. It does not add BAFU's credit or the label *Modified Data*. Add both before you pass a copy on.

On what basis the full inventory may be passed on is discussed in [#1](https://github.com/sentier-dev/sentier-bafu/issues/1).
