<p><a href="https://www.d-d-s.ch/"><img src="site/assets/dds-logo.svg" alt="Départ de Sentier" width="200"></a></p>

# BAFU/UVEK inventory database: community findings

This workspace collects measured findings on the BAFU/UVEK life-cycle inventory database as feedback to BAFU, the Swiss Federal Office for the Environment (FOEN), which decides what it changes. People who work with the database record here what they measure in BAFU's data, and a second person is asked to repeat each measurement.

Beside the findings, this workspace holds contributions (mappings, models and variants, which keep their own name) and community patches for users who need a change now.

**The site: <https://sentier-dev.github.io/sentier-bafu/>.** It lists every finding with its status and its discussion, and it shows what was reported to BAFU and what BAFU answered. It is built from the records in this repository.

## Report a finding

You measured something in BAFU's data that looks wrong, or that you cannot explain. [Open a finding](https://github.com/sentier-dev/sentier-bafu/issues/new?template=bafu-data-finding.yml) with the dataset code, the release, what you measured and how, and why it looks wrong. You need a free GitHub account.

A maintainer adds a record to [`community/findings/`](community/findings/README.md). The finding gets the number of its issue and the status "Needs a second measurement".

## Repeat a measurement

This is the most useful help. Choose a finding with the status "Needs a second measurement" on the [findings page](https://sentier-dev.github.io/sentier-bafu/findings.html). Repeat the measurement on BAFU's release files, and write what you got in the finding's issue. A different result is as useful as the same one.

## Propose a contribution

A contribution is a mapping, a model, a rebuilt inventory or a method variant, with its evidence and the checks it must pass. A contribution never replaces BAFU's numbers. [Open a contribution](https://github.com/sentier-dev/sentier-bafu/issues/new?template=community-contribution.yml), and read [the contribution workflow](community/workflow.md).

## The patched copy

The patched copy is BAFU's release with import fixes and community patches applied. It is a convenience for users who need a change now. A community patch is not BAFU's correction.

The patch tool is in this repository. You need [git](https://git-scm.com/) and [uv](https://docs.astral.sh/uv/), a tool that installs Python programs. BAFU's Terms of Use apply to the files that a run downloads and to everything built from them: read [docs/terms-of-use.md](docs/terms-of-use.md) first.

```sh
git clone https://github.com/sentier-dev/sentier-bafu.git
cd sentier-bafu
uv sync
uv run bafu-fixes list
uv run bafu-fixes run latest output/ --strict --report output/report.html
```

- `list` shows the import fixes and the community patches, with the findings each patch answers and the person who authorised it.
- `run latest output/` downloads the files of BAFU:2026 v1 (about 37 MB, once), checks the download against a known checksum, applies the import fixes and the patches, and writes the patched files to the folder `output/`. A folder with BAFU's files works in place of `latest`.
- `--strict` checks the files against the EcoSpold 1 schema after the import fixes and after each patch.
- `--report` writes a report that opens in a web browser. It lists each step with its author and the person who authorised it, and it shows what the step changed.
- `--only` and `--skip` choose the patches. `uv run bafu-fixes-tui` offers the same run as a menu in the terminal.

One more command builds what follows from the patched files:

```sh
uv run --no-project --python 3.12 python scripts/build_release.py release latest output/release-run
```

It builds a Brightway database of BAFU's release and one of the patched copy, both with the EF 3.1 impact methods. It checks both and compares them. Then it writes the patched copy as files for Brightway, openLCA, ILCD and SimaPro, and reads each file back. The files carry BAFU's credit, the label *Modified Data* and the list of changes.

Its state:

- [`community/patches.json`](community/patches.json) lists the community patches with the findings they answer. A script writes it from the patches in `src/bafu_community_fixes/patches/`.
- The files for Brightway, openLCA, ILCD and SimaPro are written and read back on your own machine and in the checks of this repository. They are not offered for download: no download exists yet that asks for acceptance of BAFU's Terms of Use. This repository and the site hold no inventory files.
- No file has been opened in openLCA or in SimaPro yet. The checks read the files with separate programs.
- Of the build that a maintainer gave a tag, one file is kept: a manifest with checksums and counts. A local build can be compared with it.

Where to read on:

- [docs/patch-tool.md](docs/patch-tool.md): every option of the patch tool, how it works, what it writes and how to write a patch.
- [docs/release-build.md](docs/release-build.md): each step of the build, what stops it and what is kept of a tagged build.
- [docs/exports.md](docs/exports.md): what each file holds and what was checked.
- The site's [Patched copy](https://sentier-dev.github.io/sentier-bafu/patch-and-build.html) page lists the patches.

## Work on this repository

- [CONTRIBUTING.md](CONTRIBUTING.md): the commands that check a change, how to write a community patch, the house style for records, and the rules for work done with an AI agent.
- [community/README.md](community/README.md): the records and the documents that say how they are handled.
- [site/README.md](site/README.md): how the site is built from the records.
- [docs/automation.md](docs/automation.md): every workflow, and the path of a finding from the issue form to BAFU's answer and to a patched copy.
- [AGENTS.md](AGENTS.md): what an AI agent reads before it changes this repository.

## Documents

- [CONTEXT.md](CONTEXT.md): the glossary. It defines finding, contribution, community patch, patched copy and the other terms used here.
- [docs/adr/](docs/adr/): the architecture decisions, each with its status.
- [docs/terms-of-use.md](docs/terms-of-use.md): a short reading of BAFU's Terms of Use for people who work with the data. It is not legal advice.
- [docs/plans/bafu-community/](docs/plans/bafu-community/README.md): the plan for bringing the patch tool and this workspace together.

## Data, credit and licence

The code and the documentation in this repository are under the MIT licence ([LICENSE](LICENSE)). BAFU's data is under BAFU's Terms of Use. Findings quote dataset codes, names and single values. Text from BAFU's LCI reports is not reproduced.

Some files that come with the code keep their own terms:

- The EcoSpold 1 schema files in `src/bafu_community_fixes/schemas/ecospold1/` are under the EcoSpold Public License 1.0 (see [their README](src/bafu_community_fixes/schemas/ecospold1/README.md)).
- The Brightway Flows data in `src/bafu_community_fixes/data/` is under the Open Database License 1.0 (see [its README](src/bafu_community_fixes/data/README.md)).
- The Rubik font in the patch tool's reports ([Rubik-OFL.txt](src/bafu_community_fixes/report_assets/Rubik-OFL.txt)) and the site's Nunito font ([OFL.txt](site/assets/OFL.txt)) are under the SIL Open Font License 1.1.
- The Départ de Sentier logo (`site/assets/dds-logo.svg`) is by Sylvain Prevost, under CC BY 4.0 (see [site/README.md](site/README.md)).

This workspace is not run by BAFU. Nothing in it implies BAFU's endorsement.
