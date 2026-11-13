"""Write community/patches.json: a snapshot of the community patch registry.

Run: python3 scripts/patches_snapshot.py --ref origin/pr-40

The patch tool (bafu-community-fixes) is not in this repository yet, so the site cannot read
its registry at build time. This script reads the patch modules of a git revision instead,
without importing them, and writes what the site and `community.py check` need: for each patch
its id, slug, description, author, who authorised it, the findings it answers and its source
at that pinned revision. Once the patch tool is in this repository, the build reads the
registry directly and this file and script go.

Which findings a patch answers comes, in this order, from: the `declared_findings` block of
the existing community/patches.json (kept by hand, for patches whose references do not name
an issue of this repository); a `findings=` argument of the patch, once the tool has one; the
patch's references to issues of this repository, joined to the finding records by issue.
Standard library only.
"""

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import community  # noqa: E402

ROOT = community.ROOT
PATCH_FOLDER = "src/bafu_community_fixes/patches"
NOTE = (
    "Snapshot of the community patch registry, written by scripts/patches_snapshot.py from the "
    "revision named in `source`. Patches are not copied into finding records: the site joins "
    "them to findings from this file. Once the patch tool is in this repository, the build "
    "reads its registry directly and this file goes. Edit `declared_findings` by hand; "
    "regenerate the rest."
)


def git(*args):
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True
    ).stdout


def constants(tree):
    """Module-level names bound to a string, such as ID = "0001-…"."""
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value.value
    return found


def value(node, names):
    """A string, None, or a tuple of strings, as written in the decorator."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(value(item, names) for item in node.elts)
    raise ValueError(f"cannot read {ast.dump(node)[:80]}")


def registered(source, path):
    """The patches a module registers with @patch(...): [(registry id, arguments, description)]."""
    tree = ast.parse(source, filename=path)
    names = constants(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not (isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "patch"):
                continue
            wanted = {"authored_by", "authorised_by", "references", "findings"}
            arguments = {k.arg: value(k.value, names) for k in decorator.keywords if k.arg in wanted}
            description = (ast.get_docstring(node) or "").strip().splitlines()
            if not description:
                raise ValueError(f"{path}: the patch has no docstring")
            found.append((value(decorator.args[0], names), arguments, description[0]))
    return found


def snapshot(ref, declared, findings, repository):
    revision = git("rev-parse", f"{ref}^{{commit}}").strip()
    by_issue = {}
    for record in findings:
        if record.get("issue"):
            by_issue.setdefault(record["issue"], []).append(record["id"])
    issue = re.compile(re.escape(repository) + r"/issues/(\d+)$")
    patches = []
    for path in git("ls-tree", "-r", "--name-only", revision, "--", PATCH_FOLDER).split():
        if not re.fullmatch(r"p\d{4}_\w+\.py", Path(path).name):
            continue
        for key, arguments, description in registered(git("show", f"{revision}:{path}"), path):
            number, _, slug = key.partition("-")
            if key in declared:
                answers = list(declared[key]["findings"])
            elif "findings" in arguments:
                answers = list(arguments["findings"])
            else:
                answers = [
                    rid
                    for url in arguments.get("references", ())
                    if (match := issue.fullmatch(url))
                    for rid in by_issue.get(int(match.group(1)), [])
                ]
            patches.append(
                {
                    "id": number,
                    "slug": slug,
                    "description": description,
                    "findings": sorted(set(answers), key=lambda rid: int(rid[1:])),
                    "author": arguments["authored_by"],
                    "authorised_by": arguments.get("authorised_by"),
                    "url": f"{repository}/blob/{revision}/{path}",
                }
            )
    unknown = set(declared) - {f"{p['id']}-{p['slug']}" for p in patches}
    if unknown:
        raise SystemExit(f"declared_findings names patches the registry does not have: {sorted(unknown)}")
    return {
        "schema": "sentier-bafu/patches/1",
        "note": NOTE,
        "source": {"repository": repository, "revision": revision, "path": PATCH_FOLDER},
        "declared_findings": declared,
        "patches": sorted(patches, key=lambda p: p["id"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--ref", required=True, help="git revision that holds the patch tool, such as origin/pr-40")
    parser.add_argument("--out", type=Path, default=ROOT / community.PATCHES_FILE)
    args = parser.parse_args()
    declared = community.read(args.out).get("declared_findings", {}) if args.out.exists() else {}
    config = community.load_config(ROOT)
    data = snapshot(args.ref, declared, community.load_findings(ROOT), config["repository"])
    problems = community.patch_errors(data)
    if problems:
        raise SystemExit("\n".join(problems))
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    with_finding = sum(bool(p["findings"]) for p in data["patches"])
    print(f"{args.out}: {len(data['patches'])} patches at {data['source']['revision'][:12]}, {with_finding} answer a finding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
