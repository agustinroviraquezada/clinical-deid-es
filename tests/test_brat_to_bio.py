"""Tests for the MEDDOCAN BRAT -> BIO converter (T2.1). Synthetic Spanish text only."""

import json
from collections import Counter

import pytest

from modeling.data_prep.brat_to_bio import (
    Span,
    SplitStats,
    convert_split,
    format_stats,
    parse_ann,
    resolve_overlaps,
    to_bio_sentences,
    tokenize,
)


def _span(text: str, fragment: str, type_: str) -> Span:
    start = text.index(fragment)
    return Span(start, start + len(fragment), type_)


def _pairs(sentences):
    return [list(zip(s.tokens, s.tags, strict=True)) for s in sentences]


# --- parse_ann -------------------------------------------------------------


def test_parse_ann_reads_text_bound_annotations():
    content = "T1\tFECHAS 10 20\t01/02/2020\nT2\tNOMBRE_SUJETO_ASISTENCIA 0 9\tAna López\n"
    assert parse_ann(content) == [
        Span(10, 20, "FECHAS"),
        Span(0, 9, "NOMBRE_SUJETO_ASISTENCIA"),
    ]


def test_parse_ann_ignores_notes_relations_and_blank_lines():
    content = "T1\tPAIS 0 6\tEspaña\n#1\tAnnotatorNotes T1\tnota\nR1\tRel Arg1:T1 Arg2:T1\n\n"
    assert parse_ann(content) == [Span(0, 6, "PAIS")]


# --- resolve_overlaps ------------------------------------------------------


def test_non_overlapping_spans_are_kept_sorted():
    spans = [Span(10, 15, "B"), Span(0, 5, "A")]
    assert resolve_overlaps(spans) == ([Span(0, 5, "A"), Span(10, 15, "B")], 0)


def test_longest_span_wins_an_overlap():
    spans = [Span(0, 5, "SHORT"), Span(2, 12, "LONG")]
    assert resolve_overlaps(spans) == ([Span(2, 12, "LONG")], 1)


def test_overlap_tie_keeps_the_first_span():
    spans = [Span(0, 6, "FIRST"), Span(3, 9, "SECOND")]
    assert resolve_overlaps(spans) == ([Span(0, 6, "FIRST")], 1)


def test_adjacent_spans_do_not_overlap():
    spans = [Span(0, 5, "A"), Span(5, 9, "B")]
    assert resolve_overlaps(spans) == ([Span(0, 5, "A"), Span(5, 9, "B")], 0)


# --- tokenize --------------------------------------------------------------


def test_tokenize_keeps_character_offsets():
    text = "Paciente de 70 años, ingresa."
    tokens = tokenize(text)
    assert [t.text for t in tokens] == ["Paciente", "de", "70", "años", ",", "ingresa", "."]
    assert all(text[t.start : t.end] == t.text for t in tokens)


def test_tokenize_splits_a_word_at_an_entity_boundary():
    text = "Dr: DRAlberto Gil"
    tokens = tokenize(text, boundaries={text.index("Alberto")})
    assert [t.text for t in tokens] == ["Dr", ":", "DR", "Alberto", "Gil"]


# --- to_bio_sentences ------------------------------------------------------


def test_single_and_multi_token_entities_get_b_and_i_tags():
    text = "Ana María López nació el 03/03/1946"
    spans = [
        _span(text, "Ana María López", "NOMBRE_SUJETO_ASISTENCIA"),
        _span(text, "03/03/1946", "FECHAS"),
    ]
    assert _pairs(to_bio_sentences(text, spans)) == [
        [
            ("Ana", "B-NOMBRE_SUJETO_ASISTENCIA"),
            ("María", "I-NOMBRE_SUJETO_ASISTENCIA"),
            ("López", "I-NOMBRE_SUJETO_ASISTENCIA"),
            ("nació", "O"),
            ("el", "O"),
            ("03", "B-FECHAS"),
            ("/", "I-FECHAS"),
            ("03", "I-FECHAS"),
            ("/", "I-FECHAS"),
            ("1946", "I-FECHAS"),
        ]
    ]


def test_adjacent_entities_of_the_same_type_start_with_b():
    text = "Madrid 28036"
    spans = [_span(text, "Madrid", "TERRITORIO"), _span(text, "28036", "TERRITORIO")]
    assert to_bio_sentences(text, spans)[0].tags == ["B-TERRITORIO", "B-TERRITORIO"]


def test_entity_that_starts_mid_word_is_split_exactly():
    text = "Firmado: DRAlberto Gil"
    spans = [_span(text, "Alberto Gil", "NOMBRE_PERSONAL_SANITARIO")]
    assert _pairs(to_bio_sentences(text, spans)) == [
        [
            ("Firmado", "O"),
            (":", "O"),
            ("DR", "O"),
            ("Alberto", "B-NOMBRE_PERSONAL_SANITARIO"),
            ("Gil", "I-NOMBRE_PERSONAL_SANITARIO"),
        ]
    ]


def test_entity_that_ends_mid_word_is_split_exactly():
    text = "Varón de 52 añosingresa hoy"
    spans = [_span(text, "52 años", "EDAD_SUJETO_ASISTENCIA")]
    sentence = to_bio_sentences(text, spans)[0]
    assert sentence.tokens == ["Varón", "de", "52", "años", "ingresa", "hoy"]
    assert sentence.tags == [
        "O",
        "O",
        "B-EDAD_SUJETO_ASISTENCIA",
        "I-EDAD_SUJETO_ASISTENCIA",
        "O",
        "O",
    ]


def test_entity_at_the_end_of_the_text_is_tagged():
    text = "Correo: ana.gil@ejemplo.es"
    spans = [_span(text, "ana.gil@ejemplo.es", "CORREO_ELECTRONICO")]
    tags = to_bio_sentences(text, spans)[0].tags
    assert tags[:2] == ["O", "O"]
    assert tags[2] == "B-CORREO_ELECTRONICO"
    assert set(tags[3:]) == {"I-CORREO_ELECTRONICO"}


def test_document_without_entities_is_all_o():
    text = "Sin hallazgos relevantes."
    assert to_bio_sentences(text, [])[0].tags == ["O", "O", "O", "O"]


def test_overlapping_spans_are_resolved_before_tagging():
    text = "Calle Mayor 5 Madrid"
    spans = [_span(text, "Calle Mayor 5", "CALLE"), _span(text, "Mayor", "TERRITORIO")]
    assert to_bio_sentences(text, spans)[0].tags == ["B-CALLE", "I-CALLE", "I-CALLE", "O"]


def test_text_is_split_into_sentences_by_newline_and_final_punctuation():
    text = "Ingresa hoy. Refiere dolor.\nAlta el lunes"
    sentences = to_bio_sentences(text, [])
    assert [s.tokens for s in sentences] == [
        ["Ingresa", "hoy", "."],
        ["Refiere", "dolor", "."],
        ["Alta", "el", "lunes"],
    ]


def test_period_not_followed_by_uppercase_does_not_split():
    text = "Dosis de 2.5 mg. cada 8 horas"
    assert len(to_bio_sentences(text, [])) == 1


def test_sentence_is_never_split_inside_an_entity():
    text = "Atendido por Dr. Pedro Ruiz en consulta"
    spans = [_span(text, "Dr. Pedro Ruiz", "NOMBRE_PERSONAL_SANITARIO")]
    assert len(to_bio_sentences(text, spans)) == 1


def test_blank_lines_produce_no_empty_sentences():
    text = "Primera línea\n\n\nSegunda línea\n"
    sentences = to_bio_sentences(text, [])
    assert len(sentences) == 2
    assert all(s.tokens for s in sentences)


# --- convert_split ---------------------------------------------------------


def _write_doc(folder, doc_id, text, ann):
    folder.joinpath(f"{doc_id}.txt").write_text(text, encoding="utf-8", newline="")
    folder.joinpath(f"{doc_id}.ann").write_text(ann, encoding="utf-8", newline="")


def test_convert_split_writes_jsonl_and_type_statistics(tmp_path):
    brat = tmp_path / "brat"
    brat.mkdir()
    ann = (
        "T1\tNOMBRE_SUJETO_ASISTENCIA 0 7\tAna Gil\n"
        "T2\tEDAD_SUJETO_ASISTENCIA 9 16\t70 años\n"
        "T3\tPAIS 26 32\tEspaña\n"
    )
    _write_doc(brat, "doc1", "Ana Gil, 70 años.\nVive en España", ann)
    _write_doc(brat, "doc2", "Sin datos.", "")
    out = tmp_path / "bio" / "train.jsonl"

    stats = convert_split(brat, out)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["doc_id"] for r in rows] == ["doc1", "doc1", "doc2"]
    assert rows[0]["tokens"] == ["Ana", "Gil", ",", "70", "años", "."]
    assert rows[1]["tags"] == ["O", "O", "B-PAIS"]
    assert stats.documents == 2
    assert stats.sentences == 3
    assert stats.entities == {
        "NOMBRE_SUJETO_ASISTENCIA": 1,
        "EDAD_SUJETO_ASISTENCIA": 1,
        "PAIS": 1,
    }
    assert stats.dropped_overlaps == 0


def test_convert_split_rejects_annotation_text_mismatch(tmp_path):
    brat = tmp_path / "brat"
    brat.mkdir()
    _write_doc(brat, "doc1", "Ana Gil", "T1\tNOMBRE_SUJETO_ASISTENCIA 0 7\tOtro nombre\n")
    with pytest.raises(ValueError, match="doc1"):
        convert_split(brat, tmp_path / "out.jsonl")


def test_format_stats_builds_a_type_by_split_table():
    stats = {
        "train": SplitStats(documents=2, sentences=5, entities=Counter({"FECHAS": 3, "PAIS": 1})),
        "dev": SplitStats(documents=1, sentences=2, entities=Counter({"FECHAS": 1})),
    }
    table = format_stats(stats)
    assert "| Type | train | dev | Total |" in table
    assert "| FECHAS | 3 | 1 | 4 |" in table
    assert "| PAIS | 1 | 0 | 1 |" in table
    assert "| Documents | 2 | 1 | 3 |" in table
