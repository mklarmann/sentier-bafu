"""Turn a folder of EcoSpold 1 files into the zip that sentier-importers reads.

sentier-importers reads BAFU's release as BAFU ships it: elements without a namespace, and
technosphere inputs linked by the exchange `number`, which is the supplying dataset's number.
The patched release written by `bafu-fixes` differs in two ways that stop that reader:

- elements are in the EcoSpold namespace, so the reader finds no `<dataset>`;
- exchanges that shared a number within a dataset carry a dummy number (the
  `renumber-exchanges` import fix), which names no dataset. The original number is kept in
  `bcf:extensions/bcf:exchange/@originalNumber`.

This module writes a copy without the namespace, with the original numbers restored, and
without the `bcf:extensions` block. No amount, unit or location is touched. The copy is an
intermediate input for the importer. It is not a release: the patched release stays as
`bafu-fixes` wrote it. A provider release (no namespace, no extensions) passes through
unchanged apart from XML serialisation.

**Elementary flows are linked on the flow as BAFU declared it.** The importer derives an
elementary flow's identifier from its name, compartment, subcompartment and unit, and the
mapping to EF 3.1 is keyed by that identifier. A patch that corrects one of the four (a name
without its unit suffix, a compartment) would give the exchange an identifier the mapping
does not hold, and the exchange would lose its EF 3.1 flow. The patched release does not
carry the declared values of an exchange it corrected: per exchange its extensions hold
`originalNumber`, `brightwayFlow` and `brightwayMatch` only. So, given the provider release
the patched one was made from (`declared`), the adapter compares each elementary exchange
with the same exchange there and, where the four differ, writes the declared ones into the
importer's copy. The corrected ones are kept in the receipt as a source observation, with
the dataset and the exchange's position, for the build to carry beside the data.

Standard library only.
"""

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from dataclasses import dataclass, field, fields
from pathlib import Path

ECOSPOLD_NS = "http://www.EcoInvent.org/EcoSpold01"
EXT_NS = "urn:bafu-community-fixes:extensions:1"
# Same threshold as `bafu_community_fixes.import_fixes.DUMMY_BASE`
DUMMY_BASE = 1_000_000_000
_FILE = re.compile(r"process_(.+)\.xml$")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


class AdapterError(Exception):
    """An input file the adapter can't turn into importer input, with the reason."""


@dataclass
class Receipt:
    """What the adapter read and changed. Dataset identifiers and counts, no inventory."""

    source: str = ""
    files: int = 0
    datasets: int = 0
    exchanges: int = 0
    namespaced_files: int = 0
    extension_blocks_removed: int = 0
    numbers_restored: Counter = field(default_factory=Counter)
    import_fixes: Counter = field(default_factory=Counter)
    patches: Counter = field(default_factory=Counter)
    # dataset identifier (the part after `process_` in the file name) -> the import fixes
    # and patches the patch tool recorded on that dataset, in the order they ran
    steps_by_dataset: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    brightway_flow_links: int = 0
    # elementary exchanges whose name, compartment, subcompartment or unit a patch changed:
    # {"dataset", "position" (0-based among the dataset's exchanges), "declared", "patched"}
    source_observations: list[dict] = field(default_factory=list)
    input_tree_sha256: str = ""
    declared_tree_sha256: str = ""
    output_zip_sha256: str = ""

    def as_dict(self) -> dict:
        # Not `dataclasses.asdict`: it rebuilds a Counter from its items, which counts them
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        for key in ("numbers_restored", "import_fixes", "patches", "steps_by_dataset"):
            data[key] = dict(sorted(data[key].items()))
        return data


def _split(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return None, tag


def _kind(exchange: ET.Element) -> str:
    """The exchange kind as sentier-importers classifies it."""
    output_group = exchange.findtext("outputGroup")
    input_group = exchange.findtext("inputGroup")
    if input_group is None and output_group == "0":
        return "production"
    if (input_group if input_group is not None else output_group) == "4":
        return "biosphere"
    return "technosphere"


def _strip_namespace(root: ET.Element, name: str) -> bool:
    """Remove the EcoSpold namespace from every element. True if there was one."""
    found = False
    for element in root.iter():
        namespace, local = _split(element.tag)
        if namespace == ECOSPOLD_NS:
            element.tag = local
            found = True
        elif namespace not in (None, EXT_NS):
            raise AdapterError(f"{name}: unexpected namespace {namespace} on <{local}>")
    return found


def _restore_numbers(dataset: ET.Element, name: str, receipt: Receipt) -> None:
    """Undo `renumber-exchanges` in one dataset and drop its extension block."""
    exchanges = dataset.findall("flowData/exchange")
    receipt.exchanges += len(exchanges)
    by_number = {exchange.get("number"): exchange for exchange in exchanges}
    if len(by_number) != len(exchanges) and dataset.find(f"{{{EXT_NS}}}extensions") is not None:
        raise AdapterError(f"{name}: exchange numbers repeat in a file that has extensions")
    restored = set()
    for block in dataset.findall(f"{{{EXT_NS}}}extensions"):
        for child in block:
            _, local = _split(child.tag)
            if local == "dataset":
                steps = receipt.steps_by_dataset.setdefault(
                    _dataset_id(name), {"import_fixes": [], "patches": []}
                )
                for item in child:
                    _, kind = _split(item.tag)
                    if kind == "importFix":
                        receipt.import_fixes[item.text or ""] += 1
                        steps["import_fixes"].append(item.text or "")
                    elif kind == "patch":
                        receipt.patches[item.text or ""] += 1
                        steps["patches"].append(item.text or "")
            elif local == "exchange":
                number = child.get("number")
                if child.get("brightwayFlow"):
                    receipt.brightway_flow_links += 1
                original = child.get("originalNumber")
                if original is None:
                    continue
                exchange = by_number.get(number)
                if exchange is None:
                    raise AdapterError(f"{name}: extension names exchange {number}, not found")
                exchange.set("number", original)
                restored.add(number)
                receipt.numbers_restored[_kind(exchange)] += 1
            else:
                raise AdapterError(f"{name}: unknown extension element <{local}>")
        dataset.remove(block)
        receipt.extension_blocks_removed += 1
    for number in by_number:
        if number in restored or number is None or not number.isascii() or not number.isdigit():
            continue
        if int(number) >= DUMMY_BASE:
            raise AdapterError(
                f"{name}: exchange {number} has a dummy number and no originalNumber to restore"
            )


def _dataset_id(name: str) -> str:
    match = _FILE.search(name)
    if match is None:
        raise AdapterError(f"{name}: file name is not process_<id>.xml")
    return match.group(1)


FLOW_IDENTITY = ("name", "category", "subCategory", "unit")


def _parse(content: bytes, name: str) -> tuple[ET.Element, bool]:
    """The document without the EcoSpold namespace, and whether it had one."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise AdapterError(f"{name}: not well-formed XML ({error})") from None
    namespaced = _strip_namespace(root, name)
    if root.tag != "ecoSpold":
        raise AdapterError(f"{name}: root element is <{root.tag}>, not <ecoSpold>")
    if not root.findall("dataset"):
        raise AdapterError(f"{name}: no <dataset> element")
    return root, namespaced


def _link_on_declared_flows(root: ET.Element, declared: ET.Element, name: str, receipt: Receipt):
    """Give each elementary exchange the flow identity it has in the provider release."""
    datasets, declared_datasets = root.findall("dataset"), declared.findall("dataset")
    if len(datasets) != len(declared_datasets):
        raise AdapterError(f"{name}: the provider release has another number of datasets")
    for dataset, declared_dataset in zip(datasets, declared_datasets, strict=True):
        exchanges = dataset.findall("flowData/exchange")
        declared_exchanges = declared_dataset.findall("flowData/exchange")
        if len(exchanges) != len(declared_exchanges):
            raise AdapterError(f"{name}: the provider release has another number of exchanges")
        pairs = zip(exchanges, declared_exchanges, strict=True)
        for position, (exchange, original) in enumerate(pairs):
            # The same exchange: same place, same number (restored), same kind
            if exchange.get("number") != original.get("number") or _kind(exchange) != _kind(
                original
            ):
                raise AdapterError(
                    f"{name}: exchange {position + 1} is not the same exchange as in the "
                    "provider release; the declared flow can't be read from it"
                )
            if _kind(exchange) != "biosphere":
                continue
            patched = {key: exchange.get(key) for key in FLOW_IDENTITY}
            as_declared = {key: original.get(key) for key in FLOW_IDENTITY}
            if patched == as_declared:
                continue
            for key, value in as_declared.items():
                if value is None:
                    exchange.attrib.pop(key, None)
                else:
                    exchange.set(key, value)
            receipt.source_observations.append(
                {
                    "dataset": _dataset_id(name),
                    "position": position,
                    "declared": as_declared,
                    "patched": patched,
                }
            )


def adapt_document(
    content: bytes, name: str, receipt: Receipt, declared: bytes | None = None
) -> bytes:
    """One EcoSpold 1 file as importer input. `name` is used in messages and the receipt.

    `declared` is the same file in the provider release; with it, elementary exchanges
    keep the flow identity BAFU declared.
    """
    _dataset_id(name)
    root, namespaced = _parse(content, name)
    receipt.namespaced_files += namespaced
    datasets = root.findall("dataset")
    for dataset in datasets:
        _restore_numbers(dataset, name, receipt)
    if declared is not None:
        _link_on_declared_flows(root, _parse(declared, name)[0], name, receipt)
    receipt.files += 1
    receipt.datasets += len(datasets)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def find_files(source: Path) -> list[Path]:
    """The EcoSpold files of a release folder, sorted by path."""
    files = sorted(p for p in source.rglob("*") if p.suffix.lower() == ".xml")
    if not files:
        raise AdapterError(f"No XML files found in {source}")
    return files


def _add_to_tree(tree, source: Path, path: Path, content: bytes) -> None:
    tree.update(path.relative_to(source).as_posix().encode() + b"\0" + content)


def tree_sha256(source: Path) -> str:
    """One SHA-256 over the relative path and bytes of every EcoSpold file, in path order."""
    tree = hashlib.sha256()
    for path in find_files(source):
        _add_to_tree(tree, source, path, path.read_bytes())
    return tree.hexdigest()


def adapt_folder(
    source: Path, destination: Path, prefix: str = "ecospold", declared: Path | None = None
) -> Receipt:
    """Write `destination` (a zip) from the EcoSpold files under `source`.

    `declared` is the provider release `source` was patched from; see the module text.
    The zip is the same for the same input: members are sorted and carry a fixed date.
    """
    receipt = Receipt(source=str(source))
    tree, declared_tree = hashlib.sha256(), hashlib.sha256()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in find_files(source):
            content = path.read_bytes()
            _add_to_tree(tree, source, path, content)
            original = None
            if declared is not None:
                twin = declared / path.relative_to(source)
                if not twin.is_file():
                    raise AdapterError(f"{path.name} is not in the provider release {declared}")
                original = twin.read_bytes()
                _add_to_tree(declared_tree, declared, twin, original)
            info = zipfile.ZipInfo(f"{prefix}/{path.name}", date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, adapt_document(content, path.name, receipt, original))
    partial.replace(destination)
    receipt.input_tree_sha256 = tree.hexdigest()
    if declared is not None:
        receipt.declared_tree_sha256 = declared_tree.hexdigest()
    receipt.output_zip_sha256 = sha256_file(destination)
    return receipt


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="Folder with EcoSpold 1 files")
    parser.add_argument("destination", type=Path, help="Zip file to write")
    parser.add_argument(
        "--declared",
        type=Path,
        help="The provider release `source` was patched from: elementary exchanges keep "
        "the flow identity they have there",
    )
    parser.add_argument("--receipt", type=Path, help="Write what was read and changed, as JSON")
    args = parser.parse_args(argv)
    try:
        receipt = adapt_folder(args.source, args.destination, declared=args.declared)
    except AdapterError as error:
        parser.exit(1, f"{error}\n")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt.as_dict(), indent=2) + "\n")
    restored = sum(receipt.numbers_restored.values())
    print(
        f"Wrote {receipt.files} file(s) to {args.destination}; "
        f"{restored} exchange number(s) restored; "
        f"{len(receipt.source_observations)} elementary exchange(s) linked on the declared flow"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
