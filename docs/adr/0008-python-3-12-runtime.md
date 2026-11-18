# ADR-0008 · Python 3.12 runtime

- **Status:** Accepted (2026-11-18)

## Context
Design §11 fixed Python 3.11. ADR-0005 deploys a container image built on the official AWS
Lambda base image. The `public.ecr.aws/lambda/python:3.11` image runs on Amazon Linux 2, which
ships glibc 2.26. T2.6 adds the model to the image, so the image now needs `torch` and `numpy`.
`torch` ≥ 2.6 publishes only `manylinux_2_28` wheels, and `numpy` 2.4 publishes only
`manylinux_2_27/2_28` wheels. Both need glibc ≥ 2.28. On the 3.11 image pip therefore tried to
build numpy from source and failed, because the image has no compiler. Downgrading is not an
option: `transformers` 5 requires `torch` ≥ 2.6.

## Decision
Move the whole project to Python 3.12 and build the image on
`public.ecr.aws/lambda/python:3.12` (Amazon Linux 2023, glibc 2.34), pinned by digest. This
applies to `pyproject.toml` (`requires-python`, ruff target), CI, the devcontainer, design §11
and AGENTS.md.

## Alternatives considered
- Keep 3.11 on a Debian base (`python:3.11-slim` + `awslambdaric`) · still a valid Lambda image,
  but it drops the official AWS image. It also needs the runtime client as an extra dependency
  and the Runtime Interface Emulator downloaded separately for the smoke test, so there are more
  moving parts to maintain and secure.
- Pin older `torch`/`numpy` with `manylinux2014` wheels · impossible with `transformers` 5, and
  it would keep known `torch` vulnerabilities.

## Consequences
- The image keeps the AWS-maintained base and the built-in emulator; the Dockerfile barely changes.
- Every environment moves to 3.12. Colab (3.13) is unaffected, because it only installs the
  `train` group and its own torch.
- The local virtual environment must be rebuilt (`uv sync`), which re-downloads torch.
