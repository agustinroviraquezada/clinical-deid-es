"""Slides (T5.2, AC-07): required topics, attribution, rendered PDF and README link."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SLIDES_DIR = ROOT / "docs" / "slides"
SLIDES_MD = SLIDES_DIR / "slides.md"
SLIDES_PDF = SLIDES_DIR / "slides.pdf"
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _slides() -> str:
    return SLIDES_MD.read_text(encoding="utf-8")


def _slide_titles() -> list[str]:
    return [m.lower() for m in re.findall(r"^# (.+)$", _slides(), flags=re.MULTILINE)]


# "Done when" of T5.2: problem, architecture, comparison, privacy, security, limitations and
# future work. Plus the AI-assisted workflow, which is the subject of the master's degree.
REQUIRED_TOPICS = (
    "problem",
    "architecture",
    "results",
    "privacy",
    "security",
    "limitations",
    "future work",
    "ai-assisted",
)


@pytest.mark.parametrize("topic", REQUIRED_TOPICS)
def test_slides_have_a_slide_for_every_required_topic(topic):
    assert any(topic in title for title in _slide_titles())


def test_slides_are_a_marp_deck_of_reasonable_length():
    text = _slides()
    assert text.startswith("---\nmarp: true")
    slides = len(re.findall(r"^---$", text, flags=re.MULTILINE)) - 1
    assert 12 <= slides <= 22


def test_slides_credit_meddocan_under_cc_by():
    text = _slides()  # FR-13
    assert "MEDDOCAN" in text
    assert "CC BY 4.0" in text
    assert "10.5281/zenodo.4279323" in text


def test_slides_state_that_the_llm_figures_are_pending():
    # Bedrock is blocked for the account: the deck must not suggest cascade figures exist.
    assert "pending" in _slides().lower()


def test_images_used_by_the_slides_exist():
    images = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", _slides())
    assert images
    missing = [img for img in images if not (SLIDES_DIR / img).exists()]
    assert missing == []


def test_rendered_pdf_is_committed():
    assert SLIDES_PDF.read_bytes()[:5] == b"%PDF-"


def test_readme_links_the_slides():
    (line,) = [ln for ln in README.splitlines() if ln.lstrip("- ").startswith("Slides:")]
    assert "added in T5.2" not in line
    assert "docs/slides/slides.pdf" in line
