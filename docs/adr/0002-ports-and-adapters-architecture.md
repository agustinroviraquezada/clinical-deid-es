# ADR-0002 · Lightweight ports and adapters architecture

- **Status:** Accepted · 18 Oct 2026

## Context
The base model must be configurable, cascade tests must not spend money on Bedrock, and the master's programme covers Clean Architecture (block 4).

## Decision
The core (`domain/`, `cascade.py`) depends on two protocols, `EntityDetector` and `LLMVerifier`. Adapters: Hugging Face model, Bedrock and test doubles.

## Alternatives considered
Simple layered design: faster, but couples the cascade to transformers/boto3. Full Clean Architecture with DDD: +4–6 h, excessive for the MVP.

## Consequences
+1–2 h of initial structure. Fast, cost-free tests; interchangeable model and LLM.
