"""Build a Brightway database from a BAFU release folder, and audit it.

    python3 scripts/build_release.py build RELEASE OUT            # the patched release
    python3 scripts/build_release.py build RELEASE OUT --no-patches   # the provider release
    python3 scripts/build_release.py build latest OUT             # download the release first
    python3 scripts/build_release.py compare BASELINE CANDIDATE --out comparison.json

`build` runs these steps and records each one's time and peak memory in `OUT/build.json`:

1. patch      `bafu-fixes run` writes the patched release (skipped with `--no-patches`)
2. adapt      the release becomes the zip sentier-importers reads (`release_build/adapter.py`);
              elementary exchanges keep the flow BAFU declared
3. import     sentier-importers writes the inventory tables
4. label      a patched release gets its own source name on every dataset
5. data       the pinned flow terms, methods and mapping are fetched and checked
6. install    sentier-brightway writes the Brightway database and the EF 3.1 methods
7. mark       the database's metadata says what it was built from ("Modified Data", patch ids)
8. audit      `release_build/audit_brightway.py` reads the database back and scores it
9. published  with `--published-results FILE`: the comparison with BAFU's published LCIA
              results (the workbook is not in this repository; without it the step is skipped)

The database of the provider release is called `bafu-2026`, BAFU's name. The database of a
patched release is called `bafu-2026-v1-patched`, so that nobody takes it for BAFU's release.

sentier-importers and sentier-brightway are used at the commits in `release_build/pins.toml`,
each in its own `uv` environment. This script needs Python 3.12 or newer, `uv` and `git`.

Everything is written under `OUT`. The built database holds BAFU's inventory, which is under
BAFU's Terms of Use: keep `OUT` local, and never upload it from a CI job. `build.json`, the
audit and the comparison hold counts, dataset codes, names and single scores.
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
STEPS = ("patch", "adapt", "import", "label", "data", "install", "mark", "audit", "published")
# The source name sentier-importers writes on every dataset, which sentier-brightway uses as
# the database name: BAFU's release. A patched release gets another.
PROVIDER_SOURCE = "bafu-2026"
PATCHED_SOURCE = "bafu-2026-v1-patched"
BIOSPHERE_DB = "ef-3.1-biosphere"
RELEASE_NAME = "BAFU:2026 v1"


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
    """The pinned tools (`[tools.*]`). Data pins (`[data.*]`) are read by `data_root.py`."""
    return tomllib.loads(path.read_text())["tools"]


# --- The build -------------------------------------------------------------------------


def plan(args: argparse.Namespace) -> dict:
    """Every path and name of a build, from its options. No file is touched."""
    out = args.out.resolve()
    patched = not args.no_patches
    database = args.database or (PATCHED_SOURCE if patched else PROVIDER_SOURCE)
    if patched and database == PROVIDER_SOURCE:
        raise BuildError(
            f"{PROVIDER_SOURCE} is the name of BAFU's release; a patched database needs another"
        )
    if not patched and database != PROVIDER_SOURCE:
        raise BuildError(f"The provider release keeps BAFU's name, {PROVIDER_SOURCE}")
    return {
        "label": args.label
        or ("patched release (community patches applied)" if patched else "provider release"),
        "patched": patched,
        "release": args.release.resolve(),
        "release_name": args.release_name,
        "out": out,
        "patched_release": out / "release",
        "patch_report": out / "release-report.html",
        "patch_summary": out / "release-summary.json",
        "importer_root": out / "importer-root",
        "importer_zip": out / "importer-root" / IMPORTER_INPUT,
        "importer_output": out / "importer-output",
        "importer_cache": out / "importer-cache",
        "receipt": out / "adapter-receipt.json",
        "pinned_data": (args.pinned_data or out / "pinned-data").resolve(),
        "data_root": out / "data-root",
        "brightway_dir": (args.brightway_dir or out / "brightway").resolve(),
        "project": args.project or ("bafu-2026-v1-patched" if patched else "bafu-2026-v1"),
        "database": database,
        "residual_database": f"{database}-residual",
        "build_steps": out / "build-steps.json",
        "audit": out / "audit",
        "published": out / "published",
        "published_summary": out / "published-results.json",
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


def patch_tool_writes_summary(env: dict[str, str]) -> bool:
    """Whether this checkout's `bafu-fixes run` has `--summary` (the run's record as JSON)."""
    done = subprocess.run(
        ["uv", "run", "--frozen", "--project", str(REPOSITORY), "bafu-fixes", "run", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
    )
    return done.returncode == 0 and "--summary" in done.stdout


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
    database, residual = paths["database"], paths["residual_database"]
    record = {
        "label": paths["label"],
        "patched": paths["patched"],
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "running",
        "release": {"name": paths["release_name"], "folder": str(paths["release"])},
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
        "databases": {"inventory": database, "flows": BIOSPHERE_DB, "no_ef_3_1_flow": residual},
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
        record["release"]["record_of_changes"] = []
        if paths["patched"]:
            patch_env = {"UV_PROJECT_ENVIRONMENT": str(venvs / "bafu-fixes")} if venvs else {}
            options = ["--xsd-check", args.xsd_check, "--report", str(paths["patch_report"])]
            record["release"]["record_of_changes"].append(paths["patch_report"].name)
            if patch_tool_writes_summary(patch_env):
                options += ["--summary", str(paths["patch_summary"])]
                record["release"]["record_of_changes"].append(paths["patch_summary"].name)
            for flag, ids in (("--only", args.only), ("--skip", args.skip)):
                if ids:
                    options += [flag, *ids]
            step(
                "patch",
                [
                    *("uv", "run", "--frozen", "--project", str(REPOSITORY), "bafu-fixes", "run"),
                    *(str(source), str(paths["patched_release"]), *options),
                ],
                patch_env,
            )
            source = paths["patched_release"]

        # 2. adapt (in this process: standard library only). A patched release is read
        # beside the provider release, so that elementary exchanges keep the declared flow.
        started = time.perf_counter()
        print(f"[adapt] {source} -> {paths['importer_zip']}", flush=True)
        receipt = adapter.adapt_folder(
            source, paths["importer_zip"], declared=paths["release"] if paths["patched"] else None
        )
        paths["receipt"].write_text(json.dumps(receipt.as_dict(), indent=2) + "\n")
        record["steps"]["adapt"] = {
            "commands": [["release_build.adapter.adapt_folder"]],
            "seconds": round(time.perf_counter() - started, 1),
            "peak_memory_mb": None,  # runs inside this process
            "returncode": 0,
        }
        release = record["release"]
        release["provider_tree_sha256"] = receipt.declared_tree_sha256 or receipt.input_tree_sha256
        release["built_tree_sha256"] = receipt.input_tree_sha256
        release["importer_zip_sha256"] = receipt.output_zip_sha256
        release["exchange_numbers_restored"] = dict(receipt.numbers_restored)
        release["patches"] = dict(sorted(receipt.patches.items()))
        release["import_fixes"] = dict(sorted(receipt.import_fixes.items()))
        release["exchanges_linked_on_the_declared_flow"] = len(receipt.source_observations)

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
        tables, folder_name = folders[0], folders[0].name

        # 4. label: a patched release gets its own source name; its version names the
        # patched files, so two different sets of patches are never taken for one another
        metadata = ["python", str(HELPERS / "inventory_metadata.py"), str(tables)]
        if paths["patched"]:
            version = f"tree-{receipt.input_tree_sha256[:8]}"
            folder_name = f"{database}-{version}"
            step(
                "label",
                importers.command(
                    *("python", str(HELPERS / "label_release.py"), str(tables)),
                    *("--receipt", str(paths["receipt"])),
                    *("--source", database, "--source-version", version),
                ),
                importers.env(),
            )
            modifications = out / "modifications.json"
            modifications.write_text(json.dumps(_modifications(receipt, record), indent=2) + "\n")
            metadata += ["--modifications", str(modifications)]
        step("import", importers.command(*metadata), importers.env())

        # 5. data
        data_command = [
            *("python", str(HELPERS / "data_root.py"), str(paths["pinned_data"])),
            *("--pins", str(args.pins.resolve()), "--record", str(out / "data-pins.json")),
        ]
        terms = paths["data_root"] / "sentier-vocab" / "terms"
        if paths["patched"]:
            # sentier-brightway looks up the flow terms of the inventory's own source
            data_command += ["--flow-terms", PROVIDER_SOURCE, database]
            data_command += [str(terms / f"{database}.parquet")]
        step("data", brightway.command(*data_command), brightway.env())
        pinned = json.loads((out / "data-pins.json").read_text())
        inventory = paths["data_root"] / "sentier-inventory" / "data" / folder_name
        inventory.mkdir(parents=True)
        for file in sorted(tables.iterdir()):
            shutil.copy2(file, inventory / file.name)
        for name in PINNED_DATA:
            if name == "sentier-vocab" and paths["patched"]:
                for file in sorted((Path(pinned["folder"]) / name / "terms").glob("*.parquet")):
                    (terms / file.name).symlink_to(file)
            else:
                (paths["data_root"] / name).symlink_to(Path(pinned["folder"]) / name)
        record["data_pins"] = [
            {key: value for key, value in pin.items() if key != "files"}
            for pin in pinned["sources"]
        ]

        # 6. install
        bw_env = {**brightway.env(), "BRIGHTWAY2_DIR": str(paths["brightway_dir"])}
        paths["brightway_dir"].mkdir(parents=True, exist_ok=True)
        step(
            "install",
            brightway.command(
                *("sentier-brightway", "db", "--project", paths["project"]),
                *("--source", database, "--data-root", str(paths["data_root"])),
            ),
            bw_env,
        )
        record["coverage"] = _coverage_lines(paths["logs"] / "install.log")

        # 7. mark
        build_steps = _build_steps(record, receipt, inventory)
        paths["build_steps"].write_text(json.dumps(build_steps, indent=2) + "\n")
        marker = out / "release-build.json"
        marker.write_text(json.dumps(_marker(record, build_steps), indent=2) + "\n")
        step(
            "mark",
            brightway.command(
                *("python", str(HELPERS / "mark_database.py"), "--project", paths["project"]),
                *("--database", database, "--database", residual),
                *("--build", str(marker), "--provider-source", PROVIDER_SOURCE),
            ),
            bw_env,
        )

        # 8. audit (exit code 1: the audit wrote its file and found errors)
        audit_command = brightway.command(
            *("python", str(HELPERS / "audit_brightway.py"), "--project", paths["project"]),
            *("--database", database, "--out", str(paths["audit"]), "--label", paths["label"]),
            *(["--sample", str(args.sample.resolve())] if args.sample else []),
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

        # 9. published (optional): against BAFU's published LCIA results
        workbook = args.published_results
        if workbook is None:
            record["published_results"] = {
                "status": "skipped",
                "reason": "no workbook given (--published-results FILE)",
            }
        elif not workbook.is_file():
            record["published_results"] = {
                "status": "skipped",
                "reason": f"{workbook} is not a file; BAFU's workbook is not in this repository",
            }
        else:
            step(
                "published",
                brightway.command(
                    *("sentier-brightway", "backtest", "--out", str(paths["published"])),
                    *("--source", database, "--data-root", str(paths["data_root"])),
                    *("--xlsx", str(workbook.resolve())),
                ),
                brightway.env(),
            )
            step(
                "published",
                brightway.command(
                    *("python", str(HELPERS / "published_results.py"), str(paths["published"])),
                    *("--out", str(paths["published_summary"])),
                ),
                brightway.env(),
            )
            record["published_results"] = {
                "status": "compared",
                "workbook_sha256": adapter.sha256_file(workbook),
                "file": str(paths["published_summary"]),
            } | {
                key: value
                for key, value in json.loads(paths["published_summary"].read_text()).items()
                if key != "categories"
            }
        if record["published_results"]["status"] == "skipped":
            print(f"[published] skipped: {record['published_results']['reason']}", flush=True)

        record["export"] = {
            "brightway_dir": str(paths["brightway_dir"]),
            "project": paths["project"],
            "databases": [database, BIOSPHERE_DB, residual],
            "summary": str(paths["patch_summary"]) if paths["patch_summary"].is_file() else None,
            "extra_steps": str(paths["build_steps"]),
            "release": paths["release_name"],
        }
        record["status"] = "completed" if audit["status"] == "passed" else "audit failed"
    except (BuildError, adapter.AdapterError) as error:
        record["status"], record["error"] = "failed", str(error)
        raise
    finally:
        record["finished"] = datetime.now(UTC).isoformat(timespec="seconds")
        paths["record"].write_text(json.dumps(record, indent=2) + "\n")

    print(f"Built {database} in project {paths['project']}, {paths['brightway_dir']}")
    for name, result in record["steps"].items():
        memory = result["peak_memory_mb"]
        print(
            f"  {name:9} {result['seconds']:7.1f} s  {memory if memory is not None else '-':>8} MB"
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
        "provider_release": record["release"]["name"],
        "provider_release_tree_sha256": record["release"]["provider_tree_sha256"],
        "patched_release_tree_sha256": receipt.input_tree_sha256,
        "datasets_changed_by_import_fix": dict(sorted(receipt.import_fixes.items())),
        "datasets_changed_by_patch": dict(sorted(receipt.patches.items())),
        "exchanges_linked_on_the_declared_flow": len(receipt.source_observations),
        "record_of_changes": record["release"]["record_of_changes"],
    }


def _build_steps(record: dict, receipt: adapter.Receipt, inventory: Path) -> list[dict]:
    """What the build itself changes, in the shape of the patch tool's steps.

    An export of the database lists these after the patch tool's own steps.
    """
    mapping = next(pin for pin in record["data_pins"] if pin["name"] == "sentier-mappings")
    steps = [
        {
            "id": "build-ef-3.1-links",
            "kind": "build step",
            "description": "Elementary exchanges are linked to EF 3.1 flows through "
            f"sentier-mappings at {mapping['commit'][:12]}, with its conversion factors. "
            "Exchanges of flows the mapping does not hold stay on BAFU's flow, in the "
            f"database {record['databases']['no_ef_3_1_flow']}, without a factor.",
            "datasets": receipt.datasets,
        }
    ]
    if receipt.source_observations:
        steps.append(
            {
                "id": "build-declared-flow-identity",
                "kind": "build step",
                "description": f"{len(receipt.source_observations)} elementary exchanges "
                "whose name or compartment a patch corrects are linked on the flow as BAFU "
                "declared it. The corrected name is the exchange's label; the declared and "
                f"the corrected flow of each are listed in {inventory.name}/"
                "source-observations.json.",
                "datasets": len({o["dataset"] for o in receipt.source_observations}),
            }
        )
    return steps


def _marker(record: dict, build_steps: list[dict]) -> dict:
    """What `mark_database.py` writes into the database's metadata."""
    release = record["release"]
    return {
        "patched": record["patched"],
        "release_name": release["name"],
        "provider_tree_sha256": release["provider_tree_sha256"],
        "built_tree_sha256": release["built_tree_sha256"],
        "patches": sorted(release["patches"]),
        "import_fixes": sorted(release["import_fixes"]),
        "record_of_changes": release["record_of_changes"],
        "build_steps": build_steps,
        "tools": {
            name: record["tools"][name]
            for name in ("this repository", "sentier-importers", "sentier-brightway")
        },
        "data": record["data_pins"],
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
    b.add_argument(
        "--database",
        help=f"Name of a patched release's database (default: {PATCHED_SOURCE}); the "
        f"provider release is always {PROVIDER_SOURCE}",
    )
    b.add_argument(
        "--release-name", default=RELEASE_NAME, help=f"The release (default: {RELEASE_NAME})"
    )
    b.add_argument(
        "--sample",
        type=Path,
        help="Datasets the audit scores, with plausible ranges (default: the BAFU:2026 v1 "
        "sample in release_build/score_sample.json)",
    )
    b.add_argument(
        "--published-results",
        type=Path,
        metavar="FILE",
        help="BAFU's published LCIA results workbook (.xlsx or .zip): also compare the "
        "build's scores with it. The workbook is not in this repository; without it, or "
        "if the file is missing, the step is skipped",
    )
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
