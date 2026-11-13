# The patched release

A convenience beside the feedback to BAFU: BAFU's release with import fixes and community patches applied, for users who need the corrections now. What this workspace is for is on the [findings](findings.md) page. Each patch names its author and who authorised it. Exports for Brightway, openLCA and SimaPro do not exist yet. The table says what works today.

## How it is built

| Step | What happens | Where | State |
|---|---|---|---|
| 1. BAFU's release | The ecoSpold v1 files are downloaded and checked against a known checksum. Nothing is changed. | [bafu-community-fixes](https://github.com/sentier-dev/bafu-community-fixes); it moves here with [#40](https://github.com/sentier-dev/sentier-bafu/pull/40) | works |
| 2. Import fixes | Preparations every reader needs: schema repairs, exchange numbers, location codes. Each is recorded. | bafu-community-fixes | works |
| 3. Community patches | Corrections with a named author and a named person who authorised them. Four answer a [finding](findings.md) (0001, 0002, 0003, 0011); seven correct elementary-flow attributes with Brightway Flows (0004–0010). | bafu-community-fixes | 11 patches |
| 4. Elementary flows | BAFU's flows are linked to EF 3.1 flows. | [sentier-mappings](https://github.com/sentier-dev/sentier-mappings), and patch 0010 | two routes exist; they are not reconciled |
| 5. Build | A Brightway database with the EF 3.1 methods. | [sentier-brightway](https://github.com/sentier-dev/sentier-brightway), with [sentier-methods](https://github.com/sentier-dev/sentier-methods) | works on BAFU's release; not yet on the patched one |
| 6. Checks | Row accounting and characterisation coverage. Importer parity and a score comparison with BAFU's published results are in review ([#38](https://github.com/sentier-dev/sentier-bafu/pull/38), [#36](https://github.com/sentier-dev/sentier-bafu/pull/36)). | [evidence](../community/build-validation.md) | on BAFU's release only |
| 7. Exports | Brightway, openLCA and SimaPro files, each with BAFU's credit, the *Modified Data* label and the list of changes. | planned | does not exist yet |

Today, sentier-brightway builds from BAFU's release through [sentier-importers](https://github.com/sentier-dev/sentier-importers) and [sentier-inventory](https://github.com/sentier-dev/sentier-inventory). Feeding it the patched release is the next step.

## Run what works today

Apply the import fixes and patches to BAFU's release:

```sh
git clone https://github.com/sentier-dev/bafu-community-fixes.git
cd bafu-community-fixes
uv sync
uv run bafu-fixes list
uv run bafu-fixes run latest output/ --strict --report output/report.html
```

The report lists every step, who wrote and authorised it, and shows the changes of the first ten datasets per step. The output is BAFU's file format with the patches applied.

Build the Brightway baseline from BAFU's release:

```sh
git clone https://github.com/sentier-dev/sentier-brightway.git
cd sentier-brightway
uv sync
uv run sentier-brightway coverage
uv run sentier-brightway files --out ../bafu-baseline
```

Record the manifest, release, input hashes and residual coverage of any build you compare.

## Before sharing a build

Every build is Modified Data under BAFU's Terms of Use, with or without patches. It carries BAFU's credit, the *Modified Data* label and the list of changes. On what basis the full inventory may be passed on is discussed in [#1](https://github.com/sentier-dev/sentier-bafu/issues/1). Check [data and terms](../docs/terms-of-use.md) first. This site holds findings and records; it has no inventory downloads.
