---
paths:
  - "Dockerfile"
  - "infra/**"
  - ".github/workflows/**"
---

# Infrastructure and CI/CD rules

- Single region `eu-west-1`. Do not create resources that are not in `specs/design.md` §9.
- GitHub Actions authenticates to AWS with **OIDC** (`aws-actions/configure-aws-credentials` with `role-to-assume`). No long-lived keys unless explicitly decided.
- Least-privilege IAM: the Lambda can only invoke the specific Bedrock model and write its logs.
- Pin versions: Lambda base image, GitHub actions by major version, Hub model revision.
- No secrets in the Dockerfile or workflow logs. `HF_TOKEN` only as a GitHub secret and never in the final image.
- Explain to the author what each new workflow or Dockerfile step does: he is learning.
- Any `aws` command that creates, changes or deletes resources requires confirmation.
