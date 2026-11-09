from clinical_deid.adapters.fakes import FakeDetector, FakeVerifier
from clinical_deid.cascade import Cascade
from clinical_deid.domain.categories import Category
from clinical_deid.domain.entities import Entity, Verdict

SAMPLE_NOTE = (
    "Paciente Lucía Fernández, de 54 años, acude a consulta el 12/03/2025 "
    "en el Hospital San Ramón de Teruel."
)
THRESHOLD = 0.85


def _entity(fragment: str, category: Category, confidence: float) -> Entity:
    start = SAMPLE_NOTE.index(fragment)
    return Entity(
        start=start,
        end=start + len(fragment),
        type=category.value,
        category=category,
        text=fragment,
        confidence=confidence,
    )


def _cascade(entities: list[Entity]) -> tuple[Cascade, FakeVerifier]:
    verifier = FakeVerifier(Verdict(is_personal_data=True, category=Category.NAME))
    return Cascade(FakeDetector(entities), verifier, threshold=THRESHOLD), verifier


def test_sample_note_is_masked_with_test_doubles():
    cascade, _ = _cascade(
        [
            _entity("Lucía Fernández", Category.NAME, 0.98),
            _entity("54 años", Category.AGE, 0.95),
            _entity("12/03/2025", Category.DATE, 0.99),
            _entity("Hospital San Ramón", Category.LOCATION, 0.93),
            _entity("Teruel", Category.LOCATION, 0.97),
        ]
    )

    result = cascade.run(SAMPLE_NOTE)

    assert result.deidentified_text == (
        "Paciente [NAME], de [AGE], acude a consulta el [DATE] en el [LOCATION] de [LOCATION]."
    )
    assert len(result.entities) == 5
    assert result.n_llm == 0


def test_uncertain_entity_is_masked_by_default():
    cascade, verifier = _cascade([_entity("Teruel", Category.LOCATION, 0.40)])

    result = cascade.run(SAMPLE_NOTE)

    assert "Teruel" not in result.deidentified_text
    assert "[LOCATION]" in result.deidentified_text
    assert verifier.calls == []
    assert result.n_llm == 0


def test_entity_at_threshold_is_accepted_as_confident():
    cascade, verifier = _cascade([_entity("Lucía Fernández", Category.NAME, THRESHOLD)])

    result = cascade.run(SAMPLE_NOTE)

    assert "[NAME]" in result.deidentified_text
    assert verifier.calls == []


def test_text_without_entities_is_returned_unchanged():
    cascade, _ = _cascade([])

    result = cascade.run(SAMPLE_NOTE)

    assert result.deidentified_text == SAMPLE_NOTE
    assert result.entities == []


def test_empty_text_is_returned_empty():
    cascade, _ = _cascade([])

    assert cascade.run("").deidentified_text == ""
