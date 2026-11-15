"""The Brightway installer: write a Sentier inventory (BAFU:2026 by default), the EF 3.1
flows and the EF 3.1 methods into a Brightway project, or as files.

It is one of the two packages of sentier-bafu's distribution and needs that distribution's
``brightway`` extra (pandas, bw2calc, bw2data and others), which the patch tool does not.
"""

from __future__ import annotations

from dataclasses import replace
from importlib.util import find_spec
from pathlib import Path

if find_spec("pandas") is None:  # the patch tool alone is installed
    raise ModuleNotFoundError(
        "sentier_brightway needs the `brightway` extra of bafu-community-fixes, which is not "
        "installed here. In a checkout of sentier-bafu: `uv sync --extra brightway`, or run "
        "the command with `uv run --extra brightway`."
    )

from . import backtest, brightway_flows  # noqa: E402
from ._frames import recording_reads
from ._version import __version__
from .bridge import load_bridge
from .build import BuildResult, build
from .constants import DEFAULT_SOURCE
from .fetch import resolve_data_root
from .flows import load_ef_flows, load_source_flows
from .inventory import load_inventory
from .methods import load_methods
from .report import Coverage, render

__all__ = [
    "__version__",
    "import_db",
    "import_files",
    "import_bafu_db",
    "import_bafu_files",
    "DEFAULT_SOURCE",
    "coverage",
    "assemble",
    "render",
    "Coverage",
    "BuildResult",
    "backtest",
]


def _assemble_from_root(
    root: Path,
    include_nomenclature: bool,
    source: str,
    source_version: str | None = None,
    flow_links: Path | str | None = None,
    flow_terms_of: str | None = None,
) -> BuildResult:
    """Build from an already resolved data root. With ``flow_links`` (the targets file of
    patch 0010's crosswalk) the flows are linked through Brightway Flows, and the mapping
    folder is not read. ``flow_terms_of`` names the source whose elementary flow terms the
    inventory uses, when that is not the inventory's own source: a patched copy of a release
    has its own name and the release's flows."""
    with recording_reads() as files_read:
        inventory = load_inventory(root, source=source, source_version=source_version)
        ef_flows = load_ef_flows(root)
        source_flows = load_source_flows(root, flow_terms_of or source)
        methods = load_methods(root)
        bridge = (
            load_bridge(root, include_nomenclature=include_nomenclature)
            if flow_links is None
            else None
        )
    if flow_links is None:
        result = build(
            inventory=inventory,
            ef_flows=ef_flows,
            bafu_flows=source_flows,
            bridge=bridge,
            methods=methods,
        )
        return replace(result, files_read=tuple(files_read))
    links = brightway_flows.link(
        inventory,
        source_flows,
        ef_flows,
        methods,
        brightway_flows.load_targets(flow_links),
        include_without_factor=include_nomenclature,
    )
    result = build(
        inventory=inventory,
        ef_flows=links.ef_flows,
        bafu_flows=source_flows,
        bridge=links.bridge,
        methods=links.methods,
    )
    coverage = replace(
        result.coverage, linking=brightway_flows.LINKING, link_lines=links.report.lines()
    )
    return replace(result, coverage=coverage, files_read=tuple(files_read))


def assemble(
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    source: str = DEFAULT_SOURCE,
    source_version: str | None = None,
    flow_links: Path | str | None = None,
    flow_terms_of: str | None = None,
) -> BuildResult:
    """Read the Sentier data (local root or verified download) and build the node dicts.

    ``source`` selects the inventory folder (``data/<source>-<version>/`` in sentier-inventory)
    and names the inventory and residual databases after it; ``source_version`` picks one
    release when the data root serves several of the same source. ``flow_links`` links the
    elementary flows through Brightway Flows (see ``brightway_flows``)."""
    return _assemble_from_root(
        resolve_data_root(data_root),
        include_nomenclature,
        source,
        source_version,
        flow_links,
        flow_terms_of,
    )


def coverage(
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    source: str = DEFAULT_SOURCE,
    source_version: str | None = None,
    flow_links: Path | str | None = None,
    flow_terms_of: str | None = None,
) -> Coverage:
    """Linking coverage without touching Brightway."""
    return assemble(
        data_root, include_nomenclature, source, source_version, flow_links, flow_terms_of
    ).coverage


def import_db(
    project: str,
    overwrite: bool = False,
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    source: str = DEFAULT_SOURCE,
    source_version: str | None = None,
    flow_links: Path | str | None = None,
    flow_terms_of: str | None = None,
) -> Coverage:
    """Install one inventory ``source`` (default BAFU-2026) + EF 3.1 biosphere + EF 3.1
    methods into ``project``. The inventory database is named after ``source`` (never after
    ``source_version``, which only picks a release when several are served).

    Run inside the Python environment where Brightway / Activity Browser is installed.
    ``include_nomenclature=False`` keeps source flows whose EF counterpart has no factor in
    the residual database instead of relinking them.

    With ``overwrite`` the previous install is removed before the new one is written; if
    the write fails part-way, re-running with ``overwrite=True`` (CLI: ``--overwrite``) is
    the recovery step.
    """
    from .writer import write  # bw2data import stays lazy

    result = assemble(
        data_root, include_nomenclature, source, source_version, flow_links, flow_terms_of
    )
    write(result, project=project, overwrite=overwrite)
    return result.coverage


def import_bafu_db(
    project: str,
    overwrite: bool = False,
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    source: str = DEFAULT_SOURCE,
    source_version: str | None = None,
) -> Coverage:
    """Thin wrapper over ``import_db`` kept under its original name."""
    return import_db(project, overwrite, data_root, include_nomenclature, source, source_version)


def import_files(
    out_dir: Path | str,
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    datapackages: bool = True,
    overwrite: bool = False,
    source: str = DEFAULT_SOURCE,
    source_version: str | None = None,
    flow_links: Path | str | None = None,
    flow_terms_of: str | None = None,
) -> Coverage:
    """Write one inventory ``source`` (default BAFU-2026) + EF 3.1 as plain files instead of a
    bw2data project.

    ``out_dir`` receives ``registry/`` (parquet tables joined by integer ``bw_id``),
    ``mappings/`` (every JSON of the bridge folder, copied verbatim; ``manifest.bridge_packages``
    lists the packages that were applied and ``include_nomenclature`` says whether the order-4
    package was), ``bw_package/``
    (bw_processing datapackages for ``bw2calc.LCA`` with no bw2data project; skipped with
    ``datapackages=False``) and ``manifest.json``. Read them back with
    ``sentier_brightway.registry.load_registry`` and
    ``sentier_brightway.datapackage.load_inventory_datapackage`` /
    ``load_method_datapackage`` / ``score``.

    A non-empty ``out_dir`` is refused unless ``overwrite=True``, and even then only a
    previous export (a folder with a ``manifest.json``) is replaced; anything else is left
    alone.
    """
    from .files import write_files

    root = resolve_data_root(data_root)
    result = _assemble_from_root(
        root, include_nomenclature, source, source_version, flow_links, flow_terms_of
    )
    write_files(
        result,
        data_root=root,
        out_dir=Path(out_dir),
        datapackages=datapackages,
        overwrite=overwrite,
        include_nomenclature=include_nomenclature,
        flow_links=None if flow_links is None else Path(flow_links),
    )
    return result.coverage


def import_bafu_files(
    out_dir: Path | str,
    data_root: Path | str | None = None,
    include_nomenclature: bool = True,
    datapackages: bool = True,
    overwrite: bool = False,
    source: str = DEFAULT_SOURCE,
    source_version: str | None = None,
) -> Coverage:
    """Thin wrapper over ``import_files`` kept under its original name."""
    return import_files(
        out_dir, data_root, include_nomenclature, datapackages, overwrite, source, source_version
    )
