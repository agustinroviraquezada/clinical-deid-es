---
name: mermaid-diagram
description: Generates a Mermaid diagram (flowchart, sequence, architecture, Gantt, state) from the code or the specs, ready for the README, an ADR or the slides.
disable-model-invocation: true
argument-hint: "[what to diagram] [optional target: README | docs/... | slides]"
---

# Mermaid diagram: $ARGUMENTS

1. Identify what must be shown and pick the type:
   - Data flow or decision → `flowchart LR`
   - Interaction between components over time (browser, API, model, Bedrock) → `sequenceDiagram`
   - Module structure → `flowchart TB` with `subgraph`
   - Planning → `gantt`
   - Lifecycle → `stateDiagram-v2`
2. Base the diagram on what exists: read the relevant specs and code. Do not draw components that are not in `specs/design.md` or `src/`; mark PROPOSED items with `(proposed)`.
3. Style rules:
   - Labels in English, short (≤ 5 words per line; use `<br/>`).
   - At most ~12 nodes; if there are more, split into two diagrams.
   - A clear Markdown title above the block stating the main idea.
   - No custom colours or styles (it must render well in GitHub light and dark themes).
4. Deliver the ` ```mermaid ` block in the chat. If a target was given, propose where to insert it and do so only after the author approves.
5. Remember GitHub renders Mermaid directly in `.md` files.
