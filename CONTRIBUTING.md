# Contributing

Open a community contribution issue or pull request. Pin the canonical import and proposed layer; provide public evidence, isolated application steps, validation results and partner positions. Use the community templates and retain dissent.

Run `python3 scripts/community.py check` and `python3 -m unittest discover -s community/tests`. Keep restricted exports, generated candidate datasets and confidential notes under ignored local folders. The dataset remains subject to its own terms.

## Package work

Changes to the `bafu_community_fixes` package (import fixes, patches, report, TUI) run in
its locked environment on Python 3.14, separately from the checks above:

```sh
uv sync --locked
uv run pytest
uv run ruff check && uv run ruff format --check
```

How to write a patch, record who authored and authorised it, add supporting data and a
test is explained in the README under [Writing a patch](README.md#writing-a-patch) and
[Patches](README.md#patches). Leave `authorised_by` out until the patch is approved; the
pipeline runs it and warns. Rebuild the Brightway Flows data with its script rather than
editing it (see [its README](src/bafu_community_fixes/data/README.md)).
