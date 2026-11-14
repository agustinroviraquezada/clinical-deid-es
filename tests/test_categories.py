"""Tests for the MEDDOCAN type -> grouped category mapping (FR-04, T2.2)."""

from pathlib import Path

import pytest

from clinical_deid.domain.categories import MEDDOCAN_TO_CATEGORY, Category, category_for

# The 22 entity types found in MEDDOCAN v1.0 (train + dev + test) when the corpus was inspected.
EXPECTED_MAPPING = {
    "NOMBRE_SUJETO_ASISTENCIA": Category.NAME,
    "NOMBRE_PERSONAL_SANITARIO": Category.NAME,
    "FAMILIARES_SUJETO_ASISTENCIA": Category.NAME,
    "FECHAS": Category.DATE,
    "EDAD_SUJETO_ASISTENCIA": Category.AGE,
    "TERRITORIO": Category.LOCATION,
    "CALLE": Category.LOCATION,
    "PAIS": Category.LOCATION,
    "HOSPITAL": Category.LOCATION,
    "INSTITUCION": Category.LOCATION,
    "CENTRO_SALUD": Category.LOCATION,
    "ID_SUJETO_ASISTENCIA": Category.ID,
    "ID_TITULACION_PERSONAL_SANITARIO": Category.ID,
    "ID_ASEGURAMIENTO": Category.ID,
    "ID_CONTACTO_ASISTENCIAL": Category.ID,
    "ID_EMPLEO_PERSONAL_SANITARIO": Category.ID,
    "NUMERO_TELEFONO": Category.CONTACT,
    "NUMERO_FAX": Category.CONTACT,
    "CORREO_ELECTRONICO": Category.CONTACT,
    "PROFESION": Category.PROFESSION,
    "SEXO_SUJETO_ASISTENCIA": Category.OTHER,
    "OTROS_SUJETO_ASISTENCIA": Category.OTHER,
}

CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "meddocan"


@pytest.mark.parametrize(("meddocan_type", "category"), sorted(EXPECTED_MAPPING.items()))
def test_every_meddocan_type_maps_to_expected_category(
    meddocan_type: str, category: Category
) -> None:
    assert category_for(meddocan_type) is category


def test_mapping_covers_exactly_the_corpus_types() -> None:
    assert MEDDOCAN_TO_CATEGORY == EXPECTED_MAPPING


def test_every_category_is_reachable_from_some_type() -> None:
    assert set(MEDDOCAN_TO_CATEGORY.values()) == set(Category)


def test_mapping_keys_are_upper_case_labels() -> None:
    assert all(key == key.upper() and key.strip() == key for key in MEDDOCAN_TO_CATEGORY)


@pytest.mark.parametrize("unknown_type", ["DESCONOCIDO", "", "fechas", "B-FECHAS"])
def test_unknown_type_falls_back_to_other_so_it_is_still_masked(unknown_type: str) -> None:
    assert category_for(unknown_type) is Category.OTHER


@pytest.mark.integration
def test_all_types_in_local_corpus_have_a_mapping() -> None:
    ann_files = list(CORPUS_DIR.glob("*/brat/*.ann"))
    if not ann_files:
        pytest.skip("MEDDOCAN corpus not downloaded (run modeling/data_prep/download_meddocan.py)")

    corpus_types: set[str] = set()
    for ann_file in ann_files:
        for line in ann_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("T"):
                corpus_types.add(line.split("\t")[1].split(" ")[0])

    assert corpus_types <= set(MEDDOCAN_TO_CATEGORY)
