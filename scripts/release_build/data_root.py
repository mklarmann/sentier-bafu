"""Fetch the data sentier-brightway pins, except the inventory, into a folder.

sentier-brightway reads four data repositories. Its `sources.toml` pins each file by commit
and SHA-256. A build from a release folder replaces the inventory and keeps the other three
(elementary flow terms, EF 3.1 methods, the BAFU to EF 3.1 mapping) as pinned.

The build's `pins.toml` can move one of the three to another commit, under `[data.<name>]`,
with the SHA-256 of every file that differs. An override is recorded with its reason, so a
build always says which data it used and where that differs from sentier-brightway's pins.

This uses sentier-brightway's own reader: a file already present with the pinned SHA-256 is
kept, anything else is downloaded and checked. Each set of pins gets its own subfolder, so
moving a pin never changes the data an earlier build points at. Run it in the
sentier-brightway environment.
"""

import argparse
import json
import tomllib
from pathlib import Path

INVENTORY = "sentier-inventory"


def apply_overrides(sources: tuple, overrides: dict, make) -> tuple[tuple, list[dict]]:
    """Replace the commit and file hashes of the sources named in `overrides`.

    `make(source, commit, files)` builds a source like `source` at another commit. Returns
    the sources to fetch and, for the record, what each one is pinned by.
    """
    unknown = set(overrides) - {source.name for source in sources}
    if unknown:
        raise ValueError(f"pins.toml overrides data that is not pinned: {sorted(unknown)}")
    result, record = [], []
    for source in sources:
        entry = {"name": source.name, "repository": source.repo, "commit": source.ref}
        override = overrides.get(source.name)
        if override is None:
            entry["pinned_by"] = "sentier-brightway"
        else:
            unknown_files = set(override.get("files", {})) - set(source.files)
            if unknown_files:
                raise ValueError(f"{source.name}: override names other files: {unknown_files}")
            entry |= {
                "commit": override["commit"],
                "pinned_by": "this build",
                "reason": override["reason"],
                "sentier_brightway_commit": source.ref,
                "files_that_differ": sorted(override.get("files", {})),
            }
            files = {**source.files, **override.get("files", {})}
            source = make(source, override["commit"], files)
        result.append(source)
        record.append(entry | {"files": dict(source.files)})
    return tuple(result), record


def pinned_sources(overrides: dict | None = None) -> tuple[tuple, list[dict]]:
    """The three data sources to fetch, and the record of their pins."""
    from sentier_brightway.fetch import Source, load_packaged_manifest

    def make(source, commit, files):
        return Source(name=source.name, repo=source.repo, ref=commit, files=files)

    sources = tuple(s for s in load_packaged_manifest() if s.name != INVENTORY)
    return apply_overrides(sources, overrides or {}, make)


SOURCE_IRI = "https://vocab.sentier.dev/sources/"
FLOW_TYPE = "elementary-flow"


def write_flow_terms(terms: Path, target: Path, provider: str, source: str) -> int:
    """Write the provider's elementary flow terms again under another source name.

    sentier-brightway names the database after the inventory's source and looks up the
    flow terms of that same source. A patched release has its own source name and, because
    its elementary exchanges are linked on the flows BAFU declared, exactly the provider's
    flows. Returns the number of terms written.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    wanted = [("type", "==", FLOW_TYPE), ("source", "==", SOURCE_IRI + provider)]
    tables = [pq.read_table(file, filters=wanted) for file in sorted(terms.glob("*.parquet"))]
    tables = [table for table in tables if table.num_rows]
    if not tables:
        raise ValueError(f"No elementary flow terms of {provider} in {terms}")
    table = pa.concat_tables(tables)
    index = table.schema.get_field_index("source")
    field = table.schema.field(index)
    renamed = pa.array([SOURCE_IRI + source] * table.num_rows, type=field.type)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table.set_column(index, field, renamed), target)
    return table.num_rows


def main(argv: list[str] | None = None) -> int:
    from sentier_brightway.fetch import manifest_key, materialize

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Where the pinned files are kept")
    parser.add_argument("--pins", type=Path, help="The build's pins.toml, for `[data.*]`")
    parser.add_argument("--record", type=Path, help="Write the pins that were used, as JSON")
    parser.add_argument(
        "--flow-terms",
        nargs=3,
        metavar=("PROVIDER", "SOURCE", "FILE"),
        help="Also write the provider's elementary flow terms under another source name",
    )
    args = parser.parse_args(argv)
    overrides = tomllib.loads(args.pins.read_text()).get("data", {}) if args.pins else {}
    sources, record = pinned_sources(overrides)
    folder = args.folder / manifest_key(sources)
    materialize(sources, cache_dir=folder)
    if args.flow_terms:
        provider, source, target = args.flow_terms
        count = write_flow_terms(folder / "sentier-vocab" / "terms", Path(target), provider, source)
        print(f"{count} elementary flow terms of {provider} written for {source}")
    if args.record:
        args.record.write_text(json.dumps({"folder": str(folder), "sources": record}, indent=2))
    for pin in record:
        print(
            f"{pin['name']} at {pin['commit'][:12]} (pinned by {pin['pinned_by']}): "
            f"{len(pin['files'])} file(s) verified"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
