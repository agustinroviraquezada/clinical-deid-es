# ADR-0003 · MEDDOCAN from Zenodo with an in-house converter

- **Status:** Accepted · 17 Oct 2026

## Context
MEDDOCAN (CC BY 4.0) is distributed on Zenodo (v1.0, DOI 10.5281/zenodo.4279323) in BRAT and XML formats. A Hugging Face version also exists (`bigbio/meddocan`).

## Decision
Download v1.0 from Zenodo with md5 verification and convert BRAT → BIO with an in-house, tested converter.

## Alternatives considered
`bigbio/meddocan`: convenient, but may rely on loading scripts that recent `datasets` versions no longer support.

## Consequences
1–1.5 h for the converter. Pinned version and primary source; a tested converter is good best-practice material.
