"""Grouped de-identification categories (FR-04).

The MEDDOCAN type -> category mapping is defined in task T2.2, after inspecting the corpus.
"""

from enum import StrEnum


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
