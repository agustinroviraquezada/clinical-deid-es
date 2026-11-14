"""Tests for the MEDDOCAN downloader (T2.1). No network: the fetch function is faked."""

import hashlib
import zipfile

import pytest

from data_prep.download_meddocan import ChecksumError, download, md5_of, safe_extract, verify_md5


def _md5(payload: bytes) -> str:
    return hashlib.md5(payload).hexdigest()  # noqa: S324 - integrity check, not security


def _fake_fetch(payload: bytes):
    calls = []

    def fetch(url, path):
        calls.append(url)
        path.write_bytes(payload)

    fetch.calls = calls
    return fetch


def test_md5_of_matches_hashlib(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"meddocan")
    assert md5_of(path) == _md5(b"meddocan")


def test_verify_md5_accepts_matching_file(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"ok")
    verify_md5(path, _md5(b"ok"))
    assert path.exists()


def test_verify_md5_mismatch_raises_and_deletes_file(tmp_path):
    path = tmp_path / "file.bin"
    path.write_bytes(b"tampered")
    with pytest.raises(ChecksumError):
        verify_md5(path, "0" * 32)
    assert not path.exists()


def test_download_fetches_and_verifies(tmp_path):
    fetch = _fake_fetch(b"zip-bytes")
    path = download(tmp_path, url="https://example.test/m.zip", md5=_md5(b"zip-bytes"), fetch=fetch)
    assert path.read_bytes() == b"zip-bytes"
    assert fetch.calls == ["https://example.test/m.zip"]


def test_download_skips_fetch_when_verified_file_exists(tmp_path):
    md5 = _md5(b"zip-bytes")
    download(tmp_path, md5=md5, fetch=_fake_fetch(b"zip-bytes"))
    second = _fake_fetch(b"zip-bytes")
    download(tmp_path, md5=md5, fetch=second)
    assert second.calls == []


def test_download_with_wrong_checksum_fails_and_leaves_no_file(tmp_path):
    with pytest.raises(ChecksumError):
        download(tmp_path, md5="0" * 32, fetch=_fake_fetch(b"corrupted"))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.security
def test_safe_extract_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../escape.txt", "x")
    with pytest.raises(ValueError):
        safe_extract(zip_path, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_extracts_regular_members(tmp_path):
    zip_path = tmp_path / "ok.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("meddocan/train/brat/a.txt", "texto")
    safe_extract(zip_path, tmp_path / "out")
    assert (tmp_path / "out/meddocan/train/brat/a.txt").read_text(encoding="utf-8") == "texto"
