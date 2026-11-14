"""The patched copy as ecoSpold v1 files again: the format BAFU's release comes in.

A patch run writes the patched copy as EcoSpold 1 XML (`bafu-fixes run`), and the database
of a build is made from those files. This module packs them as one archive to hand on,
`<name>-ecospold1.zip`, and reads the archive back. Nothing is converted: a file in the
archive is the file the patch run wrote, with the label added.

The patched copy is Modified Data under BAFU's Terms of Use, and one file can be passed on
without the others. So every dataset carries the label and BAFU's credit itself, twice:

* in its extension element, `<bcf:dataset label="Modified Data" credit="...">`, beside the
  import fixes and patches that changed it (`<bcf:importFix>`, `<bcf:patch>`): for programs;
* at the start of its general comment (`referenceFunction/@generalComment`), which LCA tools
  show: for people. BAFU's own comment follows it, unchanged.

The archive also holds what `members` gives it: the record of modifications and the
statement.

Reading back (`check`): the archive holds one file for every dataset of the database and no
other; every file is valid EcoSpold 1, by the schema the patch tool checks against; every
dataset carries the label, the credit and its note; and with those taken off again, every
file is the file the patch run wrote, compared as canonical XML. The files are not compared
exchange by exchange with the database: the database was built from them.

lxml and the standard library. lxml is imported when a function runs, so that the export
step can be loaded where it is not installed.
"""

import hashlib
import zipfile
from pathlib import Path

ECOSPOLD_NS = "http://www.EcoInvent.org/EcoSpold01"
#: The namespace of the patch tool's own data in a file (`bafu_community_fixes.models`).
EXT_NS = "urn:bafu-community-fixes:extensions:1"
EXT_PREFIX = "bcf"
SCHEMA = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "bafu_community_fixes"
    / "schemas"
    / "ecospold1"
    / "EcoSpold01Dataset.xsd"
)
#: The longest text EcoSpold 1 takes in a general comment (`TString32000`).
MAX_COMMENT = 32000
#: Between the note and BAFU's own comment.
SEPARATOR = "\n\n"
#: The time of every entry of the archive: the same files give the same archive.
STAMP = (1980, 1, 1, 0, 0, 0)

_E, _X = f"{{{ECOSPOLD_NS}}}", f"{{{EXT_NS}}}"
_REFERENCE = f"{_E}metaInformation/{_E}processInformation/{_E}referenceFunction"


class EcospoldError(Exception):
    """The files can't be packed as they are."""


def _etree():
    from lxml import etree

    return etree


def _parse(data):
    """A document without the blank text between its elements, as the patch tool reads it."""
    etree = _etree()
    return etree.fromstring(data, etree.XMLParser(remove_blank_text=True, huge_tree=True))


def find_files(folder):
    """The EcoSpold files of a folder, sorted as the patch tool sorts them."""
    files = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() == ".xml")
    if not files:
        raise EcospoldError(f"No XML files in {folder}")
    return files


def code_of(name):
    """The code of the dataset a file holds: `process_<code>.xml`, as the build names nodes."""
    return Path(str(name)).stem.removeprefix("process_")


def serialise(root):
    """A document as the patch tool writes it: indented by two spaces, declared UTF-8."""
    etree = _etree()
    tree = etree.ElementTree(root)
    etree.indent(tree, space="  ")
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8")


def _drop_empty_extensions(root):
    """Take out extension elements that say nothing: no attribute, no child."""
    for dataset in root.findall(f"{_E}dataset"):
        container = dataset.find(f"{_X}extensions")
        if container is None:
            continue
        for child in list(container):
            if not child.attrib and not len(child) and not (child.text or "").strip():
                container.remove(child)
        if not len(container) and not container.attrib:
            dataset.remove(container)


def canonical(root):
    """Canonical XML of a document, without what says nothing: the blank text between
    elements (the indentation) and extension elements with no attribute and no child."""
    _drop_empty_extensions(root)
    for element in root.iter():
        if len(element) and element.text is not None and not element.text.strip():
            element.text = None
        if element is not root and element.tail is not None and not element.tail.strip():
            element.tail = None
    return _etree().tostring(root, method="c14n")


def _datasets(root):
    if root.tag != f"{_E}ecoSpold":
        raise EcospoldError(f"the root element is <{root.tag}>, not EcoSpold 1's <ecoSpold>")
    found = root.findall(f"{_E}dataset")
    if not found:
        raise EcospoldError("no dataset")
    return found


def _reference(dataset):
    found = dataset.find(_REFERENCE)
    if found is None:
        raise EcospoldError("a dataset without a referenceFunction")
    return found


def label(root, note, mark, credit):
    """Write the label into every dataset of a document: the extension, and the comment."""
    etree = _etree()
    for dataset in _datasets(root):
        reference = _reference(dataset)
        comment = reference.get("generalComment")
        text = note if comment is None else note + SEPARATOR + comment
        if len(text) > MAX_COMMENT:
            raise EcospoldError(
                f"with the note the general comment would have {len(text):,} characters, "
                f"and EcoSpold 1 takes {MAX_COMMENT:,}"
            )
        reference.set("generalComment", text)
        container = dataset.find(f"{_X}extensions")
        if container is None:
            container = etree.SubElement(dataset, f"{_X}extensions", nsmap={EXT_PREFIX: EXT_NS})
        own = container.find(f"{_X}dataset")
        if own is None:
            own = etree.Element(f"{_X}dataset")
            container.insert(0, own)
        if own.get("label") is not None or own.get("credit") is not None:
            raise EcospoldError("a dataset is labelled already: not a file of a patch run")
        own.set("label", mark)
        own.set("credit", credit)


def unlabel(root, note, mark, credit):
    """Take the label off again, in place. Returns what a dataset lacks, if anything."""
    problems = []
    try:
        datasets = _datasets(root)
    except EcospoldError as error:
        return [str(error)]
    for dataset in datasets:
        reference = dataset.find(_REFERENCE)
        comment = None if reference is None else reference.get("generalComment")
        if comment == note:
            del reference.attrib["generalComment"]
        elif comment is not None and comment.startswith(note + SEPARATOR):
            reference.set("generalComment", comment[len(note + SEPARATOR) :])
        else:
            problems.append("the general comment does not begin with the note of this dataset")
        container = dataset.find(f"{_X}extensions")
        own = None if container is None else container.find(f"{_X}dataset")
        if own is None or own.get("label") != mark or own.get("credit") != credit:
            problems.append("the extension lacks the label or the credit")
            continue
        del own.attrib["label"], own.attrib["credit"]
    return problems


def _add(archive, name, data):
    entry = zipfile.ZipInfo(name, date_time=STAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o644 << 16
    archive.writestr(entry, data)


def write(folder, path, *, notes, mark, credit, members, expected=None):
    """Pack the patched files of `folder` as the archive `path`, each with its label.

    `notes` is `{code: note}` for every dataset of the database: the files must be those
    datasets and no others. `members` is `{name: bytes}` for the files that travel inside.
    `expected` is `(files, fingerprint)` from the summary of the patch run: the files read
    must be the ones it describes, by the fingerprint the patch tool computes
    (`bafu_community_fixes.summary.fingerprint`). Raises `EcospoldError`; the caller
    removes what was written so far.
    """
    folder = Path(folder)
    files = find_files(folder)
    names = [file.relative_to(folder).as_posix() for file in files]
    codes = [code_of(name) for name in names]
    if len(set(codes)) != len(codes):
        raise EcospoldError(f"Two files of {folder} hold a dataset of one code")
    if clash := sorted(set(names) & set(members)):
        raise EcospoldError(f"A dataset file is named like the record: {clash[0]}")
    absent, unknown = sorted(set(notes) - set(codes)), sorted(set(codes) - set(notes))
    if absent or unknown:
        raise EcospoldError(
            f"The files are not the datasets of the database: {len(absent):,} dataset(s) "
            f"without a file, {len(unknown):,} file(s) without a dataset, first "
            f"{(absent or unknown)[0]!r}"
        )
    digest, size, datasets = hashlib.sha256(), 0, 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in members.items():
            _add(archive, name, data)
        for file, name, code in zip(files, names, codes, strict=True):
            data = file.read_bytes()
            digest.update(str(file.relative_to(folder)).encode() + b"\0" + data)
            size += len(data)
            try:
                root = _parse(data)
                label(root, notes[code], mark, credit)
            except (EcospoldError, _etree().XMLSyntaxError) as error:
                raise EcospoldError(f"{name}: {error}") from None
            datasets += len(root.findall(f"{_E}dataset"))
            _add(archive, name, serialise(root))
    if expected is not None and (len(files), digest.hexdigest()) != tuple(expected):
        raise EcospoldError(
            f"The files in {folder} are not the ones the summary of the patch run describes"
        )
    return {
        "files": len(files),
        "datasets": datasets,
        "bytes_before_the_label": size,
        "fingerprint_before_the_label": digest.hexdigest(),
    }


def check(path, folder, *, notes, mark, credit, members):
    """Problems found when the archive is read back; see the module text."""
    etree = _etree()
    folder = Path(folder)
    schema = etree.XMLSchema(etree.parse(str(SCHEMA)))
    sources = {file.relative_to(folder).as_posix(): file for file in find_files(folder)}
    problems = []
    with zipfile.ZipFile(path) as archive:
        listed = archive.namelist()
        names = sorted(name for name in listed if name.lower().endswith(".xml"))
        if len(set(listed)) != len(listed):
            problems.append("a name is in the archive twice")
        for name, data in members.items():
            if name not in listed:
                problems.append(f"{name}: not in the archive")
            elif archive.read(name) != data:
                problems.append(f"{name}: not the one that was written beside the archive")
        if other := sorted(set(listed) - set(names) - set(members)):
            problems.append(f"{len(other):,} file(s) that nothing accounts for, first {other[0]}")
        written = {code_of(name) for name in names}
        if absent := sorted(set(notes) - written):
            problems.append(
                f"{len(absent):,} dataset(s) of the database have no file, first {absent[0]}"
            )
        if unknown := sorted(written - set(notes)):
            problems.append(
                f"{len(unknown):,} file(s) hold no dataset of the database, first {unknown[0]}"
            )
        if set(names) != set(sources):
            problems.append(
                f"the archive holds {len(names):,} dataset files and the patch run wrote "
                f"{len(sources):,}"
            )
        for name in names:
            try:
                root = _parse(archive.read(name))
            except etree.XMLSyntaxError as error:
                problems.append(f"{name}: not XML: {str(error)[:200]}")
                continue
            if not schema.validate(root):
                first = schema.error_log[0]
                problems.append(
                    f"{name}: not valid EcoSpold 1: line {first.line}: {first.message[:200]}"
                )
            note = notes.get(code_of(name))
            if note is None:
                continue
            if mark not in note or credit not in note:
                problems.append(f"{name}: the note lacks the label or the credit")
            found = unlabel(root, note, mark, credit)
            problems += [f"{name}: {problem}" for problem in found]
            source = sources.get(name)
            if found or source is None:
                continue
            if canonical(root) != canonical(_parse(source.read_bytes())):
                problems.append(
                    f"{name}: differs from the file the patch run wrote in more than the label"
                )
    return problems
