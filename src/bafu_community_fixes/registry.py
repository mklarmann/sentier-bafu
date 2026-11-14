"""Registration and discovery of community patches.

A patch is a function that takes a `Database` and changes its models in place.
Register it with `@patch` in any module under `bafu_community_fixes.patches`.
Patches run in order of their id, so use sortable ids like `"0001-short-name"`.
The pipeline records which datasets each patch changed, and how; patches
don't do that themselves.

Every patch names who wrote it, and who authorised it to be applied to the
patched copy. Unauthorised patches still run, but the run report flags
them. Every patch also names the findings it answers, so that a finding and its
patch are linked in one place, here.
"""

import importlib
import pkgutil
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable

from bafu_community_fixes.changes import Evidence, Provenance, Rule
from bafu_community_fixes.xml import Database

type PatchFunc = Callable[[Database], None]


@dataclass(frozen=True)
class Patch:
    id: str
    description: str
    func: PatchFunc
    provenance: Provenance
    rationale: str = ""
    rules: tuple[Rule, ...] = ()
    evidence: tuple[Evidence, ...] = ()

    def __call__(self, db: Database) -> None:
        self.func(db)


_REGISTRY: dict[str, Patch] = {}
_ID = re.compile(r"\d{4}-[a-z0-9]+(-[a-z0-9]+)*")
_FINDING = re.compile(r"F[1-9]\d*")


def patch(
    id: str,
    *,
    findings: tuple[str, ...],
    authored_by: str,
    authorised_by: str | None = None,
    references: tuple[str, ...] = (),
    reported_by: str | None = None,
    confirmed_by: str | None = None,
    rules: tuple[Rule, ...] = (),
    evidence: tuple[Evidence, ...] = (),
) -> Callable[[PatchFunc], PatchFunc]:
    """Register a patch. Its docstring's first line is the description, the rest the rationale.

    `findings` are the ids of the findings in the ledger that the patch answers, like
    `("F14",)`. They are required: a patch that answers no finding says so with `()`.
    `authored_by` wrote the patch, and `authorised_by` approved it for this community
    release. `reported_by` found the problem, and `confirmed_by` confirmed it for the
    data owner. `references` are links to the issue, discussion or evidence.
    `rules` explain in plain language which rule (schema or convention) requires it.
    `evidence` lists the specific changes, with links, for the run report.
    """

    def decorator(func: PatchFunc) -> PatchFunc:
        if id in _REGISTRY:
            raise ValueError(f"Duplicate patch id: {id}")
        if not _ID.fullmatch(id):
            raise ValueError(f"Patch id {id!r} must look like '0012-short-name'")
        if taken := [key for key in _REGISTRY if key[:4] == id[:4]]:
            raise ValueError(f"Patch {id} has the same number as {taken[0]}")
        if isinstance(findings, str) or not all(_FINDING.fullmatch(f) for f in findings):
            raise ValueError(f"Patch {id}: findings must be ids like ('F14',), not {findings!r}")
        lines = (func.__doc__ or "").strip().splitlines()
        if not lines:
            raise ValueError(f"Patch {id} needs a docstring describing what it does")
        rationale = "\n".join(line.strip() for line in lines[1:]).strip()
        provenance = Provenance(
            authored_by,
            authorised_by,
            tuple(references),
            reported_by,
            confirmed_by,
            tuple(findings),
        )
        _REGISTRY[id] = Patch(
            id, lines[0], func, provenance, rationale, tuple(rules), tuple(evidence)
        )
        return func

    return decorator


def available_patches() -> list[Patch]:
    """All registered patches, in application order."""
    from bafu_community_fixes import patches

    for module in pkgutil.iter_modules(patches.__path__):
        importlib.import_module(f"{patches.__name__}.{module.name}")
    return [_REGISTRY[key] for key in sorted(_REGISTRY)]


def data_file(name: str) -> Traversable:
    """A supporting data file shipped in `bafu_community_fixes/data`."""
    return files("bafu_community_fixes.data") / name
