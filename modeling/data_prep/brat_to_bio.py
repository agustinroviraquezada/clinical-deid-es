"""MEDDOCAN BRAT -> BIO converter (ADR-0003, task T2.1).

Decisions (T2.1):
- Overlapping spans: the longest wins (ties: the one that starts first); dropped spans are counted.
- Tokens are split at entity boundaries, so labels stay exact even when an entity cuts a word.
- Output: JSONL, one sentence per line: ``{"doc_id", "tokens", "tags"}``.
- Training unit: the sentence (line breaks and ``. ? !`` followed by an uppercase letter),
  never split inside an entity.

Usage::

    uv run python -m modeling.data_prep.brat_to_bio --corpus data/meddocan --out data/meddocan/bio
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SPLITS = ("train", "dev", "test")
TOKEN_RE = re.compile(r"\w+|[^\w\s]")
SENTENCE_END = {".", "?", "!"}


@dataclass(frozen=True, order=True)
class Span:
    """A character span annotated in a BRAT ``.ann`` file (end is exclusive)."""

    start: int
    end: int
    type: str


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int


@dataclass
class BioSentence:
    tokens: list[str]
    tags: list[str]


@dataclass
class SplitStats:
    documents: int = 0
    sentences: int = 0
    entities: Counter[str] = field(default_factory=Counter)
    dropped_overlaps: int = 0


def _parse_ann_lines(content: str) -> list[tuple[Span, str]]:
    """Return each text-bound annotation (``T`` lines) with the text BRAT recorded for it."""
    annotations = []
    for line in content.splitlines():
        if not line.startswith("T"):
            continue  # notes (#), relations (R), events (E)... carry no span
        _, meta, surface = line.split("\t", 2)
        parts = meta.split(" ")
        # Discontinuous spans ("0 5;7 9") are reduced to their outer bounds.
        span = Span(int(parts[1]), int(parts[-1]), parts[0])
        annotations.append((span, surface))
    return annotations


def parse_ann(content: str) -> list[Span]:
    """Parse the text-bound annotations of a BRAT ``.ann`` file."""
    return [span for span, _ in _parse_ann_lines(content)]


def resolve_overlaps(spans: list[Span]) -> tuple[list[Span], int]:
    """Drop overlapping spans: the longest wins, ties go to the earliest start.

    Returns the kept spans sorted by position and the number of dropped spans.
    """
    kept: list[Span] = []
    for span in sorted(spans, key=lambda s: (-(s.end - s.start), s.start)):
        if all(span.end <= other.start or span.start >= other.end for other in kept):
            kept.append(span)
    return sorted(kept), len(spans) - len(kept)


def tokenize(text: str, boundaries: set[int] | None = None) -> list[Token]:
    """Split ``text`` into words and punctuation, keeping character offsets.

    A token is also cut at every offset in ``boundaries`` that falls inside it, so an entity
    that starts or ends mid-word ("DRAlberto") gets its own token.
    """
    cuts = sorted(boundaries or ())
    tokens = []
    for match in TOKEN_RE.finditer(text):
        start, end = match.span()
        inner = [c for c in cuts if start < c < end]
        for piece_start, piece_end in zip([start, *inner], [*inner, end], strict=True):
            tokens.append(Token(text[piece_start:piece_end], piece_start, piece_end))
    return tokens


def _tag_tokens(tokens: list[Token], spans: list[Span]) -> list[str]:
    tags = []
    previous: Span | None = None
    index = 0
    for token in tokens:
        while index < len(spans) and spans[index].end <= token.start:
            index += 1
        span = spans[index] if index < len(spans) else None
        if span is not None and span.start <= token.start < span.end:
            tags.append(("I-" if span == previous else "B-") + span.type)
            previous = span
        else:
            tags.append("O")
            previous = None
    return tags


def _starts_sentence(text: str, before: Token, token: Token, tag: str) -> bool:
    if tag.startswith("I-"):
        return False  # never split inside an entity
    gap = text[before.end : token.start]
    if "\n" in gap:
        return True
    return before.text in SENTENCE_END and gap.isspace() and token.text[0].isupper()


def to_bio_sentences(text: str, spans: list[Span]) -> list[BioSentence]:
    """Convert a document and its spans into BIO-tagged sentences."""
    kept, _ = resolve_overlaps(spans)
    boundaries = {s.start for s in kept} | {s.end for s in kept}
    tokens = tokenize(text, boundaries)
    tags = _tag_tokens(tokens, kept)

    sentences: list[BioSentence] = []
    for i, (token, tag) in enumerate(zip(tokens, tags, strict=True)):
        if i == 0 or _starts_sentence(text, tokens[i - 1], token, tag):
            sentences.append(BioSentence(tokens=[], tags=[]))
        sentences[-1].tokens.append(token.text)
        sentences[-1].tags.append(tag)
    return sentences


def _read(path: Path) -> str:
    # newline="" keeps "\r\n" intact so BRAT character offsets stay valid.
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def convert_split(brat_dir: Path, out_path: Path) -> SplitStats:
    """Convert every ``.txt``/``.ann`` pair in ``brat_dir`` into a JSONL file."""
    stats = SplitStats()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as out:
        for txt_path in sorted(brat_dir.glob("*.txt")):
            doc_id = txt_path.stem
            text = _read(txt_path)
            ann_path = txt_path.with_suffix(".ann")
            annotations = _parse_ann_lines(_read(ann_path)) if ann_path.exists() else []
            for span, surface in annotations:
                if text[span.start : span.end] != surface:
                    raise ValueError(
                        f"{doc_id}: annotation {span.type} [{span.start}, {span.end}) "
                        "does not match the document text"
                    )
            spans = [span for span, _ in annotations]
            kept, dropped = resolve_overlaps(spans)
            sentences = to_bio_sentences(text, kept)
            for sentence in sentences:
                row = {"doc_id": doc_id, "tokens": sentence.tokens, "tags": sentence.tags}
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

            stats.documents += 1
            stats.sentences += len(sentences)
            stats.entities.update(span.type for span in kept)
            stats.dropped_overlaps += dropped
    return stats


def format_stats(stats: dict[str, SplitStats]) -> str:
    """Markdown table of entity counts per type and split."""
    splits = list(stats)
    types = sorted(set().union(*(s.entities for s in stats.values())))

    def row(label: str, values: list[int]) -> str:
        cells = " | ".join(str(v) for v in [*values, sum(values)])
        return f"| {label} | {cells} |"

    lines = [
        f"| Type | {' | '.join(splits)} | Total |",
        "|" + " --- |" * (len(splits) + 2),
        *(row(t, [stats[s].entities[t] for s in splits]) for t in types),
        row("**Entities**", [sum(stats[s].entities.values()) for s in splits]),
        row("Documents", [stats[s].documents for s in splits]),
        row("Sentences", [stats[s].sentences for s in splits]),
        row("Dropped overlaps", [stats[s].dropped_overlaps for s in splits]),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=Path("data/meddocan"))
    parser.add_argument("--out", type=Path, default=Path("data/meddocan/bio"))
    args = parser.parse_args(argv)

    stats = {
        split: convert_split(args.corpus / split / "brat", args.out / f"{split}.jsonl")
        for split in SPLITS
    }
    table = format_stats(stats)
    (args.out / "stats.md").write_text(table + "\n", encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
