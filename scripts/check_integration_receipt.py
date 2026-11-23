"""Check the integration receipt for sentier-bafu#19 against Git objects.

    python3 scripts/check_integration_receipt.py [--rev HEAD]

Reads only Git objects: the two source commits, the integration merge commit and
`--rev`. It fails unless:

- the merge commit has exactly the two source heads as parents and is an ancestor of
  `--rev`, and the merge tree is the union of both source trees, every file identical to
  its source except the declared resolutions of the paths both sources track;
- every difference between the merge and `--rev` is declared: a changed file in
  `changed_after_merge`, a new file in `added_after_merge` (each with a reason), a removed
  file only as the source path of a `moved` or `retired` entry;
- every tracked file of both sources has exactly one entry, with a disposition from
  DISPOSITIONS, matching source and destination SHA-256 (destination read at `--rev`), and
  the full tree at `--rev` is accounted for;
- the disposition counts computed from the entries equal the stated counts;
- the composed files keep the community text, nothing current links into a verbatim
  history copy, both inventories match their commits, and the preserved community
  interfaces and workspace records are present at `--rev`.

Exits non-zero on any failure.
"""

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = "docs/plans/bafu-community"
RECEIPT = f"{PLAN}/integration-receipt.json"
DISPOSITIONS = ("kept unchanged", "merged", "moved", "retired")


def git(*args: str, binary: bool = False):
    out = subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout
    return out if binary else out.decode()


def is_ancestor(commit: str, rev: str) -> bool:
    command = ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, rev]
    return subprocess.run(command, capture_output=True).returncode == 0


def tree(rev: str) -> dict[str, str]:
    """Path -> blob id of every tracked file at `rev`."""
    entries = git("ls-tree", "-r", "-z", rev).split("\0")[:-1]
    return {path: meta.split()[2] for meta, path in (e.split("\t", 1) for e in entries)}


def blob(rev: str, path: str) -> bytes:
    return git("show", f"{rev}:{path}", binary=True)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def check_merge(receipt: dict, errors: list[str]) -> None:
    merge, sources = receipt["merge_commit"], receipt["sources"]
    ws, cm = sources["workspace"]["commit"], sources["community"]["commit"]
    parents = git("log", "-1", "--format=%P", merge).split()
    if parents != [ws, cm] or receipt["merge_parents"] != parents:
        errors.append(f"merge {merge[:12]} parents {parents} are not [workspace, community]")
    ws_tree, cm_tree, merge_tree = tree(ws), tree(cm), tree(merge)
    shared = sorted(set(ws_tree) & set(cm_tree))
    resolutions = receipt["merge_resolutions"]
    if sorted(resolutions) != shared:
        errors.append(f"merge resolutions {sorted(resolutions)} are not the shared paths {shared}")
    if set(merge_tree) != set(ws_tree) | set(cm_tree):
        errors.append(
            "merge tree is not the union of both source trees: "
            f"{sorted(set(merge_tree) ^ (set(ws_tree) | set(cm_tree)))}"
        )
    for path, blob_id in merge_tree.items():
        if path in resolutions:
            continue
        if blob_id != ws_tree.get(path, cm_tree.get(path)):
            errors.append(f"{path} differs from its source in the merge but is not a resolution")
    for path, resolution in resolutions.items():
        if not resolution.get("reason"):
            errors.append(f"merge resolution of {path} has no reason")
    # The resolutions themselves: community text kept.
    if merge_tree.get("LICENSE") != cm_tree.get("LICENSE") or ws_tree.get("LICENSE") != cm_tree.get(
        "LICENSE"
    ):
        errors.append("LICENSE is not the identical text of both sources at the merge")
    if merge_tree.get("README.md") != cm_tree.get("README.md"):
        errors.append("README.md at the merge is not the community README unchanged")
    if not blob(merge, ".gitignore").startswith(blob(cm, ".gitignore")):
        errors.append(".gitignore at the merge does not start with the community rules")


def check_after_merge(receipt: dict, rev: str, errors: list[str]) -> dict[str, str]:
    merge = receipt["merge_commit"]
    if not is_ancestor(merge, rev):
        errors.append(f"merge commit {merge[:12]} is not an ancestor of {rev}")
    merge_tree, rev_tree = tree(merge), tree(rev)
    changed = {p for p in set(merge_tree) & set(rev_tree) if merge_tree[p] != rev_tree[p]}
    added = set(rev_tree) - set(merge_tree)
    removed = set(merge_tree) - set(rev_tree)

    declared_changed = {e["path"]: e for e in receipt["changed_after_merge"]}
    declared_added = {e["path"]: e for e in receipt["added_after_merge"]}
    for kind, declared in (("changed", declared_changed), ("added", declared_added)):
        errors += [
            f"{kind}_after_merge {p} has no reason"
            for p, e in declared.items()
            if not e.get("reason")
        ]
    if changed != set(declared_changed):
        errors.append(
            f"changed after the merge but not declared: {sorted(changed - set(declared_changed))}; "
            f"declared but unchanged: {sorted(set(declared_changed) - changed)}"
        )
    if added != set(declared_added):
        errors.append(
            f"added after the merge but not declared: {sorted(added - set(declared_added))}; "
            f"declared but not added: {sorted(set(declared_added) - added)}"
        )
    allowed_removed = {
        e["path"]
        for e in receipt["files"]
        if e["disposition"] in {"moved", "retired"} and e.get("destination") != e["path"]
    }
    if removed != allowed_removed:
        errors.append(
            "removed after the merge without a moved/retired entry: "
            f"{sorted(removed - allowed_removed)}; "
            f"moved/retired but still present: {sorted(allowed_removed - removed)}"
        )
    for path, entry in declared_added.items():
        if entry.get("sha256") is None:
            if not entry.get("sha256_omitted"):
                errors.append(
                    f"added_after_merge {path} has neither sha256 nor a reason to omit it"
                )
        elif path in rev_tree and sha(blob(rev, path)) != entry["sha256"]:
            errors.append(f"added_after_merge {path} hash mismatch at {rev}")
    return rev_tree


def check_files(receipt: dict, rev: str, rev_tree: dict[str, str], errors: list[str]) -> None:
    sources = receipt["sources"]
    seen = Counter((e["source"], e["path"]) for e in receipt["files"])
    expected = Counter(
        (name, path) for name, record in sources.items() for path in tree(record["commit"])
    )
    if seen != expected:
        errors.append(
            "source files not accounted exactly once: "
            f"{sorted((seen - expected) + (expected - seen))}"
        )

    for e in receipt["files"]:
        where, disposition = f"{e['source']}:{e['path']}", e["disposition"]
        if disposition not in DISPOSITIONS:
            errors.append(f"{where}: disposition {disposition!r} is not one of {DISPOSITIONS}")
            continue
        source_sha = sha(blob(sources[e["source"]]["commit"], e["path"]))
        if source_sha != e["source_sha256"]:
            errors.append(f"{where}: source hash mismatch")
        if disposition == "retired":
            if not e.get("successor") or not e.get("reason"):
                errors.append(f"{where}: retired without a successor and a reason")
            if e["path"] in rev_tree:
                errors.append(f"{where}: retired but still present at {rev}")
            continue
        dest = e["destination"]
        if dest not in rev_tree:
            errors.append(f"{where}: destination {dest} missing at {rev}")
            continue
        dest_sha = sha(blob(rev, dest))
        if dest_sha != e["destination_sha256"]:
            errors.append(f"{where}: destination {dest} hash mismatch at {rev}")
        if disposition in {"kept unchanged", "moved"} and dest_sha != source_sha:
            errors.append(f"{where}: {disposition} but not byte-identical at {rev}")
        if disposition == "kept unchanged" and dest != e["path"]:
            errors.append(f"{where}: kept unchanged but its destination is {dest}")
        if disposition == "moved" and dest == e["path"]:
            errors.append(f"{where}: moved but its destination is its own path")
        if disposition in {"merged", "moved"} and not e.get("reason"):
            errors.append(f"{where}: {disposition} without a reason")
        if disposition == "merged" and dest_sha == source_sha:
            errors.append(f"{where}: merged but byte-identical to its source")
        copy = e.get("verbatim_copy")
        if copy and (copy not in rev_tree or sha(blob(rev, copy)) != source_sha):
            errors.append(f"{where}: {copy} is not a verbatim copy at {rev}")

    accounted = {e["destination"] for e in receipt["files"] if e["disposition"] != "retired"}
    accounted |= {e["path"] for e in receipt["added_after_merge"]}
    if set(rev_tree) != accounted:
        errors.append(f"tree at {rev} not fully accounted: {sorted(set(rev_tree) ^ accounted)}")

    computed: dict[str, dict[str, int]] = {}
    for e in receipt["files"]:
        by_source = computed.setdefault(e["source"], dict.fromkeys(DISPOSITIONS, 0))
        if e["disposition"] in by_source:
            by_source[e["disposition"]] += 1
    if receipt["counts"] != computed:
        errors.append(f"stated counts {receipt['counts']} differ from the entries {computed}")


def check_content(receipt: dict, rev: str, rev_tree: dict[str, str], errors: list[str]) -> None:
    cm = receipt["sources"]["community"]["commit"]
    ws = receipt["sources"]["workspace"]["commit"]

    readme, original = blob(rev, "README.md").decode(), blob(cm, "README.md").decode()
    start = readme.find("## Review workspace\n")
    if start < 0 or readme[:start] != original[: original.find("## License\n")]:
        errors.append("README.md: community text before its License section is not preserved")
    licence = " ".join(readme[readme.find("\n## License\n") :].split())
    notices = ("MIT", "EcoSpold Public License", "Open Database License", "Open Font", "CC BY")
    if not all(term in licence for term in notices):
        errors.append("README.md: the License section lost a notice")
    if not blob(rev, ".gitignore").startswith(blob(cm, ".gitignore")):
        errors.append(".gitignore: community rules are not an unchanged prefix")
    data_readme = "src/bafu_community_fixes/data/README.md"
    kept = paragraphs(blob(rev, data_readme).decode())
    original_paragraphs = paragraphs(blob(cm, data_readme).decode())
    if [p for p in kept if p in original_paragraphs] != original_paragraphs:
        errors.append(f"{data_readme}: a community paragraph was changed, dropped or reordered")

    copies = {e["verbatim_copy"] for e in receipt["files"] if e.get("verbatim_copy")}
    for path in rev_tree:
        if path.endswith(".md") and path not in copies:
            text = blob(rev, path).decode(errors="replace")
            for target in re.findall(r"\]\(([^)#\s]+)", text):
                if (
                    "://" not in target
                    and posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
                    in copies
                ):
                    errors.append(f"{path} links into the verbatim history copy {target}")

    inventory = json.loads(blob(rev, receipt["source_inventory"]))
    pinned = json.loads(blob(rev, f"{PLAN}/source-inventory.json"))
    if {s["commit"] for s in inventory["sources"].values()} != {ws, cm}:
        errors.append("the dated source inventory is not for the two source commits")
    for record in (*inventory["sources"].values(), *pinned["sources"].values()):
        commit, listed = record["commit"], record["files"]
        if [f["path"] for f in listed] != sorted(tree(commit)) or record["file_count"] != len(
            listed
        ):
            errors.append(f"inventory for {commit[:7]} does not list exactly its tracked files")
        errors += [
            f"inventory hash mismatch {commit[:7]}:{f['path']}"
            for f in listed
            if sha(blob(commit, f["path"])) != f["sha256"]
        ]

    pyproject = tomllib.loads(blob(rev, "pyproject.toml").decode())
    pyproject.get("tool", {}).get("ruff", {}).pop("extend-exclude", None)
    if pyproject != tomllib.loads(blob(cm, "pyproject.toml").decode()):
        errors.append("pyproject.toml differs from the community one beyond the ruff exclude")
    models = blob(rev, "src/bafu_community_fixes/models.py").decode()
    if 'EXT_NS = "urn:bafu-community-fixes:extensions:1"' not in models:
        errors.append("XML extension namespace changed")
    data = json.loads(
        blob(rev, "src/bafu_community_fixes/data/brightway-flows-corrections-bafu-2026-v1.json")
    )
    if (len(data["corrections"]), len(data["excluded"])) != (53, 26):
        errors.append("Brightway Flows data no longer has 53 corrections and 26 exclusions")
    patches = sorted(
        m.group(1)
        for p in rev_tree
        if (m := re.fullmatch(r"src/bafu_community_fixes/patches/p(\d{4})_\w+\.py", p))
    )
    if patches != [f"{n:04d}" for n in range(1, 12)]:
        errors.append(f"patch modules are not exactly 0001-0011: {patches}")
    fixes = blob(rev, "src/bafu_community_fixes/import_fixes.py").decode()
    if fixes.count("@import_fix(") != 14:
        errors.append("import_fixes.py no longer registers 14 import fixes")

    def finding_ids(commit: str) -> set[str]:
        return set(
            re.findall(r"^\| (F\d+) \|", blob(commit, "community/findings.md").decode(), re.M)
        )

    if not {f"F{n}" for n in range(1, 12)} <= finding_ids(ws) <= finding_ids(rev):
        errors.append("findings ledger lost an entry (F1-F11 and every finding at the source)")
    for record in ("community/contributions/C001.json", "community/contributions/C002.json"):
        if record not in rev_tree:
            errors.append(f"contribution record {record} missing")


def check(rev: str) -> list[str]:
    rev = git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()
    receipt = json.loads(blob(rev, RECEIPT))
    for commit in (receipt["merge_commit"], *(s["commit"] for s in receipt["sources"].values())):
        if subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True
        ).returncode:
            return [f"commit {commit} named in the receipt is not in this repository"]
    errors: list[str] = []
    check_merge(receipt, errors)
    rev_tree = check_after_merge(receipt, rev, errors)
    check_files(receipt, rev, rev_tree, errors)
    check_content(receipt, rev, rev_tree, errors)

    print(
        f"Receipt at {rev[:12]}: {len(receipt['files'])} source entries, merge "
        f"{receipt['merge_commit'][:12]}, {len(rev_tree)} files at --rev"
    )
    for name, by_disposition in receipt["counts"].items():
        print(f"  {name}: " + ", ".join(f"{n} {d}" for d, n in by_disposition.items()))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rev", default="HEAD")
    problems = check(parser.parse_args().rev)
    print("\n".join(problems) if problems else "All receipt checks passed.")
    raise SystemExit(int(bool(problems)))
