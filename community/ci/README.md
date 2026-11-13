# Documentation and contribution CI

The [Documentation workflow](../../.github/workflows/pages.yml) validates contribution records, runs the synthetic community tests and build-audit checks, then builds and checks the public documentation site. Pull requests never deploy. Updates to `main` publish only the generated `_site/` artifact through GitHub Pages, once a repository administrator has enabled **Settings → Pages → Source: GitHub Actions**.

Run the same contribution checks locally with `python3 scripts/community.py check`, `python3 -m unittest discover -s community/tests` and `python3 scripts/build_checks.py community/templates/build-audit.json`. Site maintenance and hosting links are documented in [site/README.md](../../site/README.md) and the main README.

The supplied `github-actions.yml` remains a standalone contribution-check template; the Documentation workflow already runs those checks. The portable `.gitlab-ci.yml` provides equivalent validation and Pages publication for a GitLab mirror.

## Full release run

The [Full release workflow](../../.github/workflows/full-release.yml) runs the import fixes and every patch on BAFU's full release: for each pull request that touches the patch tool or its data (patches proposed), for each such change on `main` (patches accepted), and on request. The [CI workflow](../../.github/workflows/ci.yml) tests the tool on a small fixture; this one shows what a patch does to the release.

The job gets the release as the tool does: `bafu-fixes run latest` downloads it once, checks its SHA-256, and the Actions cache keeps it under that checksum. It runs with `--strict`, which checks against the EcoSpold 1 schema after the import and after every patch, and then checks the files that were written. It fails if

- a step stops (a patch stops when its target is not as expected) or the result is not valid EcoSpold 1;
- the files read are not a release the tool knows (`download.FINGERPRINTS`);
- a patch changes nothing, so its target was not there.

Its job summary (the *Summary* page of the check) lists every step with its author, who authorised it, and the datasets, exchanges and values it changed. A patch that is not yet authorised is marked. On a pull request the job also runs the base revision, and the summary starts with what the pull request changes: new and removed steps, the difference per step, and how many files of the patched release differ.

Nothing from the inventory is published. The job summary and the uploaded `full-release-summary` hold counts, checksums and file names. The release, the patched release and the HTML report, which quotes the data, stay on the runner.

A new patch needs no change to the workflow: patches are found in `src/bafu_community_fixes/patches/`.

Run the same locally:

```sh
uv sync --locked
uv run bafu-fixes run latest output/ --strict --summary output/summary.json
uv run python scripts/check_patched_release.py output/ --summary output/summary.json
uv run python scripts/full_release_table.py output/summary.json --check
```

To see what a change does, run it on the other revision too (for example in a `git worktree`) and add `--base other/summary.json --base-output other/ --head-output output/` to the last command.
