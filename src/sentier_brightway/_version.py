"""The version of the distribution that ships this package (``bafu-community-fixes``, the
package of sentier-bafu), with a fallback for an uninstalled source tree."""

from __future__ import annotations

import importlib.metadata

DISTRIBUTION = "bafu-community-fixes"
FALLBACK_VERSION = "0.1.0"


def _version() -> str:
    try:
        return importlib.metadata.version(DISTRIBUTION)
    except importlib.metadata.PackageNotFoundError:
        return FALLBACK_VERSION


__version__ = _version()
