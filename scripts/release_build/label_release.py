"""Label the importer's tables of a patched release, so nobody takes them for BAFU's.

sentier-importers writes `bafu-2026` and `v1` on every dataset, whatever it reads, and
sentier-brightway names the database after that source. For a patched release this:

- writes the patched release's own source name and version on every dataset;
- gives each elementary exchange that the adapter linked on the declared flow its corrected
  name back as the label (`flow_name`). The flow identifier stays the declared one;
- writes `source-observations.json` beside the tables: for each such exchange the declared
  and the corrected name, compartment, subcompartment and unit, and the steps recorded on
  its dataset.

Run it in the sentier-importers environment (it needs pyarrow).
"""

import argparse
import json
from collections import Counter
from pathlib import Path

OBSERVATIONS = "source-observations.json"


class LabelError(Exception):
    pass


def relabel(names: list, kinds: list, owners: list, observations: list[dict]) -> list:
    """`names` with the corrected name on every observed exchange.

    `owners` is the dataset of each exchange row, in the tables' order; an exchange's
    position counts the rows of its dataset. Raises if a row is not the declared flow.
    """
    seen: Counter = Counter()
    row_of = {}
    for row, owner in enumerate(owners):
        row_of[(owner, seen[owner])] = row
        seen[owner] += 1
    names = list(names)
    for observation in observations:
        key = (observation["dataset"], observation["position"])
        row = row_of.get(key)
        if row is None:
            raise LabelError(f"No exchange {key[1]} in dataset {key[0]}")
        declared = observation["declared"]["name"]
        if kinds[row] != "biosphere" or names[row] != declared:
            raise LabelError(
                f"Exchange {key[1]} of dataset {key[0]} is {names[row]!r} ({kinds[row]}), "
                f"not the declared elementary flow {declared!r}"
            )
        names[row] = observation["patched"]["name"]
    return names


def label_folder(folder: Path, receipt: dict, source: str, source_version: str) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq

    observations = receipt.get("source_observations", [])
    exchanges = pq.read_table(folder / "exchanges.parquet")
    names = relabel(
        exchanges.column("flow_name").to_pylist(),
        exchanges.column("flow_type").to_pylist(),
        exchanges.column("process_id").to_pylist(),
        observations,
    )
    index = exchanges.schema.get_field_index("flow_name")
    field = exchanges.schema.field(index)
    exchanges = exchanges.set_column(index, field, pa.array(names, type=field.type))
    pq.write_table(exchanges, folder / "exchanges.parquet")

    processes = pq.read_table(folder / "processes.parquet")
    for column, value in (("source", source), ("source_version", source_version)):
        index = processes.schema.get_field_index(column)
        field = processes.schema.field(index)
        constant = pa.array([value] * processes.num_rows, type=field.type)
        processes = processes.set_column(index, field, constant)
    pq.write_table(processes, folder / "processes.parquet")

    steps = receipt.get("steps_by_dataset", {})
    record = [
        observation | {"steps": steps.get(observation["dataset"], {}).get("patches", [])}
        for observation in observations
    ]
    (folder / OBSERVATIONS).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return {
        "datasets": processes.num_rows,
        "source": source,
        "source_version": source_version,
        "exchanges_linked_on_the_declared_flow": len(observations),
        "datasets_with_such_exchanges": len({o["dataset"] for o in observations}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Folder with the importer's two tables")
    parser.add_argument("--receipt", type=Path, required=True, help="The adapter's receipt")
    parser.add_argument("--source", required=True, help="Source name of the patched release")
    parser.add_argument("--source-version", required=True)
    args = parser.parse_args(argv)
    receipt = json.loads(args.receipt.read_text())
    try:
        result = label_folder(args.folder, receipt, args.source, args.source_version)
    except LabelError as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
