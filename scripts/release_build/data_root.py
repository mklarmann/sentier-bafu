"""Fetch the data sentier-brightway pins, except the inventory, into a folder.

sentier-brightway reads four data repositories. Its `sources.toml` pins each file by commit
and SHA-256. A build from a release folder replaces the inventory and keeps the other three
(elementary flow terms, EF 3.1 methods, the BAFU to EF 3.1 mapping) exactly as pinned.

This uses sentier-brightway's own reader: a file already present with the pinned SHA-256 is
kept, anything else is downloaded and checked. Run it in the sentier-brightway environment.
"""

import argparse
import json
from pathlib import Path

INVENTORY = "sentier-inventory"


def pinned_sources() -> tuple:
    from sentier_brightway.fetch import load_packaged_manifest

    return tuple(source for source in load_packaged_manifest() if source.name != INVENTORY)


def main(argv: list[str] | None = None) -> int:
    from sentier_brightway.fetch import materialize

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Where the pinned files are kept")
    parser.add_argument("--record", type=Path, help="Write the pins that were used, as JSON")
    args = parser.parse_args(argv)
    sources = pinned_sources()
    materialize(sources, cache_dir=args.folder)
    pins = [
        {"name": s.name, "repository": s.repo, "commit": s.ref, "files": dict(s.files)}
        for s in sources
    ]
    if args.record:
        args.record.write_text(json.dumps(pins, indent=2) + "\n")
    for pin in pins:
        print(f"{pin['name']} at {pin['commit'][:12]}: {len(pin['files'])} file(s) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
