# Container image for AWS Lambda (design §9, ADR-0005).
# Lambda runs this image and calls `clinical_deid.api.lambda_handler.handler` for each request.

# Pinned uv release (tag + digest), used only to export the locked dependency list.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

# AWS Lambda base image for Python 3.12 on Amazon Linux 2023 (ADR-0008: torch and numpy need
# glibc >= 2.28, which the 3.11 image lacks), pinned by digest so every build starts from the
# same OS layer. It already contains the Lambda runtime client and the Runtime Interface Emulator used
# by the smoke test in deploy.yml.
FROM public.ecr.aws/lambda/python:3.12@sha256:a53086fc3118c5457097083ba3d1ccf1d8fdfcba9e7a90fbfc5d2b06c625215b

# Turn uv.lock into a requirements file with hashes (runtime dependencies only, no dev tools),
# then install it with pip into the folder Lambda loads code from. --require-hashes makes pip
# reject any package whose content differs from the lockfile.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt --target "${LAMBDA_TASK_ROOT}" \
    && rm -f /tmp/requirements.txt /usr/local/bin/uv pyproject.toml uv.lock

# Fine-tuned NER model (design §5). deploy.yml downloads the revision pinned in config/model.json
# into ./model before building; for a local build, see docs/deployment.md. The model goes in its
# own layer, before the code, so a code-only change reuses the cached ~500 MB layer.
COPY model/ /opt/model/

# MODEL_PATH tells the app where the model is (config.py). The HF_* variables keep transformers
# from ever reaching the Hub at runtime and point its cache at /tmp, the only writable folder
# in Lambda.
ENV MODEL_PATH=/opt/model \
    HF_HUB_OFFLINE=1 \
    HF_HOME=/tmp/hf

# Application code only (tests, notebooks, data and secrets are excluded by .dockerignore).
COPY src/clinical_deid "${LAMBDA_TASK_ROOT}/clinical_deid"

# Module path and attribute of the function Lambda calls.
CMD ["clinical_deid.api.lambda_handler.handler"]
