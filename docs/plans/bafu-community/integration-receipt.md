# Integration receipt: community-fixes into sentier-bafu (#19)

**Status: candidate cutover, to be confirmed with the community maintainers.** Nothing
here has been pushed, merged into `main` or announced. ADRs 0001–0004 remain `proposed`.

**Land it with a merge commit only (no squash, no rebase), otherwise one history is lost.**
A squash or rebase rewrites the integration merge into new commits that no longer have
`053c799` as an ancestor, and this receipt's checks then fail.

| | Repository | Ref | Commit | Tracked files |
|---|---|---|---|---|
| Workspace | `sentier-dev/sentier-bafu` | `main` | `a13bbbf2e4536e8de62eb8b4a9dd6a6a50faea41` | 64 |
| Community (authoritative on conflicts) | `sentier-dev/bafu-community-fixes` | `main` | `053c799a4d3e129747f47d6775ea88647c0bec78` | 65 |
| Integration merge | `codex/integrate-community-fixes-v2` | merge commit | `f310b96b9f6cdf4f3c4667bd9dd629b4c52e1c39` | 126 |

The merge commit has both source heads as parents (unrelated histories merged; no squash
and no file copy), so `git log` and `git blame` reach every original commit and author.
It holds only the resolution of the three paths both sources track; every adjustment
that makes the two coexist is a separate commit after it. The machine-readable
[receipt](integration-receipt.json) lists all 129 source files with their SHA-256 at
source and on the branch; the dated [source inventory](source-inventory-2026-10-23.json)
records both heads, every ref, PR, issue and release, and the delta since the planning
pins. The 13 October planning inventory, [source-inventory.json](source-inventory.json),
is kept unchanged as that record. Re-check everything from Git objects with:

```sh
python3 scripts/check_integration_receipt.py            # checks HEAD
python3 scripts/check_integration_receipt.py --rev <commit>
```

The Documentation workflow runs the same check on every push and pull request.

## Commits

| Commit | Subject |
|---|---|
| `f310b96` | Merge bafu-community-fixes 053c799 into sentier-bafu a13bbbf (#19) |
| `d4d20c3` | Move the registry unittest out of the community pytest root (#19) |
| `43a0023` | Keep the community ruff scope unchanged after the merge (#19) |
| `158b11b` | Pin the workspace tooling to Python 3.12 outside the package project (#19) |
| `a970bde` | Keep both original READMEs verbatim as migration history (#19) |
| `854d98a` | Compose the root README: add the review workspace and complete the licences (#19) |
| `22bf972` | Add the ODbL source and licence notice to the Brightway Flows data (#19) |
| `df20e8f` | CONTRIBUTING: add a short section for package work (#19) |
| (this commit) | Add the file-disposition receipt, its checker and the dated inventory (#19) |

## What changed since the planning pins

The planning inventory pinned workspace `87d14af` (52 files) and community `15bbfbb`
(64 files).

- **Workspace, 87d14af → a13bbbf:** the planning PR #27 added the plan folder (including
  `source-inventory.json`), four proposed ADRs, `CONTEXT.md` and `AGENTS.md` and rewrote
  the README's consolidation section. PRs #33 and #34 (merged 23 October) updated the
  findings ledger (F8 handled by patch 0011; F12–F17), added
  `community/reconciliation.{json,md}` with checks in `scripts/community.py` and
  `community/tests/test_records.py`, and closed #22. 12 files added, 4 modified, nothing
  removed. The README did not change after #27.
- **Community, 15bbfbb → 053c799:** `patches/p0011_flag_aggregated.py` added (#5, merged
  15 October); `import_fixes.py`, `README.md` and four test modules modified (#5 and #6;
  #6, merged 18 October, makes `renumber-exchanges` keep BAFU's exchange numbers and give
  only duplicates a dummy number, which changes XML output); nothing removed. PR #7 was
  closed unmerged. The community repository has only `main`, no tags and no releases. Its
  issues #1 and #2 stay open with their assignee (Laurenz Bougan); this branch does not
  transfer, close or comment on them. Community `main` is unchanged since the first
  integration attempt.
- **First attempt:** `codex/integrate-community-fixes` merged the same community head
  into workspace `14e718e` and was never pushed. This branch supersedes it on `a13bbbf`.

## Dispositions

Counts are computed from the file entries by the checker and compared with these.

| Source | Kept unchanged | Merged | Moved | Retired |
|---|---|---|---|---|
| Community (65) | 61 | 4 | 0 | 0 |
| Workspace (64) | 55 | 8 | 1 | 0 |

No file is retired or dropped. `LICENSE` is counted in both rows: the two MIT texts are
byte-identical, so one file serves both.

### At the merge: the three shared paths

| Path | Resolution |
|---|---|
| `LICENSE` | Byte-identical MIT text; kept. |
| `.gitignore` | Union. The community file is an unchanged prefix; the workspace adds `.local/`, `.env`, `inputs/`, `cache/`, `notes/private/`, `_site/` (its `__pycache__/`, `*.pyc`, `.venv/` and `output/` are already covered). No tracked file is ignored. |
| `README.md` | The community README, unchanged. |

Every other file of the merge tree is byte-identical to its source.

### After the merge

The checker allows a difference between the merge and the checked commit only if it is
declared here (and in the JSON): a changed file with a reason, an added file with a
reason, or the old path of a moved file.

| Changed path | Why |
|---|---|
| `.gitlab-ci.yml` | Registry test path (test move) and the Python 3.12 / --no-project pins. |
| `pyproject.toml` | ruff extend-exclude for the workspace paths. |
| `community/build-validation.md` | Python 3.12 / --no-project for audit_registry.py, with a note about the script's pinned docstring. |
| `community/ci/github-actions.yml` | --no-project --python 3.12 for the site build. |
| `site/README.md` | States the Python 3.12, no-project invocation. |
| `README.md` | Review workspace section and the completed License section. |
| `src/bafu_community_fixes/data/README.md` | ODbL §4.2b/4.3 notice after the unchanged permission paragraph. |
| `CONTRIBUTING.md` | Package work section. |
| `.github/workflows/pages.yml` | Integration receipt check, fetch-depth: 0. |

| Added path | Why |
|---|---|
| `registry-tests/test_audit_registry.py` | Destination of the moved registry unittest. |
| `docs/migration-history/README.md` | Index of the verbatim copies with full source SHAs and permalinks. |
| `docs/migration-history/bafu-community-fixes-053c799-README.md` | Verbatim community README at 053c799a4d3e129747f47d6775ea88647c0bec78. |
| `docs/migration-history/sentier-bafu-a13bbbf-README.md` | Verbatim workspace README at a13bbbf2e4536e8de62eb8b4a9dd6a6a50faea41. |
| `docs/plans/bafu-community/source-inventory-2026-10-23.json` | Dated inventory of both source heads, refs, PRs, issues and releases on 23 October 2026. |
| `.gitattributes` | Marks the generated receipt and inventory so GitHub collapses them in diffs. |
| `scripts/check_integration_receipt.py` | Checker for this receipt, run in the Documentation workflow. |
| `docs/plans/bafu-community/integration-receipt.md` | This receipt, generated from its JSON. |
| `docs/plans/bafu-community/integration-receipt.json` | Machine-readable receipt. |

Removed after the merge: `tests/test_audit_registry.py` (moved to `registry-tests/`).

Three root-level conventions met without sharing a path:

| Conflict | Resolution (community authoritative) |
|---|---|
| `tests/` is the community pytest root. The workspace's `tests/test_audit_registry.py` is a unittest module that imports pandas, so `uv run pytest` fails at collection. | Moved byte-identical to `registry-tests/`. |
| Community CI runs `uv run ruff check` and `ruff format --check` over the whole root; the workspace scripts and tests give 35 lint errors and 4 formatting differences under its config. | `[tool.ruff] extend-exclude` for those eight paths; ruff checks the same 43 Python files and `pyproject.toml` as at 053c799. The new checker follows the community style and is not excluded. |
| `pyproject.toml` and `.python-version` (3.14) now sit at the root: plain `uv run` syncs the package project, and `--no-project` alone still picks 3.14. | GitLab: `UV_PYTHON=3.12` and `--no-project`; documented commands gain `--no-project --python 3.12`. `scripts/audit_registry.py` is unchanged (its SHA-256 is pinned by `community/runs/bafu-export-audit.json`); a line beside its documented command says its docstring keeps the old one. |

## Changes to community files

- `README.md`: unchanged at the merge. After it, the *Review workspace* section and a
  complete License section (the community sentence named `schemas/ecospold1/`; the
  files are in `src/bafu_community_fixes/schemas/ecospold1/`). The text before the
  License section is unchanged byte for byte.
- `src/bafu_community_fixes/data/README.md`: ODbL §4.2b/4.3 notice added after the
  unchanged permission paragraph. Recorded as `merged`. The generated JSON's `license`
  field is left as generated.
- `pyproject.toml`: ruff `extend-exclude` only.
- `.gitignore`: workspace rules appended after the unchanged community rules.

## Preserved

Checked by `scripts/check_integration_receipt.py` or by the suites below:

- Package `bafu_community_fixes`, distribution `bafu-community-fixes` 0.1.0,
  `requires-python >=3.14`, commands `bafu-fixes` and `bafu-fixes-tui`, extension
  namespace `urn:bafu-community-fixes:extensions:1` (the whole `pyproject.toml` apart
  from the ruff exclude is compared with the community file).
- The 14 import fixes in their order, with `renumber-exchanges` as changed by #6; patches
  0001–0011 with their ids, decorators, provenance (`authored_by`, `authorised_by`,
  `confirmed_by`, references) and rationale; the warning for unauthorised patches.
- Report template, embedded Rubik font and its OFL, Sentier logo, TUI and styles,
  EcoSpold 1 XSDs and their README, `py.typed`.
- Brightway Flows data: 53 corrections and 26 exclusions, the crosswalk, the permission
  paragraph in `data/README.md`, and `scripts/build_brightway_flows_data.py`.
- `uv.lock` and `.github/workflows/ci.yml` (package job), and
  `.github/workflows/pages.yml` (site and contribution job) as separate jobs on separate
  Pythons.
- Findings F1–F17 (including withdrawals and the aggregation list), the reconciliation
  receipt for #22, contribution records C001 and C002, run records, templates, evidence
  index and all historical source links: these files are byte-identical.

## Verification

Run on 23 October 2026, macOS 26.5, uv 0.9.2; Python 3.14.7 for the package (from `uv sync --locked`, with `PYTHONPATH` set to the checkout's own `src/` and an assertion that the imported `bafu_community_fixes` lies inside it) and Python 3.12.12 with `--no-project` for the workspace checks. Heavy runs went through the host's `heavy_lock.sh`.

| Check | Before | Integration branch |
|---|---|---|
| `pytest` (locked env) | 106 passed, 1 skipped (community 053c799) | 106 passed, 1 skipped |
| `ruff check`, `ruff format --check` | passed | passed (same 43 Python files and `pyproject.toml`, plus the new checker) |
| `uv lock --check` | passed | passed |
| `scripts/community.py check` | passed (workspace a13bbbf): 2 records, reconciliation of 17 findings | passed, same output |
| `unittest discover -s community/tests` | 32 passed (workspace a13bbbf) | 32 passed |
| `build_checks.py community/templates/build-audit.json` | passed, summary `e0027dcd…` | passed, same summary |
| `build_site.py` (markdown 3.7) + `check_site.py` | 11 pages, links valid | 11 pages, links valid |
| Registry `unittest` (pandas 2.2.3, pyarrow 19.0.1) | 4 passed (`tests/`) | 4 passed (`registry-tests/`) |
| `scripts/check_integration_receipt.py` |  | passed |
| Relative links in the 32 current Markdown files |  | 70 relative links, none broken, none into a verbatim copy |
| pre-commit | not configured in either source | not configured |

The skipped test is `tests/test_bafu_release.py`, which needs the full provider archive (`BAFU_ECOSPOLD_DIR`); it passed in the full-release run below. The planning baseline at 15bbfbb was 91 passed and 1 skipped; the 15 extra tests at 053c799 come from #5 and #6.

Every commit of the branch was checked. At the merge `f310b96` the package suite stops at collection (`tests/test_audit_registry.py` needs pandas) and ruff reports the workspace scripts; `d4d20c3` fixes the first (106 passed, 1 skipped; ruff still reports the workspace paths) and `43a0023` the second. From `43a0023` on, every commit passes the package suite, ruff, `uv lock --check` and all workspace checks; the workspace checks pass at every commit.

### Fixture parity

The public fixture `tests/fixtures/raw_bafu.xml` (one dataset, three exchanges) was run through the pipeline at a clean 053c799 checkout and on this branch, with `xsd_check="every-step"` (`--strict`) and a report, with and without extensions. A driver also ran the pipeline with an extra probe patch that has no `authorised_by`, and with a probe patch that raises.

| Comparison | Result |
|---|---|
| Output XML, extensions on | byte-identical (SHA-256 `85627574…`) |
| Output XML, `--no-extensions` | byte-identical (`7313589f…`) |
| Extension fields (`bcf:importFix`, `originalNumber`) | identical (part of the XML) |
| `bafu-fixes list` (14 import fixes, 11 patches, authorisation) | byte-identical |
| Step order and per-step dataset/change counts | identical: 13 of 14 import fixes change the fixture (25 values); all 11 patches change 0 datasets on it |
| Run log, all fields | identical except start/finish times, source/destination paths and the software `git commit` |
| Report HTML | identical after masking timestamps, durations, paths and the `git commit` row (all four modes) |
| Unauthorised probe | warning callout and 2 "Not yet authorised" badges in both |
| Failing probe | report still written, run marked failed, in both |

### Full-release parity

Run locally on 23 October on the licensed BAFU:2026 v1 ecoSpold1 archive (SHA-256 `cbaeed4ae79c0be98709c854211cd72725d4f22f8b9b3fe334b7f343fca152f5`, 11,947 XML files), comparing community 053c799 with the first integration build (`738e385`), whose `src/`, `tests/` and `uv.lock` are byte-identical to 053c799. Settings: all patches, XSD check after import and every patch, report, with and without extensions.

- 11,947 datasets and 420,063 exchanges read; 11,601 datasets changed; 11,947 files written.
- Output XML byte-identical before and after on 11,947 of 11,947 files, with extensions (tree SHA-256 `2d1f6928924f5938f41b468492a0a8ee65685efe14fc54d73ccf95b09274da0c`) and without (`3c4a66d98732a2c36cc3cb5700ceef7d3b6776167f44e446774cb8eba305a2df`).
- Step order, per-step counts and per-step change hashes identical, for the 14 import fixes and the 11 patches. Patches (datasets / values / exchanges): 0001 3/3/3, 0002 25/25/25, 0003 1,289/1,289/0, 0004 1,354/3,542/3,542, 0005 237/1,106/1,106, 0006 206/534/534, 0007 117/129/129, 0008 25/25/25, 0009 4,200/64,825/64,825, 0010 7,727/587,494/293,747, 0011 40/40/0.
- No unauthorised-step warning; reports identical after masking timestamps, output path, duration and git commit.
- `tests/test_bafu_release.py` (enabled with `BAFU_ECOSPOLD_DIR`) passed before and after.

**Why it carries over to this branch:** compared with 053c799, `tests/`, `uv.lock` and `.python-version` here are byte-identical, and `src/` differs in exactly one file, `src/bafu_community_fixes/data/README.md`, which gained the ODbL notice. It is documentation: no code reads it (`data_file()` is called only for the corrections JSON and the crosswalk CSV). `pyproject.toml` differs only by the ruff exclude. There is no code change, so the run was not repeated. The per-file evidence (11,947 output hashes per mode) is kept locally because it is derived from the licensed archive; only these aggregate numbers are published. This shows that the integration does not change runtime behaviour; it does not show that each patch is scientifically correct on real data.

### Package contents

The wheel built from this branch has the same 59 files as one built from 053c799. Three differ: `bafu_community_fixes/data/README.md` (a package resource, so the ODbL notice ships in the wheel), `METADATA` (its long description is the README; all headers are equal) and `RECORD` (which hashes both). The sdist has the same 49 files; `README.md`, `pyproject.toml`, `PKG-INFO` and `src/bafu_community_fixes/data/README.md` differ.

### Checker mutation tests

Each mutation was made in a throwaway commit in a scratch clone, checked, and
discarded; the real branch was never changed.

| Mutation | Expected | Result | Checker message |
|---|---|---|---|
| (a) delete a community file after the merge (`patches/p0011_flag_aggregated.py`) | fail | failed | removed after the merge without a moved/retired entry; destination missing; tree not fully accounted; patch modules are not exactly 0001-0011 |
| (b) edit a kept file (`community/findings.md`) | fail | failed | changed after the merge but not declared; destination hash mismatch; kept unchanged but not byte-identical |
| (c) receipt names a merge commit with the same tree and parents that is not on the branch | fail | failed | merge commit … is not an ancestor of --rev (the only error) |
| (d) unknown disposition (`copied`) | fail | failed | disposition 'copied' is not one of (...); stated counts differ from the entries |
| (e) stated counts off by one | fail | failed | stated counts ... differ from the entries ... |
| (f) the real branch | pass | passed | All receipt checks passed. |

## Open questions for the maintainers

1. **Cutover SHA.** This candidate uses community `053c799` and workspace `a13bbbf`.
   Confirm with Chris Mutel and Laurenz Bougan that 053c799 is the cutover, and that the
   source repository stays active until they accept the migration (ADR 0001). Workspace
   PRs #36, #37 and #38 are open against `main`; if any merges first, redo the merge on
   the new `main`.
2. **Data permission.** On 13 October Chris Mutel gave permission for the Brightway Flows
   data to be used in bafu-community-fixes, with the pipeline's output following the BAFU
   Terms of Use instead of ODbL share-alike. Does that permission apply in sentier-bafu?
   This branch adds the ODbL notice but does not decide that question (ADR 0003, workspace
   issue #1). Nothing from that data is published on the site.

Not decided here: bringing the workspace scripts under ruff (a separate, visible change);
the composed README keeps the community title `bafu-community-fixes` while the name is
open (#25); custody of community issues #1 and #2 stays with the source maintainers.

## Rollback

Nothing is published, so rollback before landing is deleting the local branch. After the
pull request has landed on `main`:

- Revert the pull request's own merge commit, not the integration merge inside it:
  `git revert -m 1 <PR merge commit>`. This restores the `main` tree from before the
  pull request; both histories stay in the repository, and the community repository is
  untouched throughout.
- Landing it again later needs a revert of that revert: Git treats the reverted commits
  as already merged, so merging the branch again would bring nothing back.
- The previous pins stay usable: the package from
  `sentier-dev/bafu-community-fixes@053c799a4d3e129747f47d6775ea88647c0bec78`, and the site from
  `sentier-dev/sentier-bafu@a13bbbf2e4536e8de62eb8b4a9dd6a6a50faea41`.
- Keep the run receipts, this receipt and the issue links. Repository renaming (#25) and
  pipeline adoption are separately reversible.

## Every file

Generated from [integration-receipt.json](integration-receipt.json). Hashes are the
first 12 hex digits of SHA-256; the destination hash is read on the branch.

| Source | Path | Disposition | Destination | SHA-256 source → destination |
|---|---|---|---|---|
| community | `.github/workflows/ci.yml` | kept unchanged | same path | `3d2371cbad13` |
| community | `.gitignore` | merged | same path | `929210f21bc2 → b81a179589ca` |
| community | `.python-version` | kept unchanged | same path | `a876e0b10411` |
| community | `LICENSE` | kept unchanged | same path | `3778c928d02a` |
| community | `README.md` | merged (verbatim copy: `docs/migration-history/bafu-community-fixes-053c799-README.md`) | same path | `7785080ad71f → ce4872bb0298` |
| community | `pyproject.toml` | merged | same path | `3ab7a0b44c97 → a8f9221f5e90` |
| community | `scripts/build_brightway_flows_data.py` | kept unchanged | same path | `e3dbece69230` |
| community | `src/bafu_community_fixes/__init__.py` | kept unchanged | same path | `079649a7973a` |
| community | `src/bafu_community_fixes/brightway_flows.py` | kept unchanged | same path | `094198bf3644` |
| community | `src/bafu_community_fixes/changes.py` | kept unchanged | same path | `c9c1424a313b` |
| community | `src/bafu_community_fixes/cli.py` | kept unchanged | same path | `394b0e42b153` |
| community | `src/bafu_community_fixes/compliance.py` | kept unchanged | same path | `43a5f59d40e8` |
| community | `src/bafu_community_fixes/data/README.md` | merged | same path | `1f6d0cbb789e → c70c762c3730` |
| community | `src/bafu_community_fixes/data/__init__.py` | kept unchanged | same path | `d20b20c375cc` |
| community | `src/bafu_community_fixes/data/brightway-flows-corrections-bafu-2026-v1.json` | kept unchanged | same path | `107582860aae` |
| community | `src/bafu_community_fixes/data/brightway-flows-crosswalk-bafu-2026-v1.csv` | kept unchanged | same path | `e9985eedbe6f` |
| community | `src/bafu_community_fixes/download.py` | kept unchanged | same path | `eb1ff4b0c878` |
| community | `src/bafu_community_fixes/import_fixes.py` | kept unchanged | same path | `ea0f3def3a31` |
| community | `src/bafu_community_fixes/models.py` | kept unchanged | same path | `2407b2e33fea` |
| community | `src/bafu_community_fixes/patches/__init__.py` | kept unchanged | same path | `a56469d8eef9` |
| community | `src/bafu_community_fixes/patches/p0001_strawberry_polyethylene_disposal.py` | kept unchanged | same path | `2bb74cb104cf` |
| community | `src/bafu_community_fixes/patches/p0002_supplier_locations.py` | kept unchanged | same path | `79b13e9b7706` |
| community | `src/bafu_community_fixes/patches/p0003_flag_not_maintained.py` | kept unchanged | same path | `13a12931a4ed` |
| community | `src/bafu_community_fixes/patches/p0004_flow_cas_numbers_added.py` | kept unchanged | same path | `c03eeeee2e77` |
| community | `src/bafu_community_fixes/patches/p0005_flow_cas_numbers_replaced.py` | kept unchanged | same path | `a697a0d7014b` |
| community | `src/bafu_community_fixes/patches/p0006_flow_cas_numbers_removed.py` | kept unchanged | same path | `cf74257e7432` |
| community | `src/bafu_community_fixes/patches/p0007_flow_names.py` | kept unchanged | same path | `29f8774f52a4` |
| community | `src/bafu_community_fixes/patches/p0008_flow_compartments.py` | kept unchanged | same path | `272718335f43` |
| community | `src/bafu_community_fixes/patches/p0009_consistent_cas_numbers.py` | kept unchanged | same path | `0cb08a6965b6` |
| community | `src/bafu_community_fixes/patches/p0010_brightway_flows_links.py` | kept unchanged | same path | `f37bbc250616` |
| community | `src/bafu_community_fixes/patches/p0011_flag_aggregated.py` | kept unchanged | same path | `e3049409ab45` |
| community | `src/bafu_community_fixes/pipeline.py` | kept unchanged | same path | `58ea1c9bca6c` |
| community | `src/bafu_community_fixes/progress.py` | kept unchanged | same path | `f53b5f3071be` |
| community | `src/bafu_community_fixes/py.typed` | kept unchanged | same path | `e3b0c44298fc` |
| community | `src/bafu_community_fixes/registry.py` | kept unchanged | same path | `ebc4c8a780e0` |
| community | `src/bafu_community_fixes/report.py` | kept unchanged | same path | `f18ae320ea6c` |
| community | `src/bafu_community_fixes/report_assets/Rubik-OFL.txt` | kept unchanged | same path | `5237f9509bd6` |
| community | `src/bafu_community_fixes/report_assets/Rubik-VariableFont_wght.ttf` | kept unchanged | same path | `c64f09f2590f` |
| community | `src/bafu_community_fixes/report_assets/__init__.py` | kept unchanged | same path | `e3b0c44298fc` |
| community | `src/bafu_community_fixes/report_assets/sentier-logo.svg` | kept unchanged | same path | `7edd73c181a1` |
| community | `src/bafu_community_fixes/schemas/__init__.py` | kept unchanged | same path | `e3b0c44298fc` |
| community | `src/bafu_community_fixes/schemas/ecospold1/EcoSpold01DataTypes.xsd` | kept unchanged | same path | `780b626010b0` |
| community | `src/bafu_community_fixes/schemas/ecospold1/EcoSpold01Dataset.xsd` | kept unchanged | same path | `1139b6a25818` |
| community | `src/bafu_community_fixes/schemas/ecospold1/EcoSpold01FlowData.xsd` | kept unchanged | same path | `a481f78031cf` |
| community | `src/bafu_community_fixes/schemas/ecospold1/EcoSpold01MetaInformation.xsd` | kept unchanged | same path | `06179033857f` |
| community | `src/bafu_community_fixes/schemas/ecospold1/README.md` | kept unchanged | same path | `cace330de035` |
| community | `src/bafu_community_fixes/templates/__init__.py` | kept unchanged | same path | `e3b0c44298fc` |
| community | `src/bafu_community_fixes/templates/report.html.j2` | kept unchanged | same path | `06f4b93d2e48` |
| community | `src/bafu_community_fixes/tui.py` | kept unchanged | same path | `2aa8fa73859d` |
| community | `src/bafu_community_fixes/tui.tcss` | kept unchanged | same path | `f4e7782857c3` |
| community | `src/bafu_community_fixes/xml.py` | kept unchanged | same path | `b4bf4d9a92a5` |
| community | `src/bafu_community_fixes/xsd.py` | kept unchanged | same path | `0e332126560d` |
| community | `tests/conftest.py` | kept unchanged | same path | `991af2858522` |
| community | `tests/fixtures/raw_bafu.xml` | kept unchanged | same path | `fc5845e349a5` |
| community | `tests/test_bafu_release.py` | kept unchanged | same path | `d158a4c3297e` |
| community | `tests/test_download.py` | kept unchanged | same path | `6fb6c1fd6898` |
| community | `tests/test_import_fixes.py` | kept unchanged | same path | `78472a928d47` |
| community | `tests/test_models.py` | kept unchanged | same path | `9b1616cd5e0f` |
| community | `tests/test_patches.py` | kept unchanged | same path | `e0c5a3703d8e` |
| community | `tests/test_pipeline.py` | kept unchanged | same path | `6a0de507b699` |
| community | `tests/test_report.py` | kept unchanged | same path | `1f67f9ad7269` |
| community | `tests/test_tui.py` | kept unchanged | same path | `472c31598bbb` |
| community | `tests/test_xml.py` | kept unchanged | same path | `a4cab5836529` |
| community | `tests/test_xsd.py` | kept unchanged | same path | `e1e81aff9d75` |
| community | `uv.lock` | kept unchanged | same path | `3a21f5ee4665` |
| workspace | `.github/ISSUE_TEMPLATE/bafu-data-finding.yml` | kept unchanged | same path | `0a5619c7a703` |
| workspace | `.github/ISSUE_TEMPLATE/community-contribution.yml` | kept unchanged | same path | `69338e7f5575` |
| workspace | `.github/ISSUE_TEMPLATE/discussion.yml` | kept unchanged | same path | `55060f640c26` |
| workspace | `.github/PULL_REQUEST_TEMPLATE.md` | kept unchanged | same path | `aa968dd216c7` |
| workspace | `.github/workflows/pages.yml` | merged | same path | `7753928c5a09 → 544e815b1d11` |
| workspace | `.gitignore` | merged | same path | `e61075ad0b49 → b81a179589ca` |
| workspace | `.gitlab-ci.yml` | merged | same path | `656e89c0544a → af2ce1d6f94a` |
| workspace | `AGENTS.md` | kept unchanged | same path | `5825cea761bf` |
| workspace | `CONTEXT.md` | kept unchanged | same path | `797f54de3a1f` |
| workspace | `CONTRIBUTING.md` | merged | same path | `245d19cb8879 → 72c0e8966d9b` |
| workspace | `LICENSE` | kept unchanged | same path | `3778c928d02a` |
| workspace | `README.md` | merged (verbatim copy: `docs/migration-history/sentier-bafu-a13bbbf-README.md`) | same path | `daaf864b3c49 → ce4872bb0298` |
| workspace | `community/README.md` | kept unchanged | same path | `b6e38948ecfa` |
| workspace | `community/application-and-testing.md` | kept unchanged | same path | `3773460caf2f` |
| workspace | `community/build-validation.md` | merged | same path | `cfbaed68dbb3 → 1bc47f216442` |
| workspace | `community/ci/README.md` | kept unchanged | same path | `399fd6d83153` |
| workspace | `community/ci/github-actions.yml` | merged | same path | `a9a30956919d → b07e1a6a88a2` |
| workspace | `community/contributions/C001.json` | kept unchanged | same path | `65965d864744` |
| workspace | `community/contributions/C002.json` | kept unchanged | same path | `defba80c2779` |
| workspace | `community/findings.md` | kept unchanged | same path | `3bd13a46db72` |
| workspace | `community/hackathon-assessment.md` | kept unchanged | same path | `cf377168201b` |
| workspace | `community/mutel-mapping-review.md` | kept unchanged | same path | `38c94d21e668` |
| workspace | `community/recommendations/README.md` | kept unchanged | same path | `d83116d273a1` |
| workspace | `community/recommendations/tracker.json` | kept unchanged | same path | `37517e5f3dc6` |
| workspace | `community/reconciliation.json` | kept unchanged | same path | `11047a6c9c42` |
| workspace | `community/reconciliation.md` | kept unchanged | same path | `b98a4c0e8ebe` |
| workspace | `community/runs/bafu-export-audit.json` | kept unchanged | same path | `416fa3d8b070` |
| workspace | `community/runs/hackathon-roundtrip.json` | kept unchanged | same path | `cc29ac28360d` |
| workspace | `community/runs/mutel-mapping-audit.json` | kept unchanged | same path | `fc1450f27482` |
| workspace | `community/templates/build-audit.json` | kept unchanged | same path | `d744340fa523` |
| workspace | `community/templates/contribution.json` | kept unchanged | same path | `1ab8f08057a8` |
| workspace | `community/templates/intake.md` | kept unchanged | same path | `c2a894950220` |
| workspace | `community/templates/recommendation.md` | kept unchanged | same path | `67d11ed7cb3f` |
| workspace | `community/templates/run-summary.json` | kept unchanged | same path | `3611be5de189` |
| workspace | `community/tests/test_build_checks.py` | kept unchanged | same path | `684c244d8eb6` |
| workspace | `community/tests/test_flow_mapping_audit.py` | kept unchanged | same path | `1d74aeadd2d6` |
| workspace | `community/tests/test_records.py` | kept unchanged | same path | `db4d69996dec` |
| workspace | `community/workflow.md` | kept unchanged | same path | `0959ee7a4272` |
| workspace | `docs/adr/0001-consolidate-community-pipeline.md` | kept unchanged | same path | `94721c0138fa` |
| workspace | `docs/adr/0002-use-upstream-flow-decisions.md` | kept unchanged | same path | `17c3eca72791` |
| workspace | `docs/adr/0003-publish-static-review-snapshots.md` | kept unchanged | same path | `cccc39a5c378` |
| workspace | `docs/adr/0004-separate-review-and-provider-status.md` | kept unchanged | same path | `1eae3db0cfa0` |
| workspace | `docs/plans/bafu-community/README.md` | kept unchanged | same path | `f35f8b9573fb` |
| workspace | `docs/plans/bafu-community/migration.md` | kept unchanged | same path | `9e93e9521ca3` |
| workspace | `docs/plans/bafu-community/naming.md` | kept unchanged | same path | `f668d7a77aba` |
| workspace | `docs/plans/bafu-community/source-inventory.json` | kept unchanged | same path | `fb1477fd2e68` |
| workspace | `docs/terms-of-use.md` | kept unchanged | same path | `bed48b95c180` |
| workspace | `evidence/index.json` | kept unchanged | same path | `6cfd78bb0647` |
| workspace | `evidence/index.md` | kept unchanged | same path | `566c09be23f0` |
| workspace | `scripts/audit_flow_mapping.py` | kept unchanged | same path | `324ad2175777` |
| workspace | `scripts/audit_registry.py` | kept unchanged | same path | `1acb1be4021f` |
| workspace | `scripts/build_checks.py` | kept unchanged | same path | `5f39ed5a1704` |
| workspace | `scripts/build_site.py` | kept unchanged | same path | `7589295c7b2b` |
| workspace | `scripts/check_site.py` | kept unchanged | same path | `1bb00fda8887` |
| workspace | `scripts/community.py` | kept unchanged | same path | `a460506c4fe2` |
| workspace | `site/README.md` | merged | same path | `1659e3a5e8be → 4a9006b3d42f` |
| workspace | `site/assets/OFL.txt` | kept unchanged | same path | `ee9491ad3ea5` |
| workspace | `site/assets/dds-logo.svg` | kept unchanged | same path | `7450c8fb9991` |
| workspace | `site/assets/favicon-32x32.png` | kept unchanged | same path | `f0fd5467f05e` |
| workspace | `site/assets/nunito.ttf` | kept unchanged | same path | `bb55a5ca5c20` |
| workspace | `site/config.json` | kept unchanged | same path | `bace154f08e9` |
| workspace | `site/import.md` | kept unchanged | same path | `f9a5939224af` |
| workspace | `site/style.css` | kept unchanged | same path | `30823f1b0e0f` |
| workspace | `tests/test_audit_registry.py` | moved | `registry-tests/test_audit_registry.py` | `a661852e60a6` |
