"""Write the `metadata.json` that sentier-brightway needs beside the importer's parquet files.

`sentier-importers run bafu-processes` and `run bafu-exchanges` write `processes.parquet` and
`exchanges.parquet`. The folder's `metadata.json` (source, release, sectors, row counts) is
only written by that repository's `scripts/run_bafu_local.py`, which also runs sources whose
inputs are not public. This writes the same keys from the two parquet files.

Run it in the sentier-importers environment (it needs pyarrow, and takes the title, publisher,
licence summary and citation from sentier-importers so they are not copied here).
"""

import argparse
import json
from pathlib import Path

SCHEMA_VERSION = "0.3.0"  # sentier-inventory: one folder per source release
MODIFIED_LABEL = "Modified Data"  # the label BAFU's Terms of Use ask for


def read_columns(folder: Path) -> tuple[dict[str, list[str]], dict[str, int]]:
    """Distinct `source`, `source_version` and `sector` values, and the row counts."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    processes = pq.read_table(
        folder / "processes.parquet", columns=["sector", "source", "source_version"]
    )
    distinct = {
        name: sorted(pc.drop_null(processes.column(name).combine_chunks()).unique().to_pylist())
        for name in processes.column_names
    }
    counts = {
        "processes.parquet": processes.num_rows,
        "exchanges.parquet": pq.read_metadata(folder / "exchanges.parquet").num_rows,
    }
    return distinct, counts


def provider_texts() -> dict[str, str]:
    """Title, publisher, licence summary, citation and source IRI, from sentier-importers."""
    from sentier_importers.sources.bafu import ecospold
    from sentier_importers.sources.bafu.provenance import BAFU_PROVENANCE, BAFU_PROVENANCE_IRI

    return {
        "title": BAFU_PROVENANCE["title"],
        "publisher": BAFU_PROVENANCE["publisher"],
        "license": ecospold.LICENSE_SUMMARY,
        "citation": BAFU_PROVENANCE["citation"],
        "provenance": BAFU_PROVENANCE_IRI,
    }


def build_metadata(
    distinct: dict[str, list[str]],
    counts: dict[str, int],
    texts: dict[str, str],
    modifications: dict | None = None,
) -> dict:
    """The folder's metadata. `modifications` marks a patched copy as modified data."""
    for column in ("source", "source_version"):
        if len(distinct[column]) != 1:
            raise ValueError(f"processes.{column} must hold one value, found {distinct[column]}")
    metadata = {
        "source": distinct["source"][0],
        "source_version": distinct["source_version"][0],
        "title": texts["title"],
        "publisher": texts["publisher"],
        "license": texts["license"],
        "citation": texts["citation"],
        "source_url": None,
        "provenance": texts["provenance"],
        "retrieved": None,
        "schema_version": SCHEMA_VERSION,
        "sectors": distinct["sector"],
        "row_counts": counts,
    }
    if modifications is not None:
        # The schema allows further keys. BAFU's Terms of Use (3.5) ask that modified
        # data is labelled as modified and never presented as the original.
        metadata["title"] = f"{texts['title']}, patched ({MODIFIED_LABEL})"
        metadata["label"] = MODIFIED_LABEL
        metadata["modified"] = True
        metadata["modifications"] = modifications
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Folder with the two parquet files")
    parser.add_argument(
        "--modifications",
        type=Path,
        help="JSON file describing the changes made to the provider release (a patched copy)",
    )
    args = parser.parse_args(argv)
    modifications = json.loads(args.modifications.read_text()) if args.modifications else None
    distinct, counts = read_columns(args.folder)
    metadata = build_metadata(distinct, counts, provider_texts(), modifications)
    target = args.folder / "metadata.json"
    target.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {target}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
