<p><a href="https://www.d-d-s.ch/"><img src="site/assets/dds-logo.svg" alt="Départ de Sentier" width="200"></a></p>

# BAFU/UVEK inventory database: community findings

This workspace collects measured findings on the BAFU/UVEK life-cycle inventory database as feedback to BAFU, the Swiss Federal Office for the Environment (FOEN), which decides what it changes. People who work with the database record here what they measure in BAFU's data, and a second person is asked to repeat each measurement.

Beside the findings, this workspace holds contributions (mappings, models and variants, which keep their own name) and community patches for users who need a change before BAFU's next release.

**The site: <https://sentier-dev.github.io/sentier-bafu/>.** It lists every finding with its status and its discussion, and it shows what was reported to BAFU and what BAFU answered. It is built from the records in this repository.

## Report a finding

You measured something in BAFU's data that looks wrong, or that you cannot explain. [Open a finding](https://github.com/sentier-dev/sentier-bafu/issues/new?template=bafu-data-finding.yml) with the dataset code, the release, what you measured and how, and why it looks wrong. You need a free GitHub account.

A maintainer adds a record to [`community/findings/`](community/findings/README.md). The finding gets the number of its issue and the status "Needs a second measurement".

## Repeat a measurement

This is the most useful help. Choose a finding with the status "Needs a second measurement" on the [findings page](https://sentier-dev.github.io/sentier-bafu/findings.html). Repeat the measurement on BAFU's release files, and write what you got in the finding's issue. A different result is as useful as the same one.

## Propose a contribution

A contribution is a mapping, a model, a rebuilt inventory or a method variant, with its evidence and the checks it must pass. A contribution never replaces BAFU's numbers. [Open a contribution](https://github.com/sentier-dev/sentier-bafu/issues/new?template=community-contribution.yml), and read [the contribution workflow](community/workflow.md).

## The patched release

The patched release is BAFU's release with import fixes and community patches applied. It is a convenience for users who need a change before BAFU's next release. A community patch is not BAFU's correction.

Its state:

- The patch tool is in [bafu-community-fixes](https://github.com/sentier-dev/bafu-community-fixes). It applies the import fixes and the community patches to the files of BAFU:2026 v1 and writes a report of what each step changed.
- [`community/patches.json`](community/patches.json) lists the community patches with the findings they answer.
- Ready-made files of the patched release for Brightway, openLCA or SimaPro do not exist yet. This repository and the site hold no inventory files.

The site's [Patched release](https://sentier-dev.github.io/sentier-bafu/patched-release.html) page has the commands.

## Work on this repository

- [CONTRIBUTING.md](CONTRIBUTING.md): the commands that check a change, the house style for records, and the rules for work done with an AI agent.
- [community/README.md](community/README.md): the records and the documents that say how they are handled.
- [site/README.md](site/README.md): how the site is built from the records.
- [AGENTS.md](AGENTS.md): what an AI agent reads before it changes this repository.

## Documents

- [CONTEXT.md](CONTEXT.md): the glossary. It defines finding, contribution, community patch, patched release and the other terms used here.
- [docs/adr/](docs/adr/): the architecture decisions, each with its status.
- [docs/terms-of-use.md](docs/terms-of-use.md): a short reading of BAFU's Terms of Use for people who work with the data. It is not legal advice.
- [docs/plans/bafu-community/](docs/plans/bafu-community/README.md): the plan for bringing the patch tool and this workspace together.

## Data, credit and licence

The code and the documentation in this repository are under the MIT licence ([LICENSE](LICENSE)). BAFU's data is under BAFU's Terms of Use. Findings quote dataset codes, names and single values. Text from BAFU's LCI reports is not reproduced.

This workspace is not run by BAFU. Nothing in it implies BAFU's endorsement.
