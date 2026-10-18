# Requirements and scope

> Spec 1 of 3 (SDD): **requirements** → `design.md` → `tasks.md`.
> Source: feasibility session of 17–18 Oct 2026 (`docs/feasibility.md`).
> Legend: **DECIDED** (do not change without the author) · **PROPOSED** (do not implement as final) · **PENDING** (do not implement).
> Scope changes: only through an ADR in `docs/adr/` plus an update to this file.

## 1. Problem

Before clinical notes can be used for research or sent to a third-party LLM, the patient's personal
data must be removed. Doing it by hand is slow, and sending a note without de-identification exposes
health data.

## 2. User and use case (DECIDED)

- **User:** a researcher or individual user. One document per request, no batches.
- **Use case:** paste text or upload a `.txt` file → receive the text with personal data masked by
  category → copy or download it to use elsewhere, for example with Claude.
- Use is at the user's own risk, with a visible notice.

## 3. Goal and hypothesis (DECIDED)

- **Goal:** a usable tool deployed at a public URL that demonstrates the full cycle: data, model,
  evaluation, LLM, API, container, CI/CD and deployment.
- **Technical hypothesis:** the cascade improves the model's recall on hard entities at a bounded
  extra cost. A negative result is documented as a finding.

## 4. Functional requirements

| ID | Requirement | Status |
| --- | --- | --- |
| FR-01 | Input: pasted text or a `.txt` file, one document per request, at most 10,000 characters. Over the limit → clear error | DECIDED |
| FR-02 | An in-house NER model (clinical RoBERTa fine-tuned on MEDDOCAN) detects personal data | DECIDED |
| FR-03 | Output: text with entities replaced by their grouped category (`[NAME]`, `[DATE]`…), ready to copy or download | DECIDED |
| FR-04 | Grouped categories: 6–8 (NAME, DATE, LOCATION, ID, CONTACT, AGE, PROFESSION, OTHER). Exact mapping set after inspecting the corpus | DECIDED (mapping PENDING) |
| FR-05 | Cascade: entities with confidence < threshold are sent to the LLM, which **confirms or rejects** them and assigns a category. It does not search for new entities | DECIDED |
| FR-06 | Only the **sentence** containing the uncertain entity is sent to the LLM, never the document | DECIDED |
| FR-07 | At most N sentences per document go to the LLM; beyond N, the remaining ones are masked by default (conservative) | DECIDED (value of N PENDING, week 3) |
| FR-08 | Login with a single demo account; test username and password in the README | DECIDED |
| FR-09 | Visible privacy notice before processing | DECIDED |
| FR-10 | Mandatory "use at my own risk" checkbox | PROPOSED |
| FR-11 | "Comparison" tab with **precomputed** results of the three configurations on the examples | DECIDED |
| FR-12 | Demo examples: MEDDOCAN test cases + 5–10 synthetic notes in a different style, labelled as synthetic | DECIDED |
| FR-13 | MEDDOCAN attribution (CC BY 4.0) on the web page, in the README and in the slides | DECIDED |

## 5. Non-functional requirements

| ID | Requirement | Status |
| --- | --- | --- |
| NFR-01 | Text is processed in memory only; never stored on disk, in a database or in logs | DECIDED |
| NFR-02 | Logs record metadata only: length, latency, number of entities and number sent to the LLM | DECIDED |
| NFR-03 | Latency < 10 s per document in the demo, **excluding** cold starts | DECIDED |
| NFR-04 | Abuse protection: Lambda reserved concurrency, in-app limits, Bedrock timeout, AWS Budgets alerts | DECIDED |
| NFR-05 | Total project cost ≤ €50 (≈€5 LLM, ≤€10 paid training, ≈€35 AWS), reviewable | DECIDED |
| NFR-06 | Security covers LLM01 prompt injection, improper output handling, LLM10 unbounded consumption, XSS, authentication and supply chain (OWASP; LLM numbering from the 2025 edition) | DECIDED |
| NFR-07 | Single AWS region: Ireland (`eu-west-1`); LLM with an EU inference profile | DECIDED |
| NFR-08 | Public repository: never secrets, patient data or model weights | DECIDED |
| NFR-09 | All repository content (code, docs, commits, issues) is written in English | DECIDED |

## 6. Acceptance criteria — definition of done (DECIDED)

- [ ] **AC-01** A user logs in, uploads or pastes a document and receives the de-identified text, which they can copy or download.
- [ ] **AC-02** Model-only recall ≥ **0.90** on the MEDDOCAN test set (span + type), with precision ≥ **0.85**.
- [ ] **AC-03** Response < 10 s in the demo (excluding cold starts).
- [ ] **AC-04** Visible privacy notice and enforced size limit.
- [ ] **AC-05** Evaluation report of the 3 configurations (model only, LLM only, cascade) on recall, precision, F1, cost per document and latency; overall and per category.
- [ ] **AC-06** Deployed on Lambda with a public URL, updated by GitHub Actions.
- [ ] **AC-07** README complete according to the TFM specification, with links to deployment, slides and video.

Anything beyond this is iteration.

## 7. Metrics

| Metric | Role | Threshold |
| --- | --- | --- |
| Recall (span + type, micro) | Primary | ≥ 0.90 (model only) |
| Precision | Constraint | ≥ 0.85 |
| F1 | Secondary, comparable with the literature | — |
| Latency per document | Product | < 10 s |
| Cost per document | Comparison | Within NFR-05 |

Evaluation: model and cascade on the 250 test documents; "LLM only" on a sample of 50 (extendable
depending on cost and results). The cascade threshold is set **once, on dev**.

## 8. Out of scope (DECIDED)

- Real patient data; any non-public data, code or knowledge.
- Normalisation to ontologies (SNOMED CT, ICD-10); other languages; PDF and .docx.
- Batch processing; running the 3 configurations live on every upload.
- The LLM looking for entities the model did not detect; self-hosted LLM.
- User management beyond the demo account; Gradio; always-on servers.
- Hand-annotated out-of-domain test set (domain shift is a **documented limitation**).
- Keeping the tool online after the grade is published.

**Only if time allows** (rule of 6 Nov: cascade deployed and evaluated, and ≤ 36 h spent):
JSON extension (drugs and diagnoses, evaluated on PharmaCoNER), live comparison,
API Gateway in front of Lambda, a second base model.

## 9. Accepted limitations

- MEDDOCAN consists of clinical case reports with synthetic personal data: performance on real notes will likely be lower.
- The task is nearly solved on MEDDOCAN (best system ≈ F1 0.975): the cascade's gain on that test set will be small.
- An uncertain sentence leaves the system towards a third party (Bedrock). Mitigated with minimal fragments and a no-retention provider; explained in the slides.
- Not a certified system for real health data.
