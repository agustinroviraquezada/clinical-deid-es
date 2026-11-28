"""Final README and licence files (T5.1, AC-07): required sections, no placeholders left."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

REQUIRED_SECTIONS = (
    "Description",
    "Tech stack",
    "Installation and running",
    "Project structure",
    "Main features",
    "Results",
    "Limitations",
    "Test access",
    "Links",
    "Data and attribution",
    "Licence",
)


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_readme_has_every_required_section(section):
    assert re.search(rf"^## {re.escape(section)}\b", README, flags=re.MULTILINE)


def test_readme_has_no_placeholders_left():
    assert "coming soon" not in README.lower()
    assert "work in progress" not in README.lower()
    assert "TODO(author)" not in README


def test_readme_gives_the_demo_username_and_public_links():
    assert "`demo`" in README
    assert "lambda-url.eu-west-1.on.aws" in README
    assert "huggingface.co/ahrovira/clinical-deid-es-meddocan" in README


def test_readme_credits_meddocan_under_cc_by():
    assert "MEDDOCAN" in README
    assert "CC BY 4.0" in README
    assert "10.5281/zenodo.4279323" in README


def test_relative_links_in_readme_point_to_existing_files():
    targets = re.findall(r"\]\(((?!https?://|#)[^)\s]+)\)", README)
    assert targets
    missing = [t for t in targets if not (ROOT / t.split("#")[0]).exists()]
    assert missing == []


SECRET_PATTERNS = {
    "argon2 hash": re.compile(r"\$argon2(id|i|d)\$v=\d+\$m="),
    "Hugging Face token": re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
}
PUBLIC_DOCS = [
    ROOT / "README.md",
    ROOT / "NOTICE",
    *sorted((ROOT / "docs").rglob("*.md")),
    *sorted((ROOT / "specs").rglob("*.md")),
]


@pytest.mark.security
@pytest.mark.parametrize("path", PUBLIC_DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_public_docs_hold_no_secrets(path):
    text = path.read_text(encoding="utf-8")
    found = [name for name, pattern in SECRET_PATTERNS.items() if pattern.search(text)]
    assert found == []


@pytest.mark.security
def test_readme_does_not_publish_the_demo_password():
    (line,) = [ln for ln in README.splitlines() if ln.lstrip("- ").startswith("Password:")]
    assert "shared privately" in line  # ADR-0012


@pytest.mark.security
@pytest.mark.parametrize(
    "leak",
    [
        "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        "hf_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6",
        "AKIA" + "ABCDEFGHIJKLMNOP",
    ],
)
def test_secret_patterns_catch_typical_leaks(leak):
    assert any(pattern.search(leak) for pattern in SECRET_PATTERNS.values())


def test_code_licence_is_apache_2_with_notice():
    assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "MEDDOCAN" in notice
    assert "CC BY 4.0" in notice
