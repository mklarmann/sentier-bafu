"""Fetch the data the Brightway installer pins, except the inventory, into a folder.

The installer reads four data repositories. Its `sources.toml`
(`src/sentier_brightway/sources.toml`) pins each file by commit and SHA-256. A build from a
release folder replaces the inventory and keeps the other three as pinned: the elementary
flow terms, the EF 3.1 methods and the BAFU to EF 3.1 mapping.

That file is the one place a data pin lives: the installer run on its own and the build
read the same commits. To move a pin, write the file again (`scripts/pin_sources.py`), with
a measured run.

This uses the installer's own reader: a file already present with the pinned SHA-256 is
kept, anything else is downloaded and checked. Each set of pins gets its own subfolder, so
moving a pin never changes the data an earlier build points at. Run it in this repository's
environment, with the `brightway` extra.
"""

import argparse
import json
from pathlib import Path

INVENTORY = "sentier-inventory"
PINNED_BY = "this repository"


def pin_record(sources: tuple) -> list[dict]:
    """What a build records of each source: where it is from, the commit, and its files."""
    return [
        {
            "name": source.name,
            "repository": source.repo,
            "commit": source.ref,
            "pinned_by": PINNED_BY,
            "files": dict(source.files),
        }
        for source in sources
    ]


def pinned_sources() -> tuple[tuple, list[dict]]:
    """The three data sources to fetch, and the record of their pins."""
    from sentier_brightway.fetch import load_packaged_manifest

    sources = tuple(s for s in load_packaged_manifest() if s.name != INVENTORY)
    return sources, pin_record(sources)


def main(argv: list[str] | None = None) -> int:
    from sentier_brightway.fetch import manifest_key, materialize

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Where the pinned files are kept")
    parser.add_argument("--record", type=Path, help="Write the pins that were used, as JSON")
    args = parser.parse_args(argv)
    sources, record = pinned_sources()
    folder = args.folder / manifest_key(sources)
    materialize(sources, cache_dir=folder)
    if args.record:
        args.record.write_text(json.dumps({"folder": str(folder), "sources": record}, indent=2))
    for pin in record:
        print(f"{pin['name']} at {pin['commit'][:12]}: {len(pin['files'])} file(s) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
