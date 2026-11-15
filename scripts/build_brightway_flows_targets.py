"""Build what the Brightway build needs to follow patch 0010's links.

Patch 0010 links every BAFU elementary flow to a Brightway Flows flow, and says nothing
more: the crosswalk holds an identifier and how close the match is. To link a database
through those identifiers, the build also needs, for each of them:

* the identifier the flow has in the release the build pins (a later release can
  redirect one to another);
* the flow's name, context and unit, to make a node for a flow that is not in EF 3.1;
* the conversion from BAFU's unit to the flow's unit, where the release states one.
  Nothing is worked out here: a conversion the release does not state stays unknown;
* for a flow that is not in EF 3.1, the flow whose factors Brightway Flows' own
  implementation of EF 3.1 gives it, when it names exactly one. The build then gives
  the flow its own factors of that flow, where that is a flow of EF 3.1 the build's
  methods have factors for. No factor is copied from the release.

Everything comes from public, pinned sources: the crosswalk in this repository, and two
files of Brightway Flows 1.1.0 from Zenodo (https://doi.org/10.5281/zenodo.23554066),
checked against their MD5 checksums. Downloads are cached in the user cache folder.

Writes `src/bafu_community_fixes/data/brightway-flows-targets-bafu-2026-v1.csv`, one row
for each row of the crosswalk, in the same order.

Usage:
    uv run python scripts/build_brightway_flows_targets.py
    uv run python scripts/build_brightway_flows_targets.py --release-files FOLDER
    uv run python scripts/build_brightway_flows_targets.py --check

`--release-files` reads the two release files from a folder that already holds them (they
are checked the same way). `--check` writes nothing and fails if the committed file is
not what the sources give.
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).parents[1] / "src" / "bafu_community_fixes" / "data"
RELEASE = "bafu-2026-v1"
CROSSWALK = DATA / f"brightway-flows-crosswalk-{RELEASE}.csv"
TARGETS = DATA / f"brightway-flows-targets-{RELEASE}.csv"

BRIGHTWAY_FLOWS_RELEASE = "1.1.0"
ZENODO_DOI = "10.5281/zenodo.23554066"
ZENODO_FILES = {  # name: MD5, as the Zenodo record gives it
    "harmonised-flows-simple.json.gz": "6faa6519ef46337b0bc899eb179b601f",
    "lcia-factors.json.gz": "d11699c522f3845931a6a877044e348e",
}
ZENODO_URL = "https://zenodo.org/api/records/23554066/files/{name}/content"

TARGET_IRI = "https://vocab.brightway.dev/elementary-flows/"
SOURCE_IRI = "https://vocab.brightway.one/bafu/2026-v1/flow/"
CONTEXT_IRI = "https://vocab.brightway.one/flow-contexts/"
EF = ("EF", "3.1")
OWN = "brightway-flows"  # Brightway Flows' own implementation of a method
EF_LIST = "EF 3.1"  # `source` of a flow that EF 3.1 holds

FIELDS = (
    *("name", "category", "subCategory", "unit", "key"),  # as in the crosswalk
    "brightway_flow_id",  # what patch 0010 writes
    "flow_id",  # the same flow in the pinned release
    *("flow_name", "flow_context", "flow_unit", "flow_list"),
    *("conversion", "conversion_basis"),
    *("factors_from", "factors_derivation"),
)


class SourceError(Exception):
    pass


def cache_dir() -> Path:
    # the same folder as the patch tool's downloads, without importing the patch tool:
    # this script needs nothing but the standard library
    try:
        from bafu_community_fixes.download import cache_dir as shared

        return shared()
    except ImportError:
        return Path.home() / ".cache" / "bafu-community-fixes"


def release_file(name: str, folder: Path | None) -> Path:
    """One file of the pinned release, checked against the record's MD5 every time."""
    path = (folder or cache_dir() / "brightway-flows" / "zenodo-23554066") / name
    if not path.exists():
        if folder is not None:
            raise SourceError(f"{path} is not there")
        path.parent.mkdir(parents=True, exist_ok=True)
        url = ZENODO_URL.format(name=name)
        print(f"Downloading {url}")
        with urllib.request.urlopen(url, timeout=300) as response:
            path.write_bytes(response.read())
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    if digest.hexdigest() != ZENODO_FILES[name]:
        raise SourceError(
            f"{path} is not the file of Brightway Flows {BRIGHTWAY_FLOWS_RELEASE} "
            f"(MD5 {digest.hexdigest()}, the record gives {ZENODO_FILES[name]})"
        )
    return path


def current(identifier: str, redirects: dict[str, str]) -> str:
    """The identifier a flow has now: a release can replace one identifier by another."""
    seen = set()
    while identifier in redirects and identifier not in seen:
        seen.add(identifier)
        identifier = redirects[identifier]
    return identifier


def factor_sources(factors: dict) -> dict[str, tuple[set[str], set[str]]]:
    """For each flow: the flows its factors come from, and how, in Brightway Flows' own
    implementation of EF 3.1 (factors without a geography only, as the build reads them)."""
    own = {
        category["id"]
        for category in factors["impact_categories"]
        if (category["method"]["name"], category.get("version")) == EF
        and category["implemented_by"] == OWN
    }
    if not own:
        raise SourceError("the release holds no EF 3.1 categories of Brightway Flows' own")
    found: dict[str, tuple[set[str], set[str]]] = {}
    for factor in factors["characterization_factors"]:
        if factor["impact_category_id"] not in own or factor.get("geography"):
            continue
        sources, how = found.setdefault(factor["elementary_flow_uuid"], (set(), set()))
        if factor.get("source_flow_uuid"):
            sources.add(factor["source_flow_uuid"])
        if factor.get("derivation"):
            how.add(factor["derivation"])
    return found


def targets(crosswalk: list[dict], harmonised: dict, factors: dict) -> list[dict]:
    flows = {flow["identifier"]: flow for flow in harmonised["flows"]}
    redirects = {
        entry["identifier"]: entry["replaced_by_identifier"]
        for entry in harmonised["redirects"]
        if entry.get("replaced_by_identifier")
    }
    (correspondence,) = [
        c for c in harmonised["correspondences"] if c["@id"].endswith(f"/correspondences/{RELEASE}")
    ]
    stated = {}  # BAFU flow (Brightway Flows' identifier of it): (target, multiplier, basis)
    for association in correspondence["xkos:madeOf"]:
        source = association["xkos:sourceConcept"]["@id"].removeprefix(SOURCE_IRI)
        stated[source] = (
            association["xkos:targetConcept"]["@id"].removeprefix(TARGET_IRI),
            association.get("qudt:conversionMultiplier"),
            association.get("brightway:conversionBasis", ""),
        )
    sources = factor_sources(factors)

    rows = []
    for row in crosswalk:
        identifier = current(row["brightway_flow_id"], redirects)
        flow = flows.get(identifier)
        if flow is None:
            raise SourceError(
                f"{row['brightway_flow_id']} ({row['name']}) is not a flow of Brightway Flows "
                f"{BRIGHTWAY_FLOWS_RELEASE}"
            )
        target, multiplier, basis = stated.get(row["bafu_flow_uuid"], (None, None, ""))
        if target is not None and current(target, redirects) != identifier:
            # the release links this BAFU flow to another flow than the crosswalk does: its
            # conversion is a statement about that other link, and is not taken
            multiplier, basis = None, ""
        outside = flow["source"] != EF_LIST
        named, how = sources.get(identifier, (set(), set())) if outside else (set(), set())
        rows.append(
            {field: row[field] for field in ("name", "category", "subCategory", "unit", "key")}
            | {
                "brightway_flow_id": row["brightway_flow_id"],
                "flow_id": identifier,
                "flow_name": flow["prefLabel"],
                "flow_context": flow["context_iri"].removeprefix(CONTEXT_IRI),
                "flow_unit": flow["unit"],
                "flow_list": flow["source"],
                "conversion": "" if multiplier is None else repr(float(multiplier)),
                "conversion_basis": basis if multiplier is not None else "",
                "factors_from": next(iter(named)) if len(named) == 1 else "",
                "factors_derivation": "+".join(sorted(how)),
            }
        )
    return rows


def as_csv(rows: list[dict]) -> str:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue()


def summary(rows: list[dict]) -> str:
    shipped = [row for row in rows if row["key"] == "as shipped"]
    outside = [row for row in shipped if row["flow_list"] != EF_LIST]
    return (
        f"{len(rows)} rows ({len(shipped)} flows as shipped): "
        f"{len(shipped) - len(outside)} link to an EF 3.1 flow, {len(outside)} to a flow outside "
        f"EF 3.1, of which {sum(bool(row['factors_from']) for row in outside)} take their "
        f"factors from one EF 3.1 flow; "
        f"{sum(row['brightway_flow_id'] != row['flow_id'] for row in shipped)} identifier "
        f"replaced by the release; {sum(bool(row['conversion']) for row in shipped)} "
        f"conversions stated"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release-files", type=Path, help="folder that holds the two files")
    parser.add_argument("--check", action="store_true", help="compare with the committed file")
    args = parser.parse_args(argv)
    folder = args.release_files.expanduser() if args.release_files else None
    try:
        with gzip.open(release_file("harmonised-flows-simple.json.gz", folder), "rt") as f:
            harmonised = json.load(f)
        with gzip.open(release_file("lcia-factors.json.gz", folder), "rt") as f:
            factors = json.load(f)
        with open(CROSSWALK, newline="") as f:
            crosswalk = list(csv.DictReader(f))
        rows = targets(crosswalk, harmonised, factors)
    except SourceError as error:
        print(f"Not built: {error}", file=sys.stderr)
        return 1
    text = as_csv(rows)
    if args.check:
        if not TARGETS.exists() or TARGETS.read_text() != text:
            print(f"{TARGETS.name} is not what the sources give; rebuild it", file=sys.stderr)
            return 1
        print(f"{TARGETS.name} is what the sources give: {summary(rows)}")
        return 0
    TARGETS.write_text(text)
    print(f"Wrote {TARGETS.name}: {summary(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
