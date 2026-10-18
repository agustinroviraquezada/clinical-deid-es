# Tasks

> Spec 3 of 3 (SDD). Each task becomes a GitHub **issue** via `scripts/github_backlog.py`
> (milestone = week). Live status lives in GitHub Issues + Projects; this file is the plan.
> Fixed format so the script can parse it: `## Week N · …` and `### Tn.m · Title` with its fields.
> Hours = estimate. Actual hours are logged at the end of each session (`/close-session`).

## Week 1 · Definition (17 Oct–23 Oct) · 10 h

Checkpoint **23 Oct**: "hello world" deployed on Lambda from GitHub Actions. Otherwise week 2 starts here.

### T1.1 · Accounts and cost guardrails
- Hours: 1.5
- Labels: infra, aws
- Spec: NFR-05, NFR-07
- Done when: new AWS account on the paid plan, MFA on root, separate admin user, region eu-west-1, AWS Budgets with alerts at 50 % and 80 % of €50, Anthropic use-case form submitted in Bedrock, Lambda quotas checked (increase requested if needed), Hugging Face account and token.

### T1.2 · Repository and environment
- Hours: 1.5
- Labels: repo
- Spec: NFR-08, NFR-09
- Done when: public repo with this kit, Codespace starts with the devcontainer, Claude Code signed in with the personal account, `uv run pytest` and `uv run ruff check .` pass, milestones and issues created with the script, GitHub Projects board created.

### T1.3 · API skeleton and tests
- Hours: 2
- Labels: api
- Spec: design §2, §6
- Done when: `src/clinical_deid/` structure created, `/api/health` responds, ports defined, cascade with test doubles returns a masked sample text, tests green.

### T1.4 · CI on GitHub Actions
- Hours: 1
- Labels: ci
- Spec: design §9
- Done when: `ci.yml` runs ruff and pytest on every push and PR; Dependabot enabled.

### T1.5 · Hello world on Lambda with CD
- Hours: 4
- Labels: infra, aws, ci
- Spec: design §9, ADR-0005
- Done when: Lambda Dockerfile, ECR repository, Lambda function with Function URL (auth `AWS_IAM`), OIDC role for GitHub Actions, `deploy.yml` builds and deploys on every push to `main`, `/api/health` responds at the URL to a signed request.

## Week 2 · Model (24 Oct–30 Oct) · 12 h

Checkpoint **31 Oct**: recall ≥ 0.90 and precision ≥ 0.85 on test. If not after 3 runs, plan B: accept and document.

### T2.1 · MEDDOCAN download and BRAT-to-BIO converter
- Hours: 2
- Labels: data
- Spec: FR-02, ADR-0003
- Done when: script downloads version 1.0 from Zenodo and verifies the md5; BRAT→BIO converter with tests (offsets, multi-token entities, overlaps); type statistics per split.

### T2.2 · Grouped category mapping
- Hours: 0.5
- Labels: data
- Spec: FR-04
- Done when: MEDDOCAN type → category table in `domain/categories.py` with a test covering every type in the corpus.

### T2.3 · Fine-tuning on Colab
- Hours: 4
- Labels: model
- Spec: FR-02, design §5
- Done when: notebook clones the repo, trains with checkpoints, at most 3 logged runs (hyperparameters and metrics), model in safetensors.

### T2.4 · Model-only evaluation
- Hours: 2
- Labels: evaluation
- Spec: AC-02, requirements §7
- Done when: `evaluate.py` reports recall, precision and F1 (span + type) overall and per category on dev and test; results in `evaluation/report/`.

### T2.5 · Publish model on the Hub (private)
- Hours: 0.5
- Labels: model
- Spec: design §5
- Done when: private Hub repository with a minimal model card citing MEDDOCAN; revision recorded in the configuration.

### T2.6 · API with the real model deployed
- Hours: 3
- Labels: api, infra
- Spec: FR-01, FR-03, AC-03
- Done when: `hf_ner.py` adapter, `/api/deidentify` with the model only, image with the model inside, deployed; latency measured (cold and warm) and Lambda memory tuned.

## Week 3 · Cascade (31 Oct–6 Nov) · 12 h

Checkpoint **6 Nov**: is the core done? Extension rule: cascade deployed and evaluated **and** ≤ 36 h spent.

### T3.1 · Per-entity confidence and threshold on dev
- Hours: 2
- Labels: cascade
- Spec: FR-05, design §3
- Done when: confidence = mean token probability; recall/precision curve per threshold on dev; threshold chosen and stored; value of N decided from the distribution of uncertain entities.

### T3.2 · Bedrock adapter with schema validation
- Hours: 3
- Labels: cascade, security
- Spec: FR-05, FR-06, NFR-06
- Done when: fixed prompt with delimited sentence, Pydantic-validated output, temperature 0, timeout, fail-safe; tests with the double and with prompt-injection sentences.

### T3.3 · Full cascade with N cap
- Hours: 2
- Labels: cascade
- Spec: FR-07, design §3
- Done when: cascade wires both ports, applies N and the fail-safe; tests with no network.

### T3.4 · Evaluation of the 3 configurations
- Hours: 3
- Labels: evaluation
- Spec: AC-05
- Done when: model only and cascade on the full test set, LLM only on 50 documents; recall, precision, F1, cost and latency; Markdown + JSON report for the Comparison tab; actual cost recorded.

### T3.5 · Cascade deployed
- Hours: 2
- Labels: infra, aws
- Spec: AC-06
- Done when: Lambda role allowed to invoke only the specific Bedrock model; cascade working at the URL; logs with metadata only.

## Week 4 · Product (7 Nov–13 Nov) · 12 h

Checkpoint **13 Nov**: feature freeze. From here on, bug fixes only.

### T4.1 · Web interface
- Hours: 4
- Labels: web
- Spec: FR-01, FR-03, FR-09, FR-10, FR-11, FR-13
- Done when: page with notice, (checkbox if decided), paste or upload `.txt`, result with copy and download, Comparison tab, demo examples, attribution; no `innerHTML` with data.

### T4.2 · Demo login
- Hours: 2.5
- Labels: security, api
- Spec: FR-08, ADR-0006
- Done when: password hash, secure cookie, attempt limit, 401 on protected routes; tests.

### T4.3 · Limits and security headers
- Hours: 1.5
- Labels: security
- Spec: NFR-04, NFR-06
- Done when: 413 on size, reserved concurrency configured, CSP and headers, test that logs contain no text.

### T4.4 · Synthetic demo notes
- Hours: 1.5
- Labels: data
- Spec: FR-12
- Done when: 5 synthetic notes in a different style (progress note, abbreviations, discharge report) reviewed by hand and marked as synthetic; precomputed results included.

### T4.5 · Security review and slide draft
- Hours: 2.5
- Labels: security, docs
- Spec: NFR-06
- Done when: `/security-review` run and findings fixed or documented; slide draft with structure and diagrams.

## Week 5 · Submission (14 Nov–20 Nov) · 9 h

Milestone **20 Nov**: public access open and tested from a phone. **21 Nov**: submission.

### T5.1 · Final README and model card
- Hours: 2
- Labels: docs
- Spec: AC-07
- Done when: README with every required section, test username and password, links, limitations; complete model card; model made public.

### T5.2 · Slides
- Hours: 2.5
- Labels: docs
- Spec: AC-07
- Done when: slides covering problem, architecture, comparison, privacy, security, limitations and future work; public link in the README.

### T5.3 · Script and video
- Hours: 3
- Labels: docs
- Spec: AC-07
- Done when: video with screen recording uploaded, public link in the README.

### T5.4 · Public opening and submission
- Hours: 1.5
- Labels: infra, submission
- Spec: AC-06
- Done when: Function URL set to `NONE` on 20 Nov, tested from another device, submission checklist reviewed, form submitted on 21 Nov.

## After the grade

### T6.1 · Shutdown and clean-up
- Hours: 0.5
- Labels: infra, aws
- Spec: requirements §8
- Done when: Lambda function, ECR image, role and Function URL deleted; Budgets reviewed; README updated to state the demo is no longer online.
