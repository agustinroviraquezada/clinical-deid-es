---
paths:
  - "tests/**/*.py"
---

# Test rules

- pytest, one file per module (`tests/test_<module>.py`), descriptive English names: `test_uncertain_entity_is_sent_to_llm`.
- Tests do not call Bedrock, download models or use the network: they use the doubles in `adapters/fakes.py`.
- Test texts are synthetic and invented (in Spanish, since the product handles Spanish notes). Never real data or fragments copied from real notes.
- Always cover the happy path, the limit (10,000 characters, N sentences) and the fail-safe.
- Security tests are marked `@pytest.mark.security` (prompt injection, XSS, logs without text, auth).
- Tests that need the real model or AWS are marked `@pytest.mark.integration` and do not run in CI by default.
