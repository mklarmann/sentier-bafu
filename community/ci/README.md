# Checks in CI

[docs/automation.md](../../docs/automation.md) describes every workflow of the repository, and [CONTRIBUTING.md](../../CONTRIBUTING.md#check-a-change) lists the commands of every check for a run on your own machine. This page describes the run on BAFU's full release in more detail.

- [Checks](../../.github/workflows/checks.yml) validates the records, runs the unit tests, builds the site from the records and checks its links, and runs the patch tool's lint and tests. It needs none of BAFU's data. Pull requests never deploy.
- [Site](../../.github/workflows/pages.yml) publishes the generated `_site/` folder, and nothing else, through GitHub Pages, once a repository administrator has enabled **Settings → Pages → Source: GitHub Actions**.

The supplied `github-actions.yml` is a standalone template of the record checks for a copy of the records elsewhere; this repository does not run it. The portable `.gitlab-ci.yml` provides the record checks and the publication of the site for a GitLab mirror.

## Full release run

Two workflows run the patch tool and everything built from its output on BAFU's full
release. The [Checks workflow](../../.github/workflows/checks.yml) tests the tool on a small
fixture; these show what a patch does to the release.

- [Proposed patches](../../.github/workflows/full-release.yml), for each pull request that
  touches the patch tool, the build, the export or a contribution layer: the import fixes
  and every patch on the full release, for the pull request's revision and for the revision
  it starts from; and the whole path on a made-up release.
- [Release build](../../.github/workflows/release-build.yml), for each such change on
  `main` (patches accepted), on request, and for a tag `patched-…`: the whole path on the
  full release, from the provider build to the exports and the manifest. A tag publishes
  the manifest, and nothing else. See [The whole path](../../docs/release-build.md).

Both get the release as the tool does: `bafu-fixes run latest` downloads it once, checks its SHA-256, and the Actions cache keeps it under that checksum (one composite action, `.github/actions/bafu-release`, for every job). The patch run uses `--strict`, which checks against the EcoSpold 1 schema after the import and after every patch, and then checks the files that were written. It fails if

- a step stops (a patch stops when its target is not as expected) or the result is not valid EcoSpold 1;
- the files read are not a release the tool knows (`download.FINGERPRINTS`);
- a patch changes nothing, so its target was not there.

Its job summary (the *Summary* page of the check) lists every step with its author, who authorised it, and the datasets, exchanges and values it changed. A patch that is not yet authorised is marked. On a pull request the job also runs the base revision, and the summary starts with what the pull request changes: new and removed steps, the difference per step, and how many files of the patched release differ.

**What each patch matched.** No patch says how many targets it expects. The summary therefore lists, for every patch, what it changed beside what it changed in an earlier run: the base revision on a pull request, the previous release on `main` and for a tag. A patch that changed something before and nothing now fails the check and says what it changed before; one that changed less, or more, is marked for the reviewer.

Nothing from the inventory is published. The job summaries and the uploaded files hold counts, checksums, dataset numbers and codes, names and single scores. The release, the patched release, the Brightway databases, the export files and the HTML report, which quotes the data, stay on the runner.

A new patch needs no change to a workflow: patches are found in `src/bafu_community_fixes/patches/`. Neither does a new contribution layer: layers are found in `community/layers/`.

Run the same locally with the commands under "On BAFU's release" in [CONTRIBUTING.md](../../CONTRIBUTING.md#on-bafus-release).

To see what a change does, run it on the other revision too (for example in a `git worktree`) and add `--base other/summary.json --base-output other/ --head-output output/patched` to the command that runs `full_release_table.py`. To compare what each patch matched with a release, add `--previous manifest.json`.
