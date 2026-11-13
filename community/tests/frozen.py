"""The frozen records that tests of rules read: see fixtures/frozen/README.md.

    RECORDS       a small tree with the frozen records: community/findings, community/patches.json,
                  community/contributions, community/recommendations and site/config.json
    workspace(t)  a copy of RECORDS at `t`, to change one thing and look at the whole
    repository()  a copy of this repository with the frozen records in place of its own, for
                  tests that build the site; made once per test run

A test that reads the repository's own records breaks when a real finding moves on.
"""

import atexit
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent / "fixtures/frozen"
# What the frozen tree replaces in a copy of the repository.
REPLACED = ("community/findings", "community/contributions", "community/recommendations", "community/patches.json")
# The keys of site/config.json that belong to the records; the rest describes the site's pages.
RECORD_KEYS = ("dataset", "provider", "releases", "repository", "site_url")
_made = {}


def workspace(target):
    """The frozen records at `target`, with the paths the scripts expect."""
    target = Path(target)
    shutil.copytree(RECORDS / "community", target / "community")
    (target / "site").mkdir(parents=True, exist_ok=True)
    shutil.copy(RECORDS / "site/config.json", target / "site/config.json")
    return target


def copy_repository(target):
    """A copy of this repository at `target` with the frozen records in place of its own."""
    target = Path(target)
    shutil.copytree(
        ROOT, target,
        ignore=shutil.ignore_patterns(".git", "_site", ".local", "__pycache__", ".venv", "fixtures"),
    )
    for name in REPLACED:
        path = target / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        source = RECORDS / name
        if source.is_dir():
            shutil.copytree(source, path)
        else:
            shutil.copy(source, path)
    config = json.loads((ROOT / "site/config.json").read_text())
    frozen = json.loads((RECORDS / "site/config.json").read_text())
    config.pop("stale_after_days", None)
    config.update({key: frozen[key] for key in RECORD_KEYS})
    (target / "site/config.json").write_text(json.dumps(config, indent=2) + "\n")
    return target


def repository():
    """The same, made once for the whole test run and removed when it ends."""
    if "root" not in _made:
        folder = tempfile.mkdtemp(prefix="frozen-repository-")
        atexit.register(shutil.rmtree, folder, ignore_errors=True)
        _made["root"] = copy_repository(Path(folder) / "repo")
    return _made["root"]
