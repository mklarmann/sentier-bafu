import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from bafu_community_fixes import download

REPO = Path(__file__).parents[1]


@pytest.fixture
def release(tmp_path, monkeypatch):
    """A local zip 'release' and an empty cache."""
    archive = tmp_path / "release-v1.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("release-v1/a.xml", "<ecoSpold/>")
        zf.writestr("release-v1/b.xml", "<ecoSpold/>")
    url = archive.as_uri()
    monkeypatch.setattr(download, "cache_dir", lambda: tmp_path / "cache")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setitem(download.CHECKSUMS, url, checksum)
    return url


def test_download_extract_and_cache(release, tmp_path):
    stages = []
    folder = download.latest_release(lambda p: stages.append(p.stage), url=release)
    assert folder == tmp_path / "cache" / "release-v1" / "release-v1"
    assert sorted(p.name for p in folder.iterdir()) == ["a.xml", "b.xml"]
    assert "Downloading the latest BAFU release" in stages
    assert download.is_cached(release)

    stages.clear()
    assert download.latest_release(lambda p: stages.append(p.stage), url=release) == folder
    assert stages == []  # served from the cache


def test_checksum_mismatch(release, monkeypatch):
    monkeypatch.setitem(download.CHECKSUMS, release, "0" * 64)
    with pytest.raises(OSError, match="SHA-256 mismatch"):
        download.latest_release(url=release)
    assert not download.is_cached(release)


def test_the_sites_list_of_releases_names_the_archive_the_tool_downloads():
    """`site/config.json` gives a release its id. The manifest of a patched release finds
    that id by the archive's checksum, so exactly one release there names this archive."""
    releases = json.loads((REPO / "site" / "config.json").read_text())["releases"]
    known = download.CHECKSUMS[download.LATEST_RELEASE]
    assert len([r["id"] for r in releases if r.get("archive_sha256") == known]) == 1
