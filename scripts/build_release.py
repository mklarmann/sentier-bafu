"""Build a Brightway database from a BAFU release folder, and audit it.

    python3 scripts/build_release.py build RELEASE OUT            # the patched release
    python3 scripts/build_release.py build RELEASE OUT --no-patches   # the provider release
    python3 scripts/build_release.py build latest OUT             # download the release first
    python3 scripts/build_release.py compare BASELINE CANDIDATE --out comparison.json

`build` runs these steps and records each one's time and peak memory in `OUT/build.json`:

1. patch    `bafu-fixes run` writes the patched release (skipped with `--no-patches`)
2. adapt    the release becomes the zip sentier-importers reads (`release_build/adapter.py`)
3. import   sentier-importers writes the inventory tables
4. data     the pinned flow terms, methods and mapping are fetched and checked
5. install  sentier-brightway writes the Brightway database and the EF 3.1 methods
6. audit    `release_build/audit_brightway.py` reads the database back and scores it

sentier-importers and sentier-brightway are used at the commits in `release_build/pins.toml`,
each in its own `uv` environment. This script needs Python 3.12 or newer, `uv` and `git`.

Everything is written under `OUT`. The built database holds BAFU's inventory, which is under
BAFU's Terms of Use: keep `OUT` local, and never upload it from a CI job.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_build import adapter  # noqa: E402

REPOSITORY = Path(__file__).resolve().parents[1]
HELPERS = REPOSITORY / "scripts" / "release_build"
PINS = HELPERS / "pins.toml"
# Where sentier-importers' registry expects BAFU's release, below its data root
IMPORTER_INPUT = Path("sources") / "bafu-2026" / "BAFU-2026 v1_ecoSpold v1.zip"
IMPORTER_SOURCES = ("bafu-processes", "bafu-exchanges")
PINNED_DATA = ("sentier-vocab", "sentier-methods", "sentier-mappings")
STEPS = ("patch", "adapt", "import", "data", "install", "audit")


class BuildError(Exception):
    """A step failed or a precondition doesn't hold; the message says which."""


# --- Running steps ---------------------------------------------------------------------


def peak_memory_mb(max_rss: int) -> float:
    """`ru_maxrss` in megabytes: it is in bytes on macOS and in kilobytes on Linux."""
    return round(max_rss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def run(
    command: list[str],
    env: dict[str, str] | None = None,
    log: Path | None = None,
    accept: tuple[int, ...] = (0,),
) -> dict:
    """Run a command; return its wall time and the peak memory of its process tree.

    An exit code outside `accept` stops the build, with the end of the log in the message.
    """
    started = time.perf_counter()
    with log.open("w") if log else open(os.devnull, "w") as stream:
        process = subprocess.Popen(
            command, env={**os.environ, **(env or {})}, stdout=stream, stderr=subprocess.STDOUT
        )
        _, status, usage = os.wait4(process.pid, 0)
        process.returncode = os.waitstatus_to_exitcode(status)
    result = {
        "command": command,
        "seconds": round(time.perf_counter() - started, 1),
        "peak_memory_mb": peak_memory_mb(usage.ru_maxrss),
        "returncode": process.returncode,
    }
    if process.returncode not in accept:
        tail = (
            "".join(log.read_text(errors="replace").splitlines(keepends=True)[-15:]) if log else ""
        )
        raise BuildError(f"{' '.join(command[:6])} ... exited with {process.returncode}\n{tail}")
    return result


class Tool:
    """A pinned checkout of another repository, run in its own `uv` environment."""

    def __init__(self, name: str, pin: dict, folder: Path, venvs: Path | None):
        self.name, self.pin, self.folder, self.venvs = name, pin, folder, venvs

    def ensure(self, allow_unpinned: bool) -> str:
        """Clone the checkout if it is missing; return the commit it is at."""
        if not self.folder.exists():
            self.folder.parent.mkdir(parents=True, exist_ok=True)
            _git("clone", "--quiet", self.pin["repository"], str(self.folder))
            _git("-C", str(self.folder), "checkout", "--quiet", self.pin["commit"])
        commit = _git("-C", str(self.folder), "rev-parse", "HEAD")
        changed = _git("-C", str(self.folder), "status", "--porcelain", "--untracked-files=no")
        if (commit != self.pin["commit"] or changed) and not allow_unpinned:
            raise BuildError(
                f"{self.name} at {self.folder} is at {commit[:12]}"
                f"{' with local changes' if changed else ''}; the pin is "
                f"{self.pin['commit'][:12]}. Check out the pin or pass --allow-unpinned."
            )
        return commit + (" (with local changes)" if changed else "")

    def command(self, *arguments: str) -> list[str]:
        extra = ["--extra", self.pin["extra"]] if self.pin.get("extra") else []
        python = ["--python", self.pin["python"]] if self.pin.get("python") else []
        return ["uv", "run", "--frozen", "--project", str(self.folder), *python, *extra, *arguments]

    def env(self) -> dict[str, str]:
        if self.venvs is None:
            return {}
        return {"UV_PROJECT_ENVIRONMENT": str(self.venvs / self.name)}


def _git(*arguments: str) -> str:
    done = subprocess.run(["git", *arguments], capture_output=True, text=True)
    if done.returncode != 0:
        raise BuildError(f"git {' '.join(arguments)}: {done.stderr.strip()}")
    return done.stdout.strip()


def load_pins(path: Path = PINS) -> dict:
    return tomllib.loads(path.read_text())["tools"]


# --- The build -------------------------------------------------------------------------


def plan(args: argparse.Namespace) -> dict:
    """Every path of a build, from its options. No file is touched."""
    out = args.out.resolve()
    patched = not args.no_patches
    return {
        "label": args.label
        or ("patched release (community patches applied)" if patched else "provider release"),
        "patched": patched,
        "release": args.release.resolve(),
        "out": out,
        "patched_release": out / "release",
        "patch_report": out / "release-report.html",
        "importer_root": out / "importer-root",
        "importer_zip": out / "importer-root" / IMPORTER_INPUT,
        "importer_output": out / "importer-output",
        "importer_cache": out / "importer-cache",
        "receipt": out / "adapter-receipt.json",
        "pinned_data": (args.pinned_data or out / "pinned-data").resolve(),
        "data_root": out / "data-root",
        "brightway_dir": (args.brightway_dir or out / "brightway").resolve(),
        "project": args.project or ("bafu-2026-v1-patched" if patched else "bafu-2026-v1"),
        "audit": out / "audit",
        "logs": out / "logs",
        "record": out / "build.json",
    }


def latest_release(venvs: Path | None) -> Path:
    """The folder the patch tool keeps BAFU's latest release in, downloading it if needed.

    The patch tool checks the download against a known SHA-256 and keeps it in the user's
    cache folder. Used for `build latest OUT`.
    """
    code = "from bafu_community_fixes.download import latest_release; print(latest_release())"
    env = {"UV_PROJECT_ENVIRONMENT": str(venvs / "bafu-fixes")} if venvs else {}
    done = subprocess.run(
        ["uv", "run", "--frozen", "--project", str(REPOSITORY), "python", "-c", code],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )
    if done.returncode != 0:
        raise BuildError(f"Could not get the latest release: {done.stderr.strip()[-500:]}")
    return Path(done.stdout.strip().splitlines()[-1])


def build(args: argparse.Namespace) -> int:
    for program in ("uv", "git"):
        if shutil.which(program) is None:
            raise BuildError(f"`{program}` is not on the PATH")
    if str(args.release) == "latest":
        args.release = latest_release(args.venvs.resolve() if args.venvs else None)
    paths = plan(args)
    out = paths["out"]
    if not paths["release"].is_dir():
        raise BuildError(f"{paths['release']} is not a folder")
    if out.exists() and any(out.iterdir()):
        raise BuildError(f"{out} is not empty; a build starts in an empty folder")
    paths["logs"].mkdir(parents=True)

    pins = load_pins(args.pins)
    tools_dir = (args.tools or out / "tools").resolve()
    venvs = args.venvs.resolve() if args.venvs else None
    importers = Tool(
        "sentier-importers", pins["sentier-importers"], tools_dir / "sentier-importers", venvs
    )
    brightway = Tool(
        "sentier-brightway", pins["sentier-brightway"], tools_dir / "sentier-brightway", venvs
    )
    record = {
        "label": paths["label"],
        "patched": paths["patched"],
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "running",
        "release": {"folder": str(paths["release"])},
        "tools": {
            "this repository": _repository_commit(),
            importers.name: importers.ensure(args.allow_unpinned),
            brightway.name: brightway.ensure(args.allow_unpinned),
            "uv": subprocess.run(
                ["uv", "--version"], capture_output=True, text=True
            ).stdout.strip(),
            "python": platform.python_version(),
            "platform": platform.platform(terse=True),
        },
        "project": paths["project"],
        "steps": {},
    }

    def step(
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        accept: tuple[int, ...] = (0,),
    ) -> None:
        """Run one command of a step; a step of several commands adds up their times."""
        commands = record["steps"].get(name, {}).get("commands", [])
        log = paths["logs"] / f"{name}{len(commands) + 1 if commands else ''}.log"
        print(f"[{name}] {' '.join(command[:8])} ...", flush=True)
        result = run(command, env, log, accept)
        previous = record["steps"].get(name, {"seconds": 0.0, "peak_memory_mb": 0.0})
        record["steps"][name] = {
            "commands": [*commands, command],
            "seconds": round(previous["seconds"] + result["seconds"], 1),
            "peak_memory_mb": max(previous["peak_memory_mb"], result["peak_memory_mb"]),
            "returncode": result["returncode"],
        }

    try:
        # 1. patch
        source = paths["release"]
        if paths["patched"]:
            options = ["--xsd-check", args.xsd_check, "--report", str(paths["patch_report"])]
            for flag, ids in (("--only", args.only), ("--skip", args.skip)):
                if ids:
                    options += [flag, *ids]
            patch_env = {"UV_PROJECT_ENVIRONMENT": str(venvs / "bafu-fixes")} if venvs else {}
            step(
                "patch",
                [
                    *("uv", "run", "--frozen", "--project", str(REPOSITORY), "bafu-fixes", "run"),
                    *(str(source), str(paths["patched_release"]), *options),
                ],
                patch_env,
            )
            source = paths["patched_release"]

        # 2. adapt (in this process: standard library only)
        started = time.perf_counter()
        print(f"[adapt] {source} -> {paths['importer_zip']}", flush=True)
        receipt = adapter.adapt_folder(source, paths["importer_zip"])
        paths["receipt"].write_text(json.dumps(receipt.as_dict(), indent=2) + "\n")
        record["steps"]["adapt"] = {
            "commands": [["release_build.adapter.adapt_folder"]],
            "seconds": round(time.perf_counter() - started, 1),
            "peak_memory_mb": None,  # runs inside this process
            "returncode": 0,
        }
        record["release"]["provider_tree_sha256"] = (
            adapter.tree_sha256(paths["release"]) if paths["patched"] else receipt.input_tree_sha256
        )
        record["release"]["built_tree_sha256"] = receipt.input_tree_sha256
        record["release"]["importer_zip_sha256"] = receipt.output_zip_sha256
        record["release"]["exchange_numbers_restored"] = dict(receipt.numbers_restored)
        record["release"]["patches"] = dict(sorted(receipt.patches.items()))
        record["release"]["import_fixes"] = dict(sorted(receipt.import_fixes.items()))

        # 3. import
        for name in IMPORTER_SOURCES:
            step(
                "import",
                importers.command(
                    *("sentier-importers", "run", name),
                    *("--data-root", str(paths["importer_root"])),
                    *("--output-dir", str(paths["importer_output"])),
                    *("--cache-dir", str(paths["importer_cache"])),
                ),
                importers.env(),
            )
        folders = sorted((paths["importer_output"] / "sentier_inventory").glob("*/"))
        if len(folders) != 1:
            raise BuildError(f"Expected one inventory folder from the importer, found {folders}")
        metadata = ["python", str(HELPERS / "inventory_metadata.py"), str(folders[0])]
        if paths["patched"]:
            modifications = out / "modifications.json"
            modifications.write_text(json.dumps(_modifications(receipt, record), indent=2) + "\n")
            metadata += ["--modifications", str(modifications)]
        step("import", importers.command(*metadata), importers.env())

        # 4. data
        step(
            "data",
            brightway.command(
                *("python", str(HELPERS / "data_root.py"), str(paths["pinned_data"])),
                *("--record", str(out / "data-pins.json")),
            ),
            brightway.env(),
        )
        inventory = paths["data_root"] / "sentier-inventory" / "data" / folders[0].name
        inventory.mkdir(parents=True)
        for file in sorted(folders[0].iterdir()):
            shutil.copy2(file, inventory / file.name)
        for name in PINNED_DATA:
            (paths["data_root"] / name).symlink_to(paths["pinned_data"] / name)
        record["data_pins"] = [
            {key: pin[key] for key in ("name", "repository", "commit")}
            for pin in json.loads((out / "data-pins.json").read_text())
        ]

        # 5. install
        bw_env = {**brightway.env(), "BRIGHTWAY2_DIR": str(paths["brightway_dir"])}
        paths["brightway_dir"].mkdir(parents=True, exist_ok=True)
        step(
            "install",
            brightway.command(
                *("sentier-brightway", "db", "--project", paths["project"]),
                *("--data-root", str(paths["data_root"])),
            ),
            bw_env,
        )
        record["coverage"] = _coverage_lines(paths["logs"] / "install.log")

        # 6. audit (exit code 1: the audit wrote its file and found errors)
        audit_command = brightway.command(
            *("python", str(HELPERS / "audit_brightway.py"), "--project", paths["project"]),
            *("--out", str(paths["audit"]), "--label", paths["label"]),
        )
        step("audit", audit_command, bw_env, accept=(0, 1))
        if not (paths["audit"] / "audit.json").is_file():
            raise BuildError(f"The audit wrote no audit.json; see {paths['logs'] / 'audit.log'}")
        audit = json.loads((paths["audit"] / "audit.json").read_text())
        record["audit"] = {
            "status": audit["status"],
            "file": str(paths["audit"] / "audit.json"),
            "sha256": adapter.sha256_file(paths["audit"] / "audit.json"),
            "errors": audit["errors"],
            "findings": audit["findings"],
        }
        record["status"] = "completed" if audit["status"] == "passed" else "audit failed"
    except (BuildError, adapter.AdapterError) as error:
        record["status"], record["error"] = "failed", str(error)
        raise
    finally:
        record["finished"] = datetime.now(UTC).isoformat(timespec="seconds")
        paths["record"].write_text(json.dumps(record, indent=2) + "\n")

    print(f"Built {paths['project']} in {paths['brightway_dir']}")
    for name, result in record["steps"].items():
        memory = result["peak_memory_mb"]
        print(
            f"  {name:8} {result['seconds']:7.1f} s  {memory if memory is not None else '-':>8} MB"
        )
    print(f"Audit {record['audit']['status']}: {record['audit']['file']}")
    for error in record["audit"]["errors"]:
        print(f"  error: {error}")
    for finding in record["audit"]["findings"]:
        print(f"  finding: {finding}")
    failed = record["audit"]["status"] != "passed"
    return int(failed or (args.fail_on_findings and bool(record["audit"]["findings"])))


def _modifications(receipt: adapter.Receipt, record: dict) -> dict:
    """What the inventory folder's metadata says about the changes to BAFU's release."""
    return {
        "tool": "bafu-community-fixes",
        "tool_commit": record["tools"]["this repository"],
        "provider_release_tree_sha256": record["release"]["provider_tree_sha256"],
        "patched_release_tree_sha256": receipt.input_tree_sha256,
        "datasets_changed_by_import_fix": dict(sorted(receipt.import_fixes.items())),
        "datasets_changed_by_patch": dict(sorted(receipt.patches.items())),
        "record_of_changes": "release-report.html, written by the same run",
    }


def _repository_commit() -> str:
    try:
        commit = _git("-C", str(REPOSITORY), "rev-parse", "HEAD")
        changed = _git("-C", str(REPOSITORY), "status", "--porcelain", "--untracked-files=no")
    except BuildError:
        return "not a git checkout"
    return commit + (" (with local changes)" if changed else "")


def _coverage_lines(log: Path) -> list[str]:
    """The linking report sentier-brightway prints after an install."""
    lines = log.read_text(errors="replace").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Installed ")), None)
    return [] if start is None else [line for line in lines[start:] if line.strip()]


def compare(args: argparse.Namespace) -> int:
    pins = load_pins(args.pins)
    tools_dir = (args.tools or args.candidate / "tools").resolve()
    venvs = args.venvs.resolve() if args.venvs else None
    brightway = Tool(
        "sentier-brightway", pins["sentier-brightway"], tools_dir / "sentier-brightway", venvs
    )
    brightway.ensure(args.allow_unpinned)
    command = brightway.command(
        *("python", str(HELPERS / "compare_builds.py")),
        *(str(args.baseline.resolve()), str(args.candidate.resolve())),
        *("--out", str(args.out.resolve())),
    )
    done = subprocess.run(command, env={**os.environ, **brightway.env()})
    return done.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--pins", type=Path, default=PINS, help="Tool pins (default: pins.toml)")
        p.add_argument(
            "--tools",
            type=Path,
            help="Folder with checkouts of sentier-importers and sentier-brightway; missing "
            "ones are cloned there at the pinned commit (default: OUT/tools)",
        )
        p.add_argument(
            "--venvs", type=Path, help="Keep the tools' environments here, not in the checkouts"
        )
        p.add_argument(
            "--allow-unpinned",
            action="store_true",
            help="Accept a tool checkout at another commit or with local changes (recorded)",
        )

    b = sub.add_parser("build", help="Build and audit a Brightway database")
    b.add_argument(
        "release",
        type=Path,
        help="Folder with BAFU's EcoSpold 1 files, or 'latest' to let the patch tool "
        "download BAFU's latest release into its cache",
    )
    b.add_argument("out", type=Path, help="Empty folder for everything the build writes")
    b.add_argument("--no-patches", action="store_true", help="Build the provider release as is")
    b.add_argument("--only", nargs="+", metavar="ID", help="Apply only these patches")
    b.add_argument("--skip", nargs="+", metavar="ID", help="Don't apply these patches")
    b.add_argument(
        "--xsd-check",
        choices=("off", "end", "every-step"),
        default="every-step",
        help="How often the patch tool checks against the EcoSpold 1 schema (default: every step)",
    )
    b.add_argument("--label", help="What this build is, for the audit and the record")
    b.add_argument("--project", help="Brightway project name")
    b.add_argument("--brightway-dir", type=Path, help="BRIGHTWAY2_DIR (default: OUT/brightway)")
    b.add_argument(
        "--pinned-data",
        type=Path,
        help="Where the pinned flow terms, methods and mapping are kept, so that several "
        "builds share one copy (default: OUT/pinned-data)",
    )
    b.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Fail if the audit has findings (a sample score outside its plausible range, "
        "elementary flows that lost their EF 3.1 flow)",
    )
    common(b)
    b.set_defaults(run=build)

    c = sub.add_parser("compare", help="Compare a patched build with the provider release's")
    c.add_argument("baseline", type=Path, help="Build folder of the provider release")
    c.add_argument("candidate", type=Path, help="Build folder of the patched release")
    c.add_argument("--out", type=Path, required=True, help="JSON file to write")
    common(c)
    c.set_defaults(run=compare)

    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (BuildError, adapter.AdapterError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
