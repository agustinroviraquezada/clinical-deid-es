import pytest

from clinical_deid.domain.sentences import sentence_bounds

TEXT = (
    "Paciente Lucía Fernández, de 54 años. Acude el 12/03/2025 con fiebre! "
    "Remitida por el Dr. García al Hospital San Ramón.\nVive en Teruel"
)


def _sentence_of(fragment: str, text: str = TEXT) -> str:
    start = text.index(fragment)
    begin, end = sentence_bounds(text, start, start + len(fragment))
    return text[begin:end]


def test_first_sentence_ends_at_its_period():
    assert _sentence_of("Lucía Fernández") == "Paciente Lucía Fernández, de 54 años."


def test_middle_sentence_ends_at_exclamation_mark():
    assert _sentence_of("12/03/2025") == "Acude el 12/03/2025 con fiebre!"


def test_newline_is_a_sentence_boundary():
    assert _sentence_of("Teruel") == "Vive en Teruel"


def test_entity_containing_a_period_stays_inside_its_sentence():
    sentence = _sentence_of("Dr. García")

    assert "Dr. García" in sentence
    assert sentence.endswith("Hospital San Ramón.")
    assert "Teruel" not in sentence


def test_text_without_terminator_is_one_sentence():
    text = "Lucía Fernández ingresa hoy"

    assert _sentence_of("Lucía", text) == text


@pytest.mark.parametrize(("start", "end"), [(-1, 3), (3, 3), (0, len(TEXT) + 1)])
def test_invalid_span_raises(start: int, end: int):
    with pytest.raises(ValueError):
        sentence_bounds(TEXT, start, end)
