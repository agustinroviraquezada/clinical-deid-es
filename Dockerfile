# Container image for AWS Lambda (design §9, ADR-0005).
# Lambda runs this image and calls `clinical_deid.api.lambda_handler.handler` for each request.

# Pinned uv release (tag + digest), used only to export the locked dependency list.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

# AWS Lambda base image for Python 3.11, pinned by digest so every build starts from the same OS
# layer. It already contains the Lambda runtime client and the Runtime Interface Emulator used
# by the smoke test in deploy.yml.
FROM public.ecr.aws/lambda/python:3.11@sha256:ee9a61044fb04e52ded90db4e5b10ef442e39ffffdfc3f8eef4eda787ae3f20a

# Turn uv.lock into a requirements file with hashes (runtime dependencies only, no dev tools),
# then install it with pip into the folder Lambda loads code from. --require-hashes makes pip
# reject any package whose content differs from the lockfile.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt --target "${LAMBDA_TASK_ROOT}" \
    && rm -f /tmp/requirements.txt /usr/local/bin/uv pyproject.toml uv.lock

# Application code only (tests, notebooks, data and secrets are excluded by .dockerignore).
COPY src/clinical_deid "${LAMBDA_TASK_ROOT}/clinical_deid"

# Module path and attribute of the function Lambda calls.
CMD ["clinical_deid.api.lambda_handler.handler"]
