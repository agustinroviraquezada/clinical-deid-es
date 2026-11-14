"""Grouped de-identification categories and the MEDDOCAN type mapping (FR-04).

The mapping covers the 22 entity types found in MEDDOCAN v1.0 (train, dev and test).
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class Category(StrEnum):
    """Grouped category shown in the masked output as ``[CATEGORY]``."""

    NAME = "NAME"
    DATE = "DATE"
    LOCATION = "LOCATION"
    ID = "ID"
    CONTACT = "CONTACT"
    AGE = "AGE"
    PROFESSION = "PROFESSION"
    OTHER = "OTHER"


MEDDOCAN_TO_CATEGORY: Mapping[str, Category] = MappingProxyType(
    {
        # Names of people (patients, clinicians and relatives).
        "NOMBRE_SUJETO_ASISTENCIA": Category.NAME,
        "NOMBRE_PERSONAL_SANITARIO": Category.NAME,
        "FAMILIARES_SUJETO_ASISTENCIA": Category.NAME,
        "FECHAS": Category.DATE,
        "EDAD_SUJETO_ASISTENCIA": Category.AGE,
        # Places and organisations.
        "TERRITORIO": Category.LOCATION,
        "CALLE": Category.LOCATION,
        "PAIS": Category.LOCATION,
        "HOSPITAL": Category.LOCATION,
        "INSTITUCION": Category.LOCATION,
        "CENTRO_SALUD": Category.LOCATION,
        # Identifiers.
        "ID_SUJETO_ASISTENCIA": Category.ID,
        "ID_TITULACION_PERSONAL_SANITARIO": Category.ID,
        "ID_ASEGURAMIENTO": Category.ID,
        "ID_CONTACTO_ASISTENCIAL": Category.ID,
        "ID_EMPLEO_PERSONAL_SANITARIO": Category.ID,
        # Contact details.
        "NUMERO_TELEFONO": Category.CONTACT,
        "NUMERO_FAX": Category.CONTACT,
        "CORREO_ELECTRONICO": Category.CONTACT,
        "PROFESION": Category.PROFESSION,
        # Sex is not one of the grouped categories, but it is still masked (conservative).
        "SEXO_SUJETO_ASISTENCIA": Category.OTHER,
        "OTROS_SUJETO_ASISTENCIA": Category.OTHER,
    }
)


def category_for(meddocan_type: str) -> Category:
    """Return the grouped category for a MEDDOCAN entity type.

    Unknown types fall back to ``Category.OTHER`` so the span is still masked (fail-safe).
    """
    return MEDDOCAN_TO_CATEGORY.get(meddocan_type, Category.OTHER)
