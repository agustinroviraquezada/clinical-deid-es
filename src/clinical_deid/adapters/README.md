# `adapters/` — implementations of the ports

An adapter connects the core to something concrete (a model, a cloud service, a fake). Each
adapter implements a protocol from `ports.py` by structural typing: it only needs a method with
the same signature, no inheritance.

## Files

| File | Implements | Status |
| --- | --- | --- |
| `fakes.py` | `EntityDetector`, `LLMVerifier` | T1.3 (done) |
| `hf_ner.py` | `EntityDetector` with `transformers` | T2.6 |
| `bedrock_llm.py` | `LLMVerifier` with `boto3` + schema validation | T3.2 |

### `fakes.py` — test doubles
- `FakeDetector(entities)` — a **stub**: `detect()` returns the preset entities, whatever the text.
- `FakeVerifier(result)` — a **stub + spy**: `verify()` returns the given `Verdict`, or raises
  the given exception (to test the fail-safe in T3.3). Every call is recorded in `.calls`, so a
  test can assert the LLM was (or was not) called and with which sentence.

```python
cascade = Cascade(FakeDetector([entity]), FakeVerifier(verdict), threshold=0.85)
result = cascade.run("Paciente Lucía Fernández ...")
```

## Rules
- Cascade tests always use `fakes.py`: no network, no model download, no AWS cost.
- External SDKs (`transformers`, `torch`, `boto3`) are imported **only** here.
- Adapters never log user text, sentences or LLM responses.
