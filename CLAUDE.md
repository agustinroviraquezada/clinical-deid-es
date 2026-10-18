@AGENTS.md

## Claude Code

- Reply to the author in Spanish; write files, commits and issues in English (see AGENTS.md).
- For changes to `src/clinical_deid/cascade.py`, `adapters/bedrock_llm.py`, `api/auth.py` or `.github/workflows/`, use plan mode and wait for approval before editing.
- Workflow: `/implement-task <id>` for each task, `/close-session <hours>` at the end, `/security-review` before any relevant PR. `/mermaid-diagram` only when the author asks for it.
- Never run `aws` commands that create, modify or delete resources without explicit confirmation.
- The author is learning Docker, CI/CD and AWS: when touching those topics, briefly explain what each step does.
