import hashlib
import urllib.error

import pytest

from sentier_brightway import fetch


def _toml(sha: str) -> str:
    return f"""
[[source]]
name = "sentier-inventory"
repo = "sentier-dev/sentier-inventory"
ref = "0123456789abcdef0123456789abcdef01234567"
[source.files]
"data/bafu-2026-v1/processes.parquet" = "{sha}"
"""


def _manifest(vocab_ref: str, digest: str) -> tuple[fetch.Source, ...]:
    """Two sources differing only in the vocab ref, both pointing at files with ``digest``."""
    return (
        fetch.Source(
            name="sentier-inventory",
            repo="sentier-dev/sentier-inventory",
            ref="a" * 40,
            files={"data/f.parquet": digest},
        ),
        fetch.Source(
            name="sentier-vocab",
            repo="sentier-dev/sentier-vocab",
            ref=vocab_ref,
            files={"data/g.parquet": digest},
        ),
    )


def test_explicit_data_root_wins(tmp_path, monkeypatch):
    (tmp_path / "arg").mkdir()
    (tmp_path / "env").mkdir()
    monkeypatch.setenv("SENTIER_DATA_ROOT", str(tmp_path / "env"))
    assert fetch.resolve_data_root(tmp_path / "arg") == tmp_path / "arg"


def test_env_var_is_used_when_no_argument(tmp_path, monkeypatch):
    (tmp_path / "env").mkdir()
    monkeypatch.setenv("SENTIER_DATA_ROOT", str(tmp_path / "env"))
    assert fetch.resolve_data_root(None) == tmp_path / "env"


def test_missing_data_root_argument_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="data_root argument"):
        fetch.resolve_data_root(tmp_path / "missing")


def test_missing_env_var_path_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTIER_DATA_ROOT", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError, match="SENTIER_DATA_ROOT"):
        fetch.resolve_data_root(None)


def test_manifest_download_verifies_sha_and_caches(tmp_path, monkeypatch):
    payload = b"parquet-bytes"
    sha = hashlib.sha256(payload).hexdigest()
    calls = []

    def fake_download(url: str) -> bytes:
        calls.append(url)
        return payload

    monkeypatch.setattr(fetch, "_download", fake_download)
    manifest = fetch.parse_manifest(_toml(sha))
    root = fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    target = root / "sentier-inventory" / "data/bafu-2026-v1/processes.parquet"
    assert target.read_bytes() == payload
    assert calls == [
        "https://raw.githubusercontent.com/sentier-dev/sentier-inventory/"
        "0123456789abcdef0123456789abcdef01234567/data/bafu-2026-v1/processes.parquet"
    ]
    fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    assert len(calls) == 1  # second call served from cache


def test_materialize_leaves_no_tmp_files(tmp_path, monkeypatch):
    payload = b"parquet-bytes"
    sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(fetch, "_download", lambda url: payload)
    manifest = fetch.parse_manifest(_toml(sha))
    root = fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    assert list(root.rglob("*.tmp")) == []


def test_sha_mismatch_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "_download", lambda url: b"tampered")
    manifest = fetch.parse_manifest(_toml("00" * 32))
    with pytest.raises(fetch.IntegrityError) as exc_info:
        fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    message = str(exc_info.value)
    assert "raw.githubusercontent.com" in message
    assert "00" * 32 in message  # expected digest
    assert hashlib.sha256(b"tampered").hexdigest() in message  # actual digest
    assert isinstance(exc_info.value, fetch.FetchError)


def test_download_failure_is_a_fetch_error_naming_the_url(tmp_path, monkeypatch):
    def fail(url: str) -> bytes:
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(fetch, "_download", fail)
    manifest = fetch.parse_manifest(_toml("00" * 32))
    with pytest.raises(fetch.FetchError) as exc_info:
        fetch.materialize(manifest, cache_dir=tmp_path / "cache")
    message = str(exc_info.value)
    assert (
        "https://raw.githubusercontent.com/sentier-dev/sentier-inventory/"
        "0123456789abcdef0123456789abcdef01234567/data/bafu-2026-v1/processes.parquet"
    ) in message


def test_cache_dir_changes_when_any_source_ref_changes(tmp_path, monkeypatch):
    payload = b"x"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.delenv("SENTIER_DATA_ROOT", raising=False)
    monkeypatch.setattr(fetch, "default_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(fetch, "_download", lambda url: payload)

    monkeypatch.setattr(fetch, "load_packaged_manifest", lambda: _manifest("b" * 40, digest))
    root_a = fetch.resolve_data_root(None)

    monkeypatch.setattr(fetch, "load_packaged_manifest", lambda: _manifest("c" * 40, digest))
    root_b = fetch.resolve_data_root(None)

    assert root_a != root_b
    assert root_a.parent == tmp_path
    assert root_b.parent == tmp_path


def test_manifest_key_is_deterministic_and_order_independent_within_a_source():
    digest = hashlib.sha256(b"x").hexdigest()
    manifest = _manifest("b" * 40, digest)
    assert fetch.manifest_key(manifest) == fetch.manifest_key(manifest)
    assert len(fetch.manifest_key(manifest)) == 12


def test_packaged_manifest_parses():
    manifest = fetch.load_packaged_manifest()
    assert {s.name for s in manifest} >= {
        "sentier-inventory",
        "sentier-vocab",
        "sentier-methods",
        "sentier-mappings",
    }
    hexdigits = set("0123456789abcdef")
    for source in manifest:
        assert len(source.ref) == 40 and set(source.ref) <= hexdigits
        for digest in source.files.values():
            assert len(digest) == 64 and set(digest) <= hexdigits


def test_a_source_read_as_pinned_is_named_with_its_commit(tmp_path):
    data = b"pinned bytes"
    manifest = _manifest("b" * 40, hashlib.sha256(data).hexdigest())
    for source in manifest:
        for path in source.files:
            target = tmp_path / source.name / path
            target.parent.mkdir(parents=True)
            target.write_bytes(data)
    read = [
        tmp_path / "sentier-inventory/data/f.parquet",
        tmp_path / "sentier-vocab/data/g.parquet",
    ]
    assert fetch.describe_sources(tmp_path, read, manifest) == [
        {
            "name": "sentier-inventory",
            "repo": "sentier-dev/sentier-inventory",
            "ref": "a" * 40,
            "as_pinned": True,
        },
        {
            "name": "sentier-vocab",
            "repo": "sentier-dev/sentier-vocab",
            "ref": "b" * 40,
            "as_pinned": True,
        },
    ]


def test_a_source_that_was_supplied_is_named_with_its_files_and_no_commit(tmp_path):
    data = b"pinned bytes"
    manifest = _manifest("b" * 40, hashlib.sha256(data).hexdigest())
    pinned = tmp_path / "sentier-vocab/data/g.parquet"
    other = tmp_path / "sentier-inventory/data/patched/f.parquet"  # a file no pin names
    changed = tmp_path / "sentier-inventory/data/f.parquet"  # a pinned path, other bytes
    for target, content in ((pinned, data), (other, data), (changed, b"other bytes")):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    digest = hashlib.sha256(data).hexdigest()
    # a file no pin names: the source is not the pinned one, though the bytes agree
    inventory, vocab = fetch.describe_sources(tmp_path, [other, pinned], manifest)
    assert inventory == {
        "name": "sentier-inventory",
        "as_pinned": False,
        "files": {"data/patched/f.parquet": digest},
    }
    assert vocab["as_pinned"] is True and vocab["ref"] == "b" * 40
    # a pinned path with other bytes
    (inventory,) = fetch.describe_sources(tmp_path, [changed], manifest)
    assert inventory["as_pinned"] is False and "ref" not in inventory
    assert inventory["files"] == {"data/f.parquet": hashlib.sha256(b"other bytes").hexdigest()}
    # nothing read from a source: it is left out, not named as pinned
    assert fetch.describe_sources(tmp_path, [], manifest) == []


def test_the_files_read_are_recorded_only_inside_the_block(tmp_path):
    from sentier_brightway._frames import note_read, recording_reads

    first, second = tmp_path / "a", tmp_path / "b"
    note_read(first)  # outside a block: nothing is kept, nothing fails
    with recording_reads() as seen:
        assert note_read(first) == first
        note_read(second)
        note_read(first)
    note_read(second)
    assert seen == [first, second]
