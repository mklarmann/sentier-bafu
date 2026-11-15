# Supporting data for patches

| File | Used by | Source |
|---|---|---|
| `brightway-flows-corrections-bafu-2026-v1.json` | patches 0004–0008 | [Brightway Flows](https://github.com/brightway-labs/brightway-flows) |
| `brightway-flows-crosswalk-bafu-2026-v1.csv` | patch 0010 | [Brightway Flows](https://github.com/brightway-labs/brightway-flows) |
| `brightway-flows-targets-bafu-2026-v1.csv` | the Brightway build, with `--linking brightway-flows` | [Brightway Flows](https://github.com/brightway-labs/brightway-flows) 1.1.0 |

Brightway Flows is published under the ODbL 1.0. Its author, Chris Mutel, has given
permission (13 October 2026) for this data to be used in this repository, with the
pipeline's output following the BAFU licensing (the BAFU Terms of Use).

Both files are derived from the Brightway Flows database: a selection from
`bafu-2026-v1-manual-fixes.json` and `simapro-lineage-manual-fixes.json` at commit
`19d6cc6`, and the `bafu-2026-v1` correspondence in `harmonised-flows-simple.json.gz` of
release 1.0.0 (https://doi.org/10.5281/zenodo.22857950). They are made available under
the Open Database License 1.0 (https://opendatacommons.org/licenses/odbl/1-0/), not under
this repository's MIT licence. `scripts/build_brightway_flows_data.py` is the method that
produces them from those sources. The permission above was recorded in
sentier-dev/bafu-community-fixes (commit 15bbfbb, 13 October 2026), where this pipeline
was published before it moved here (#19); its confirmation for this repository is asked
in #19.

Rebuild both files with `uv run python scripts/build_brightway_flows_data.py`. It
downloads everything it needs from public, pinned sources (GitHub and Zenodo) and
checks their hashes; don't edit the files by hand.

## What the build needs to follow patch 0010's links

`brightway-flows-targets-bafu-2026-v1.csv` has one row for each row of the crosswalk. It
adds what the crosswalk does not hold: the identifier the flow has in Brightway Flows 1.1.0
(https://doi.org/10.5281/zenodo.23554066), its name, context and unit, the conversion from
BAFU's unit that this release states, and, for a flow outside EF 3.1, the one flow that
Brightway Flows' own implementation of EF 3.1 names as the source of its factors. No factor
is copied. It is derived from `harmonised-flows-simple.json.gz` and `lcia-factors.json.gz`
of that release, and is made available under the Open Database License 1.0 like the two
files above.

Rebuild it with `uv run python scripts/build_brightway_flows_targets.py`; `--check` compares
the committed file with what the sources give. The permission named above was given for
the two files of patches 0004 to 0010. It has not been asked for this third file, which
only the second linking of the build reads (`docs/brightway-build.md`).
