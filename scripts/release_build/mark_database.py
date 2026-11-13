"""Write what a database was built from into its Brightway metadata.

A database built from a patched release must not be taken for BAFU's release: its name
says so, and its metadata carries the label "Modified Data", the patch ids and the import
fix ids. A database built from the provider release keeps BAFU's name and says that its
amounts are BAFU's. Both say what the build itself changed (the relinking to EF 3.1 flows).

The record goes under the key `release_build` of each named database. Run it in the
sentier-brightway environment, with `BRIGHTWAY2_DIR` set to the folder the build wrote.
"""

import argparse
import json
import os
import sys
from pathlib import Path

KEY = "release_build"
MODIFIED_LABEL = "Modified Data"
PROVIDER_LABEL = "Provider release"


class MarkError(Exception):
    pass


def release_record(build: dict, credit: str) -> dict:
    """The record for the metadata, from the build's own record of what it did."""
    patched = bool(build["patched"])
    return {
        "label": MODIFIED_LABEL if patched else PROVIDER_LABEL,
        "modified_data": patched,
        "provider_release": build["release_name"],
        "credit": credit,
        "provider_release_tree_sha256": build["provider_tree_sha256"],
        "built_release_tree_sha256": build["built_tree_sha256"],
        "patches": build["patches"],
        "import_fixes": build["import_fixes"],
        "record_of_changes": build["record_of_changes"],
        "build_steps": build["build_steps"],
        "tools": build["tools"],
        "data": build["data"],
    }


def check_name(database: str, record: dict, provider_source: str) -> None:
    """A patched database must not carry the provider's name."""
    names = {provider_source, f"{provider_source}-residual"}
    if record["modified_data"] and database in names:
        raise MarkError(
            f"{database} is the name of BAFU's release; a patched database needs another name"
        )


def mark(project: str, databases: list[str], record: dict, provider_source: str) -> None:
    if not os.environ.get("BRIGHTWAY2_DIR"):
        raise MarkError("BRIGHTWAY2_DIR is not set; point it at the folder this build wrote")
    import bw2data as bd

    if project not in bd.projects:
        raise MarkError(f"No Brightway project {project!r}")
    bd.projects.set_current(project)
    for name in databases:
        if name not in bd.databases:
            raise MarkError(f"Database {name!r} is not in project {project!r}")
        check_name(name, record, provider_source)
    for name in databases:
        bd.databases[name][KEY] = record
    bd.databases.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", action="append", required=True)
    parser.add_argument("--build", type=Path, required=True, help="JSON written by the build")
    parser.add_argument("--provider-source", default="bafu-2026", help="BAFU's source name")
    args = parser.parse_args(argv)
    from sentier_brightway.constants import citation

    credit = citation(args.provider_source).removeprefix("Source: ").rstrip(".")
    record = release_record(json.loads(args.build.read_text()), credit)
    try:
        mark(args.project, args.database, record, args.provider_source)
    except MarkError as error:
        print(f"Could not mark the database: {error}", file=sys.stderr)
        return 2
    print(f"{record['label']}: {', '.join(args.database)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
