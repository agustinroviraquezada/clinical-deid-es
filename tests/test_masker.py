import pytest

from clinical_deid.domain.categories import Category
from clinical_deid.domain.entities import Entity
from clinical_deid.domain.masker import mask


def _entity(text: str, fragment: str, category: Category, confidence: float = 0.99) -> Entity:
    start = text.index(fragment)
    return Entity(
        start=start,
        end=start + len(fragment),
        type=category.value,
        category=category,
        text=fragment,
        confidence=confidence,
    )


def test_spans_are_replaced_by_their_category():
    text = "Paciente Lucía Fernández ingresa el 12/03/2025."
    entities = [
        _entity(text, "Lucía Fernández", Category.NAME),
        _entity(text, "12/03/2025", Category.DATE),
    ]

    assert mask(text, entities) == "Paciente [NAME] ingresa el [DATE]."


def test_text_without_entities_is_unchanged():
    text = "Sin hallazgos relevantes."

    assert mask(text, []) == text


def test_entity_order_does_not_matter():
    text = "Paciente Lucía Fernández ingresa el 12/03/2025."
    entities = [
        _entity(text, "12/03/2025", Category.DATE),
        _entity(text, "Lucía Fernández", Category.NAME),
    ]

    assert mask(text, entities) == "Paciente [NAME] ingresa el [DATE]."


def test_adjacent_spans_are_both_masked():
    text = "Lucía,Madrid"
    entities = [
        _entity(text, "Lucía", Category.NAME),
        _entity(text, ",Madrid", Category.LOCATION),
    ]

    assert mask(text, entities) == "[NAME][LOCATION]"


def test_overlapping_spans_are_rejected():
    text = "Lucía Fernández"
    entities = [
        _entity(text, "Lucía Fernández", Category.NAME),
        _entity(text, "Fernández", Category.NAME),
    ]

    with pytest.raises(ValueError, match="overlap"):
        mask(text, entities)


def test_out_of_range_span_is_rejected():
    entity = Entity(start=5, end=50, type="NAME", category=Category.NAME, text="x", confidence=0.9)

    with pytest.raises(ValueError, match="range"):
        mask("texto corto", [entity])
