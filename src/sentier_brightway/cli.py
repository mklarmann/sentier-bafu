"""``sentier-brightway db|files|coverage|backtest``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from dataclasses import asdict
from pathlib import Path

from . import coverage, import_db, import_files, render
from .constants import DEFAULT_SOURCE, citation
from .fetch import FetchError

# files.ExistingOutputError is a RuntimeError and FileNotFoundError/NotADirectoryError are
# OSErrors, so the except tuple in main() covers them


def _add_source(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="inventory source id to install (data/<source>-<version>/ in sentier-inventory); "
        f"names the inventory database (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--source-version",
        default=None,
        help="release of --source to read when the data root serves several (default: the "
        "only one present)",
    )


def _add_flow_links(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--flow-links",
        default=None,
        metavar="FILE",
        help="link the elementary flows through Brightway Flows, with this targets file of "
        "patch 0010's crosswalk, in place of the mapping folder of sentier-mappings",
    )


def _add_flow_terms_of(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--flow-terms-of",
        default=None,
        metavar="SOURCE",
        help="the source whose elementary flow terms the inventory uses, when that is not "
        "--source itself (a patched copy of a release has its own name and the release's flows)",
    )


def _add_report(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--report",
        default=None,
        metavar="FILE",
        help="also write the linking report as JSON: the lines printed, and the counts",
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sentier-brightway")
    sub = p.add_subparsers(dest="command", required=True)

    db = sub.add_parser(
        "db", help="write one inventory source (default BAFU-2026) + EF 3.1 into a bw2data project"
    )
    db.add_argument("--project", required=True, help="bw2data project name")
    _add_source(db)
    _add_flow_links(db)
    _add_flow_terms_of(db)
    _add_report(db)
    db.add_argument("--overwrite", action="store_true", help="replace existing databases")
    db.add_argument("--data-root", default=None, help="local ~/dds-shaped folder (skips download)")
    db.add_argument(
        "--skip-nomenclature",
        action="store_true",
        help="do not relink BAFU flows whose EF counterpart has no factor",
    )

    fil = sub.add_parser(
        "files", help="write registry parquet + mappings + datapackages to a folder (no bw2data)"
    )
    fil.add_argument("--out", required=True, help="output folder")
    _add_source(fil)
    _add_flow_links(fil)
    _add_flow_terms_of(fil)
    _add_report(fil)
    fil.add_argument("--overwrite", action="store_true", help="replace a non-empty output folder")
    fil.add_argument(
        "--no-datapackages",
        action="store_true",
        help="skip the bw_processing output (bw_package/)",
    )
    fil.add_argument("--data-root", default=None, help="local ~/dds-shaped folder (skips download)")
    fil.add_argument(
        "--skip-nomenclature",
        action="store_true",
        help="do not relink BAFU flows whose EF counterpart has no factor",
    )

    cov = sub.add_parser("coverage", help="print linking coverage, no Brightway needed")
    _add_source(cov)
    _add_flow_links(cov)
    _add_flow_terms_of(cov)
    _add_report(cov)
    cov.add_argument("--data-root", default=None)
    cov.add_argument("--skip-nomenclature", action="store_true")

    bt = sub.add_parser(
        "backtest", help="score all processes and compare with BAFU's published EF 3.1 results"
    )
    bt.add_argument(
        "--out", required=True, help="dashboard data folder (CSV, meta, parquet, run_report)"
    )
    bt.add_argument(
        "--xlsx",
        default=None,
        help="BAFU 'LCIA Results' .xlsx or .zip (default: ~/dds/sources/bafu-2026/...)",
    )
    bt.add_argument(
        "--files",
        default=None,
        help="existing file-mode export; omitted = export into <out>/files first",
    )
    bt.add_argument("--data-root", default=None, help="local ~/dds-shaped folder (skips download)")
    _add_source(bt)
    _add_flow_links(bt)
    _add_flow_terms_of(bt)
    bt.add_argument("--skip-nomenclature", action="store_true")
    bt.add_argument("--fixture-categories", action="store_true", help=argparse.SUPPRESS)
    return p


def _run_backtest(args: argparse.Namespace, include: bool) -> str:
    """Export first when no ``--files`` is given, then score, compare and write."""
    from . import backtest as bt  # bw2calc is imported inside run_backtest

    files_dir = Path(args.files) if args.files else Path(args.out) / "files"
    if args.files and (args.flow_links or args.flow_terms_of):
        raise ValueError(
            "--files names an export that is already made; --flow-links and --flow-terms-of "
            "are options of making one and would not be used"
        )
    if not args.files:
        # <out>/files is ours: overwrite only ever replaces a previous export there
        import_files(
            files_dir,
            data_root=args.data_root,
            include_nomenclature=include,
            overwrite=True,
            source=args.source,
            source_version=args.source_version,
            flow_links=args.flow_links,
            flow_terms_of=args.flow_terms_of,
        )
    cats = bt.FIXTURE_CATEGORIES if args.fixture_categories else bt.CATEGORIES
    xlsx = Path(args.xlsx) if args.xlsx else bt.DEFAULT_XLSX.expanduser()
    result = bt.run_backtest(files_dir, xlsx, args.out, categories=cats)
    return f"{bt.render_summary(result)}\n{citation(args.source)}"


def _run(args: argparse.Namespace) -> str:
    """Run one subcommand and return the text to print on success."""
    include = not args.skip_nomenclature
    if args.command == "backtest":
        return _run_backtest(args, include)
    if args.command == "coverage":
        cov = coverage(
            data_root=args.data_root,
            include_nomenclature=include,
            source=args.source,
            source_version=args.source_version,
            flow_links=args.flow_links,
            flow_terms_of=args.flow_terms_of,
        )
    elif args.command == "files":
        cov = import_files(
            args.out,
            data_root=args.data_root,
            include_nomenclature=include,
            datapackages=not args.no_datapackages,
            overwrite=args.overwrite,
            source=args.source,
            source_version=args.source_version,
            flow_links=args.flow_links,
            flow_terms_of=args.flow_terms_of,
        )
    else:
        cov = import_db(
            args.project,
            overwrite=args.overwrite,
            data_root=args.data_root,
            include_nomenclature=include,
            source=args.source,
            source_version=args.source_version,
            flow_links=args.flow_links,
            flow_terms_of=args.flow_terms_of,
        )
    text = render(cov)
    if args.report:
        report = {
            "linking": cov.linking,
            "lines": [line for line in text.splitlines() if line.strip()],
            "coverage": asdict(cov),
        }
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
    if args.command == "files":
        text += f"\nFiles written to {Path(args.out).resolve()}"
    return text


def _progress_handler() -> logging.Handler:
    """Progress lines (project creation, one per method) on stderr while a command runs."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv if argv is not None else sys.argv[1:])
    logger = logging.getLogger("sentier_brightway")
    handler = _progress_handler()
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(min(logger.level or logging.INFO, logging.INFO))
    try:
        # the rendered report already carries the unit-conflict line; the API keeps warning,
        # and any other warning (bw2data's included) still reaches the user
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=r".*conflicting units", category=UserWarning)
            text = _run(args)
    except (FetchError, OSError, ValueError, ImportError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    print(text)
    return 0
