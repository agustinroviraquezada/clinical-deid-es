# `adapters/` — implementations of the ports

An adapter connects the core to something concrete (a model, a cloud service, a fake). Each
adapter implements a protocol from `ports.py` by structural typing: it only needs a method with
the same signature, no inheritance.

## Files

| File | Implements | Status |
| --- | --- | --- |
| `fakes.py` | `EntityDetector`, `LLMVerifier` | T1.3 (done) |
| `hf_ner.py` | `EntityDetector` with `transformers` | T2.6 |
| `bedrock_llm.py` | `LLMVerifier` with `boto3` + schema validation | T3.2 (done) |

### `fakes.py` — test doubles
- `FakeDetector(entities)` — a **stub**: `detect()` returns the preset entities, whatever the text.
- `FakeVerifier(result)` — a **stub + spy**: `verify()` returns the given `Verdict`, or raises
  the given exception (to test the fail-safe in T3.3). Every call is recorded in `.calls`, so a
  test can assert the LLM was (or was not) called and with which sentence.

```python
cascade = Cascade(FakeDetector([entity]), FakeVerifier(verdict), threshold=0.85)
result = cascade.run("Paciente Lucía Fernández ...")
```

### `bedrock_llm.py` — LLM verifier on Bedrock
- `BedrockVerifier.from_settings()` builds a `bedrock-runtime` client in `AWS_REGION` with a
  short timeout and no retries; credentials come from the Lambda IAM role.
- Fixed system prompt; the sentence and the candidate go in `<sentence>`/`<candidate>` tags as
  data, with `<`/`>` neutralised so the input cannot close a tag. `temperature=0`, low `maxTokens`.
- The reply must be exactly `{"is_personal_data": bool, "category": "<Category>"}` (Pydantic,
  strict, no extra fields). Any error, timeout or out-of-schema reply raises
  `LLMVerificationError`, and the cascade masks the entity (fail-safe).
- Unit tests inject a fake client. `RUN_BEDROCK_TESTS=1 uv run pytest -m integration` calls the
  real model (costs a fraction of a cent; needs Bedrock model access in `eu-west-1`).

## Rules
- Cascade tests always use `fakes.py`: no network, no model download, no AWS cost.
- External SDKs (`transformers`, `torch`, `boto3`) are imported **only** here.
- Adapters never log user text, sentences or LLM responses.
