"""The manifest of a patched release: what was built, from which release, by which patches.

    python3 scripts/release_manifest.py --summary summary.json --output OUT \
        --tag patched-2026-v1.1 --revision <commit> --out manifest.json
    python3 scripts/release_manifest.py --verify manifest.json

A patched release publishes this file and nothing else: no inventory. The manifest holds
checksums, counts, who is behind each patch, and the numbers of the datasets each patch
changed, so that a local build can prove it reproduced the release
(`bafu-fixes run latest OUT --strict --summary S`, then this script, then compare `output`).

It is written from two things a run of the patch tool leaves behind:

- the run summary (`bafu-fixes run --summary`): the release that was read, the tool, each
  step with its author and authoriser, the fingerprint of what was written;
- the written files: each dataset carries the ids of the patches that changed it
  (`bcf:extensions`), which gives the dataset numbers per patch.

It refuses, and writes nothing, when the run did not complete, when the files are not the ones
the summary describes, when the release that was read is not a known one, when a patch that
changed data has no authoriser, when the two counts of a patch's datasets disagree, or when a
patch names a finding that has no record. Standard library only.
"""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import community  # noqa: E402

FORMAT = "sentier-bafu/patched-release/1"
EXTENSIONS = "{urn:bafu-community-fixes:extensions:1}"
RESULTS = ("applied", "not needed", "failed")
SHA256 = re.compile(r"[0-9a-f]{64}")
STEP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
# What a manifest may hold, and nothing else: the release job publishes a file only if it
# has exactly this shape.
PATCH_KEYS = {"id", "description", "findings", "author", "authorised_by", "result", "datasets_changed",
              "exchanges_changed", "values_changed", "datasets"}
FIX_KEYS = {"id", "description", "result", "datasets_changed", "values_changed"}
TOP_KEYS = {"format", "tag", "built", "provider_release", "tool", "options", "import_fixes", "patches",
            "totals", "output"}


class Refused(Exception):
    pass


def files_of(folder):
    """The XML files of a patched release, as the patch tool lists them."""
    return sorted(path for path in Path(folder).rglob("*") if path.suffix.lower() == ".xml")


def fingerprint(folder, files):
    """The fingerprint the run summary carries for the written files, and their size."""
    digest, size = hashlib.sha256(), 0
    for path in files:
        data = path.read_bytes()
        digest.update(str(path.relative_to(folder)).encode() + b"\0" + data)
        size += len(data)
    return digest.hexdigest(), size


def changed_datasets(files):
    """{patch id: sorted dataset numbers} from the marks each written dataset carries."""
    changed = {}
    for path in files:
        for dataset in ET.parse(path).getroot():
            number = dataset.get("number")
            for patch in dataset.iterfind(f"{EXTENSIONS}extensions/{EXTENSIONS}dataset/{EXTENSIONS}patch"):
                changed.setdefault((patch.text or "").strip(), set()).add(int(number))
    return {patch: sorted(numbers) for patch, numbers in changed.items()}


def result_of(step):
    if step.get("error"):
        return "failed"
    return "applied" if step.get("datasets") else "not needed"


def release_id(release, config):
    """The id of the provider release in site/config.json, when that list names its archive."""
    for known in config["releases"]:
        if known.get("archive_sha256") == release["archive_sha256"] or known.get("url") == release["url"]:
            return known["id"]
    return None


def manifest(summary, folder, tag=None, revision=None, root=community.ROOT):
    """The manifest of the run that `summary` describes and `folder` holds. Raises Refused."""
    if summary.get("status") != "completed" or not summary.get("output"):
        raise Refused("the run did not complete; a release is built from a complete run")
    release = summary["release"]
    if not release.get("url") or not SHA256.fullmatch(release.get("archive_sha256") or ""):
        raise Refused("the files that were read are not a release this revision of the tool knows")
    files = files_of(folder)
    digest, size = fingerprint(folder, files)
    output = summary["output"]
    if (len(files), digest) != (output["files"], output["fingerprint"]):
        raise Refused("the files in the output folder are not the ones the summary describes")
    changed = changed_datasets(files)
    known = {record["id"] for record in community.load_findings(root)}
    patches, fixes = [], []
    for step in summary["steps"]:
        if not STEP_ID.fullmatch(step["id"]):
            raise Refused("a step has an id that is not a plain name")
        result = result_of(step)
        if result == "failed":
            raise Refused(f"step {step['id']} failed; a release holds no failed step")
        if step["kind"] != "patch":
            fixes.append({
                "id": step["id"], "description": step["description"], "result": result,
                "datasets_changed": step["datasets"], "values_changed": step["changes"],
            })
            continue
        numbers = changed.get(step["id"], [])
        if len(numbers) != step["datasets"]:
            raise Refused(
                f"patch {step['id']}: the summary counts {step['datasets']} changed datasets, "
                f"the written files carry its mark on {len(numbers)}"
            )
        if step["datasets"] and not step.get("authorised_by"):
            raise Refused(f"patch {step['id']} changed data and names nobody who authorised it")
        findings = list(step.get("findings") or [])
        for rid in findings:
            if rid not in known:
                raise Refused(f"patch {step['id']} names {rid}, which has no record")
        patches.append({
            "id": step["id"],
            "description": step["description"],
            "findings": findings,
            "author": step["authored_by"],
            "authorised_by": step.get("authorised_by"),
            "result": result,
            "datasets_changed": step["datasets"],
            "exchanges_changed": step.get("exchanges"),
            "values_changed": step["changes"],
            "datasets": numbers,
        })
    unknown = sorted(set(changed) - {patch["id"] for patch in patches})
    if unknown:
        raise Refused("the written files carry the mark of a patch the summary does not list: " + ", ".join(unknown))
    software = summary.get("software", {})
    return {
        "format": FORMAT,
        "tag": tag,
        "built": summary.get("finished"),
        "provider_release": {
            "id": release_id(release, community.load_config(root)),
            "url": release["url"],
            "archive_sha256": release["archive_sha256"],
            "fingerprint": release["fingerprint"],
            "files": release["files"],
            "datasets": release["datasets"],
            "exchanges": release["exchanges"],
        },
        "tool": {
            "name": "bafu-community-fixes",
            "version": software.get("bafu-community-fixes"),
            "revision": revision or software.get("git commit"),
        },
        "options": {key: summary.get("options", {}).get(key) for key in
                    ("XSD schema check", "extensions in output", "only patches", "skipped patches")},
        "import_fixes": fixes,
        "patches": patches,
        "totals": dict(summary["totals"]),
        "output": {"files": output["files"], "bytes": size, "fingerprint": digest},
    }


def shape_errors(data):
    """What keeps a file from being a manifest: it holds these fields, of these kinds, and no others."""
    errors = []

    def need(condition, text):
        if not condition:
            errors.append(text)

    def text(value, limit=500):
        return isinstance(value, str) and len(value) <= limit and "\n" not in value

    def count(value):
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0

    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        return ["the manifest holds other fields than a manifest has"]
    need(data["format"] == FORMAT, f"format is not {FORMAT}")
    need(data["tag"] is None or (text(data["tag"], 100) and re.fullmatch(r"[A-Za-z0-9._+-]+", data["tag"])), "tag")
    need(data["built"] is None or text(data["built"], 40), "built")
    release = data["provider_release"]
    need(isinstance(release, dict) and set(release) == {"id", "url", "archive_sha256", "fingerprint", "files",
                                                         "datasets", "exchanges"}, "provider_release")
    if isinstance(release, dict) and not errors:
        need(release["id"] is None or text(release["id"], 40), "provider_release.id")
        need(text(release["url"]) and release["url"].startswith("https://"), "provider_release.url")
        need(all(SHA256.fullmatch(str(release[key])) for key in ("archive_sha256", "fingerprint")), "provider_release checksums")
        need(all(count(release[key]) for key in ("files", "datasets", "exchanges")), "provider_release counts")
    tool = data["tool"]
    need(isinstance(tool, dict) and set(tool) == {"name", "version", "revision"}
         and all(value is None or text(value, 100) for value in tool.values()), "tool")
    need(isinstance(data["options"], dict) and len(data["options"]) <= 10 and all(
        text(key, 60) and (value is None or isinstance(value, bool) or text(value, 200))
        for key, value in data["options"].items()), "options")
    need(isinstance(data["totals"], dict) and all(text(k, 40) and count(v) for k, v in data["totals"].items()), "totals")
    output = data["output"]
    need(isinstance(output, dict) and set(output) == {"files", "bytes", "fingerprint"} and count(output.get("files"))
         and count(output.get("bytes")) and SHA256.fullmatch(str(output.get("fingerprint"))), "output")
    for name, keys in (("import_fixes", FIX_KEYS), ("patches", PATCH_KEYS)):
        steps = data[name]
        if not isinstance(steps, list) or len(steps) > 10000:
            errors.append(name)
            continue
        for step in steps:
            if not isinstance(step, dict) or set(step) != keys:
                errors.append(f"{name}: a step holds other fields than a step has")
                continue
            where = f"{name} {step['id']}" if text(step["id"], 100) else name
            need(text(step["id"], 100) and STEP_ID.fullmatch(step["id"]), f"{where}: id")
            need(text(step["description"], 1000), f"{where}: description")
            need(step["result"] in RESULTS, f"{where}: result")
            need(count(step["datasets_changed"]) and count(step["values_changed"]), f"{where}: counts")
            if name == "patches":
                need(text(step["author"], 200) and (step["authorised_by"] is None or text(step["authorised_by"], 200)),
                     f"{where}: author and authoriser")
                need(isinstance(step["findings"], list)
                     and all(isinstance(f, str) and re.fullmatch(r"F[1-9][0-9]*", f) for f in step["findings"]),
                     f"{where}: findings")
                need(step["exchanges_changed"] is None or count(step["exchanges_changed"]), f"{where}: exchanges")
                need(isinstance(step["datasets"], list) and all(count(n) for n in step["datasets"])
                     and step["datasets"] == sorted(set(step["datasets"]))
                     and len(step["datasets"]) == step["datasets_changed"], f"{where}: dataset numbers")
    return errors


def notes(data):
    """The text of the release: what the manifest says, in words. No inventory."""
    release = data["provider_release"]
    lines = [
        f"Patched release `{data['tag']}`." if data["tag"] else "Patched release.",
        "",
        "This release publishes `manifest.json` only. It holds no inventory: build the patched release "
        "yourself with the patch tool at the revision below, and compare the fingerprint of what you built.",
        "",
        f"- Provider release: {release['url']} (archive SHA-256 `{release['archive_sha256']}`), "
        f"{release['datasets']:,} datasets",
        f"- Tool: {data['tool']['name']} {data['tool']['version'] or ''} at revision `{data['tool']['revision']}`",
        f"- Output: {data['output']['files']:,} files, fingerprint `{data['output']['fingerprint']}`",
        f"- Import fixes: {len(data['import_fixes'])}; community patches: {len(data['patches'])}",
        "",
        "| Patch | Findings | Author | Authorised by | Result | Datasets changed |",
        "|---|---|---|---|---|---:|",
    ]
    for patch in data["patches"]:
        cells = [patch["id"], ", ".join(patch["findings"]) or "none", patch["author"],
                 patch["authorised_by"] or "nobody yet", patch["result"], f"{patch['datasets_changed']:,}"]
        lines.append("| " + " | ".join(str(cell).replace("|", "/") for cell in cells) + " |")
    lines += ["", "A community patch is not a correction by the provider. The provider decides what it changes."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--summary", type=Path, help="the run summary written by `bafu-fixes run --summary`")
    parser.add_argument("--output", type=Path, help="the folder the run wrote")
    parser.add_argument("--tag", help="the tag of the release")
    parser.add_argument("--revision", help="the commit the tool was run at")
    parser.add_argument("--out", type=Path, help="where to write the manifest")
    parser.add_argument("--notes", type=Path, help="also write the text of the release here")
    parser.add_argument("--verify", type=Path, metavar="MANIFEST", help="check that a file is a manifest and nothing else")
    parser.add_argument("--root", type=Path, default=community.ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.verify:
        try:
            data = json.loads(args.verify.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print(f"{args.verify.name}: not a JSON file")
            return 1
        errors = shape_errors(data)
        for error in errors[:20]:
            print(f"{args.verify.name}: {error}")
        if errors:
            return 1
        if args.notes:
            args.notes.write_text(notes(data), encoding="utf-8")
        print(f"{args.verify.name}: a manifest of {len(data['patches'])} patches, and nothing else")
        return 0
    if not (args.summary and args.output and args.out):
        parser.error("--summary, --output and --out are needed to write a manifest")
    try:
        data = manifest(json.loads(args.summary.read_text(encoding="utf-8")), args.output, args.tag,
                        args.revision, args.root.resolve())
    except Refused as refusal:
        print(f"No manifest written: {refusal}")
        return 1
    errors = shape_errors(data)
    if errors:
        print("No manifest written: " + "; ".join(errors[:5]))
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.notes:
        args.notes.write_text(notes(data), encoding="utf-8")
    print(f"{args.out}: {len(data['patches'])} patches, {len(data['import_fixes'])} import fixes, "
          f"output fingerprint {data['output']['fingerprint']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
