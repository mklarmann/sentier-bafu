# The whole path: from BAFU's release to exports and a manifest

One command runs everything that is built from BAFU's release in this repository, and CI
runs that command: for patches that are proposed (pull requests, on a made-up release and,
for the patch run, on the full release), for patches that are accepted (`main`), and for a
release (a tag). This page says what the command does, what stops it, what a release
publishes, and what is still done by hand. The steps themselves are described in
[From a release to a Brightway database](brightway-build.md),
[Exports of the patched release](exports.md) and
[Building a contribution beside the patched release](contribution-builds.md).

## The command

```sh
python3 scripts/build_release.py release path/to/bafu-2026-v1 output/run
python3 scripts/build_release.py release latest output/run     # the patch tool downloads the release
```

It needs Python 3.12 or newer, `uv` and `git`. Everything is written under the output
folder, which holds BAFU's inventory and stays local.

| Step | What it does | It fails when |
|---|---|---|
| provider build | BAFU's release as it is: adapter, importer, Brightway database `bafu-2026` with the EF 3.1 methods, audit | a step of the build stops, or the audit has an error. Findings on BAFU's own release are reported and do not fail |
| patched build | import fixes and community patches, then the same; database `bafu-2026-v1-patched`, marked Modified Data | a patch stops, the result is not valid EcoSpold 1, the audit has an error or a finding |
| written files | every written file against the EcoSpold 1 schema, and the file set against the run summary | a file is invalid, or the files are not the ones the summary describes |
| patch run | the table of the patch run, and what each patch matched now and in the previous release | the release is not a known one, a step stopped, or a patch changes nothing |
| comparison | patched against provider: every changed row and every moved score attributed to a step | a changed row or a moved score has no explanation |
| exports | Brightway package, openLCA JSON-LD, ILCD and SimaPro CSV of the patched database, each read back | a format can't be written, or reads back differently. The other formats are still written and checked |
| per contribution | build beside the patched release, comparison with it, exports | as above, for the contribution's own database |
| manifest | `manifest.json` from what the steps left behind | never; a failed step is recorded in it |

Every step runs in its own process. Its result, time and peak memory go into the manifest
and into `release.json`. A step that fails does not stop the run: the steps that can still
run do, a step whose input is missing is recorded as not run with the reason, and the
command ends with status 1. The folder `results/` holds the only files that may leave the
machine: the manifest, the run summary, the audits, the comparisons, the export step's own
manifest and the table of the patch run.

`--tag NAME` names the release in the manifest and makes the command fail if the run can't
be published. `--previous FILE` gives the manifest of the previous release (or an earlier
run summary) for the patch run check. `--contribution LAYER` and `--layers FOLDER` choose
the contributions; without either, every layer in `community/layers/` that names who
authorised it is built. A layer that nobody has authorised is listed as skipped; it is built
only when it is named with `--contribution`.
`--partial-release` is for a test release: that it is unknown and that patches find nothing
to change in it does not fail the run.

## What the runs of 13 November 2026 measured

On BAFU:2026 v1 (11,947 datasets, 420,063 exchanges), on macOS, each step in its own
process; peak memory is the largest resident size of the step's process tree:

| Step | Seconds | Peak memory | Result |
|---|---:|---:|---|
| provider build | 117 | 1.2 GB | 11,947 datasets, no unlinked exchange; audit passed with 3 findings, the strawberry scores of BAFU's release |
| patched build | 300 | 1.5 GB | 14 import fixes and 11 patches; 11,601 datasets changed; audit passed without a finding |
| written files | 7 | 0.1 GB | 11,947 files valid EcoSpold 1, and the ones the summary describes |
| patch run | under 1 | | every patch changed as much as in the earlier run |
| comparison | 3 | 1.1 GB | 188 of 420,063 exchange rows differ, each explained by a step; in each of 25 methods the scores of three datasets move, all three by patch 0001 |
| exports | 188 | 3.0 GB | four formats written, each read back without a difference |
| the whole command | 615 | 3.2 GB | |

A second run, in another checkout with the tools cloned and the pinned data downloaded
again, and through the workflow's own steps, gave the same patched files (fingerprint
`f08a6b23…0978`), the same importer tables, the same scores of every dataset in all 25
methods (byte for byte), the same comparison, and the same ILCD and SimaPro files. It took
978 s on the same machine under load. What differs between two runs is listed in
[Exports](exports.md).

## One run summary

`bafu-fixes run --summary FILE.json` writes one record that every later step reads:

| Who reads it | What it takes |
|---|---|
| the patch run check, on a pull request and on `main` | the release that was read, each step with its counts and its error, the fingerprint of the written files |
| the check of the written files | the number of files and their fingerprint |
| the Brightway build | keeps the file with the build and hands it on (`build.json`, `export.summary`) |
| the comparison | the fields each step changed, to explain changed rows of a step it has no entry for |
| the export step | every step that changed data, with rationale, author, authoriser and references, and for every changed dataset the steps that changed it |
| the manifest | all of the above, and the dataset numbers per patch |

It names a changed dataset by its file and its number, and holds no name, amount or other
value of the release.

## A patch that no longer finds its target

No patch says how many targets it expects. Patches 0001, 0002, 0004, 0005, 0008 and 0011
stop when a value they name is not as expected; none notices that a target is gone, and
0003, 0006, 0007, 0009 and 0010 never stop. So the check is made outside the patches, from
what each patch changed:

- the run summary counts, per patch, the datasets, exchanges and values it changed;
- the patch run check compares these with an earlier run: on a pull request the run of the
  base revision, on `main` and for a tag the manifest of the previous release;
- a patch that changes nothing fails the check, and the message says what it changed
  before; a patch that changes less or more than before is a warning for the reviewer;
- the manifest carries the comparison (`check_against_previous`).

What this can't see: a target that was never matched, and a patch that changes the right
number of things in the wrong place. For that a patch would have to declare what it
expects, in the patch: the release it was written for, and how many datasets and exchanges
it changes there (an `expects` argument of `@patch`, checked when the input is that
release), and each patch that names datasets would have to stop when one of them is absent
from a full release.

## Inputs whose declared unit is not their supplier's

The Brightway build links an input to its supplier by the supplier's number and takes the
amount as written. It reads the two unit labels and converts nothing. BAFU:2026 v1 has 660
technosphere inputs whose declared unit is spelled differently from the unit of the dataset
they are linked to: 619 mix `p` and `unit` (two spellings of one thing; the build writes
`unit` for both), 40 write `m3` for a dataset in `Nm3`, and one writes `kWh` for a dataset
in `MJ`. In the Brightway database that leaves 41 inputs whose unit label is not their
supplier's.

The last one is `Electricity, from natural gas` (FI), which takes 0.0156738 of
`Electricity, natural gas, at power plant` (FI). The build computes with 0.0156738 of that
dataset as it is. A tool that converts declared units would use 0.0564 (× 3.6). This is
finding F13: the supplier is modelled per kWh and labelled MJ.

Nothing converts that amount silently and nothing drops it:

- the **audit** lists every input whose declared unit is not its supplier's unit, sorted
  by the declared table (`scripts/release_build/export_labels.toml`) into the same quantity
  under another label, and another quantity. For the second kind it reads from the
  technosphere matrix the amount Brightway uses, and names the finding the input belongs
  to. One without a recorded finding is a finding of the audit, which fails a patched build;
- the **export** writes the amount the database holds, in the supplier's unit, with the
  declared unit in the exchange's comment, and lists the input in its manifest;
- the **manifest** carries the list (`declared_units`).

When a patch corrects such an input or its supplier, the recorded difference no longer
matches anything; the audit says so and the row in the table can go.

## A release

A person pushes a tag `patched-…` on a commit of `main`. The workflow runs the command
with `--tag`, and a second job, the only one with a token that can write, receives one
file, checks that it has exactly the shape of a manifest and that the run can be released,
and creates a GitHub Release that holds `manifest.json` and nothing else.

The export files are produced and read back in CI but are not published until a download
exists that asks for acceptance of BAFU's terms.

The manifest (`scripts/release_build/release_manifest.py`, format
`sentier-bafu/patched-release/2`). Its first ten fields are the manifest of a patched
release in format 1, unchanged:

| Field | Content |
|---|---|
| `tag`, `built` | the tag; when the patch run finished |
| `provider_release` | BAFU's release: address, SHA-256 of the archive, fingerprint of the files read, numbers of files, datasets and exchanges, and its id in `site/config.json`, which names the archive's SHA-256 |
| `tool` | `bafu-community-fixes`, its version, the commit it was run at |
| `options` | schema check, extensions, patches selected or skipped |
| `import_fixes` | per import fix: id, description, result, datasets and values changed |
| `patches` | per community patch: id, description, findings, author, authoriser, result (`applied`, `not needed`, `failed`), counts, and the numbers of the datasets it changed |
| `totals`, `output` | steps, datasets and values changed; number, size and fingerprint of the patched files |
| `status`, `problems`, `not_releasable` | whether every step ran; what keeps the run from being published |
| `steps` | each step with its result, seconds and peak memory |
| `check_against_previous` | per patch, what it changed now and in the previous release |
| `brightway` | both databases: name, label, audit result with errors and findings, counts, checksums of the audit and of the scores, tool commits and data pins |
| `comparison` | rows changed by step, scores moved by method and step, what has no explanation |
| `declared_units` | inputs whose declared unit is not their supplier's, with the amount used and the finding |
| `exports` | per export file its name, size and SHA-256; per format whether it was written and read back; `published: false` |
| `contributions` | each contribution built beside the patched release: id, name, database, layer checksum, what it changed, its audit, comparison and export files |

A run can't be released when: the patch tool did not complete or read an unknown release;
a step failed; a patch changed data and names nobody who authorised it; a patch names a
finding that has no record in `community/findings/`; an audit has an error, or the patched
build's audit a finding; the comparison did not pass; an export was not written or read
back differently.

The manifest names the author and the authoriser of a patch, and of a contribution's layer,
and nobody else. Who reported a finding and who answered for BAFU are in the run summary
and never reach the manifest.

The run summary itself leaves the machine in a public form. A patch may say which person
confirmed a problem for BAFU; what a workflow uploads or writes to its job summary says
`BAFU` and the date instead. One function does that
(`scripts/release_build/public_summary.py`): the release run writes `results/run-summary.json`
through it and holds back a kept file that still names who confirmed otherwise, the pull
request workflow uploads the public form of its two summaries, and both job summaries read
their input through it.

## In CI

[Automation](automation.md) describes every workflow of the repository. These two run the
build:

| Workflow | When | What |
|---|---|---|
| `full-release.yml` (Proposed patches) | a pull request that touches the patch tool, the build, the export or a layer; on request | the patch run on BAFU's full release for this revision and the base revision, with what the pull request changes and what each patch matched; and the whole path on a made-up release, with the build, export and adapter tests |
| `release-build.yml` (Release build) | a push to `main` that touches the same; on request; a tag `patched-*` | the command above on BAFU's full release, the job summary, the files of `results/` as an artifact; for a tag, the release with the manifest |

Two composite actions hold what both need: `.github/actions/bafu-release` installs the
patch tool and makes BAFU's release available (the tool's own download folder from the
Actions cache, the SHA-256 checked by the tool), and `.github/actions/patch-run` runs the
patch tool strictly and checks the written files. A new patch, a new contribution layer or
a new import fix needs no change to a workflow.

## What a release still needs from a person

1. Authorise each patch (`authorised_by` in the patch) and each contribution layer. After
   a change to a patch, `python3 scripts/patches_snapshot.py` writes the list of patches
   the site reads.
2. Push the tag. Protect tags `patched-*` in the repository settings so that only
   maintainers can.
3. When BAFU publishes a release: its address, checksum and fingerprint in
   `download.py`, and the units and compartments it adds in `export_labels.toml`. The run
   stops and names what is missing.
4. When a tool the build calls moves: its pin in `scripts/release_build/pins.toml`,
   together with a measured run.
5. A finding for every input the audit reports with a unit of another quantity than its
   supplier's.
6. Import of the export files into openLCA and SimaPro. No file has been imported into
   either; the checks read the files with independent parsers.
