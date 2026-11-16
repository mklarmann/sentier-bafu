# Supporting data for patches

| File | Used by | Source |
|---|---|---|
| `brightway-flows-corrections-bafu-2026-v1.json` | patches 0004–0008 | [Brightway Flows](https://github.com/brightway-labs/brightway-flows) |
| `brightway-flows-crosswalk-bafu-2026-v1.csv` | patch 0010 | [Brightway Flows](https://github.com/brightway-labs/brightway-flows) |

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
