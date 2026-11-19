"""Shared helpers for validating and locating flat Sentier data frames."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import pandas as pd

from .constants import FLOW_IRI_PREFIX

_FILES_READ: ContextVar[list[Path] | None] = ContextVar(
    "sentier_brightway_files_read", default=None
)


def note_read(path: Path) -> Path:
    """Remember that the data file ``path`` is read, while ``recording_reads`` is open; every
    reader of a data root calls this, so that an export can say which files it was made from.
    Returns ``path``."""
    seen = _FILES_READ.get()
    if seen is not None and path not in seen:
        seen.append(Path(path))
    return path


@contextmanager
def recording_reads() -> Iterator[list[Path]]:
    """Collect the data files read inside the block, in the order they were first read."""
    seen: list[Path] = []
    token = _FILES_READ.set(seen)
    try:
        yield seen
    finally:
        _FILES_READ.reset(token)


def require_columns(df: pd.DataFrame, required: frozenset[str], path: Path) -> None:
    """Raise ``ValueError`` naming any of ``required`` missing from ``df.columns``."""
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"{path} is missing required columns {missing}")


def codes_from_iris(iri: pd.Series, path: Path) -> pd.Series:
    """Strip ``FLOW_IRI_PREFIX`` from a series of flow IRIs, or raise ``ValueError`` naming
    ``path`` and the first offending value if any IRI does not start with it."""
    bad = iri[~iri.str.startswith(FLOW_IRI_PREFIX)]
    if not bad.empty:
        raise ValueError(
            f"{path}: flow iri does not start with {FLOW_IRI_PREFIX!r}: {bad.iloc[0]!r}"
        )
    return iri.str.removeprefix(FLOW_IRI_PREFIX)


def data_root_error(kind: str, expected: Path) -> FileNotFoundError:
    """Build a consistent error for a data root that does not hold the expected ``kind``."""
    return FileNotFoundError(
        f"no {kind} found; expected {expected}; --data-root (or $SENTIER_DATA_ROOT) must "
        "point at the folder that contains the sentier-inventory, sentier-vocab, "
        "sentier-methods and sentier-mappings checkouts"
    )
