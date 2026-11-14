"""Download MEDDOCAN v1.0 from Zenodo and verify its md5 (ADR-0003, task T2.1).

MEDDOCAN is CC BY 4.0 (DOI 10.5281/zenodo.4279323). It is never versioned in this repository:
it lands in ``data/``, which is git-ignored.

Usage::

    uv run python -m data_prep.download_meddocan --dest data
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

ZENODO_RECORD = "4279323"
URL = f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/meddocan.zip/content"
MD5 = "6a09eb975580fdf56bc7041eadc9c921"
ZIP_NAME = "meddocan.zip"
TIMEOUT_SECONDS = 60

Fetch = Callable[[str, Path], None]


class ChecksumError(RuntimeError):
    """The downloaded file does not match the pinned md5."""


def md5_of(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)  # integrity check against Zenodo, not security
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_md5(path: Path, expected: str) -> None:
    """Raise ``ChecksumError`` and delete ``path`` if its md5 differs (fail-safe)."""
    actual = md5_of(path)
    if actual != expected:
        path.unlink()
        raise ChecksumError(f"{path.name}: md5 {actual} != expected {expected}")


def _http_fetch(url: str, path: Path) -> None:
    if not url.startswith("https://"):
        raise ValueError("only https downloads are allowed")
    with (
        urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response,  # noqa: S310 - https only
        path.open("wb") as out,
    ):
        shutil.copyfileobj(response, out)


def download(dest_dir: Path, *, url: str = URL, md5: str = MD5, fetch: Fetch | None = None) -> Path:
    """Download the corpus zip into ``dest_dir`` and verify it. Skips if already verified."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / ZIP_NAME
    if target.exists() and md5_of(target) == md5:
        return target

    # Download to a ".part" file and rename only after verification: an interrupted or
    # tampered download never leaves a zip that looks valid.
    partial = target.with_suffix(".part")
    try:
        (fetch or _http_fetch)(url, partial)
        verify_md5(partial, md5)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def safe_extract(zip_path: Path, dest: Path) -> None:
    """Extract ``zip_path`` into ``dest``, rejecting members that escape it (zip-slip)."""
    root = dest.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            if not (root / member).resolve().is_relative_to(root):
                raise ValueError(f"unsafe path in archive: {member}")
        archive.extractall(root)  # noqa: S202 - every member checked above


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=Path("data"))
    args = parser.parse_args(argv)

    zip_path = download(args.dest)
    print(f"Verified {zip_path} (md5 {MD5})")
    safe_extract(zip_path, args.dest)
    print(f"Extracted to {args.dest / 'meddocan'}")


if __name__ == "__main__":
    main()
