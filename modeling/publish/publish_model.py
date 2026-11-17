"""Publish the fine-tuned model on the Hugging Face Hub as a private repository (task T2.5).

Decisions (T2.5, design §5 and §8):

- The repository is created **private** and the upload is refused if it is not private.
- Only an allowlist of files is uploaded: config, tokenizer and ``model.safetensors``.
  ``training_args.bin`` (a pickle) and any other file are never published (supply chain).
- A minimal model card (``README.md``) cites MEDDOCAN (CC BY 4.0), the base model and its pinned
  revision, the test metrics of the model-only report (T2.4) and the intended use.
- Everything goes up in a single Hub commit; its SHA is the pinned revision, recorded in
  ``config/model.json`` so that deployment (T2.6) downloads exactly that version.
- The token is read from ``HF_TOKEN`` or asked with a hidden prompt. It is never printed or saved.

huggingface_hub is imported only inside ``HubClient``, so the pure helpers can be tested with a
fake client and without the ``train`` dependency group.

Usage (from the repository root)::

    uv run --group train python -m modeling.publish.publish_model \\
        --model-dir "<runs-root>/run-1/model" --run-log modeling/training/runs/run-1.json
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

DEFAULT_REPO_NAME = "clinical-deid-es-meddocan"
DEFAULT_REPORT = Path("src/clinical_deid/api/report/model_only.json")
DEFAULT_CONFIG = Path("config/model.json")
WEIGHTS_FILE = "model.safetensors"
ALLOWED_FILES = ("config.json", WEIGHTS_FILE, "tokenizer.json", "tokenizer_config.json")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


class Hub(Protocol):
    """The few Hub operations this script needs (real client below, fake in the tests)."""

    def whoami(self) -> str: ...

    def create_private_repo(self, repo_id: str) -> None: ...

    def is_private(self, repo_id: str) -> bool: ...

    def upload(self, repo_id: str, files: dict[str, Path | bytes], message: str) -> str: ...


# --- Model card --------------------------------------------------------------


def build_model_card(run_log: Mapping[str, Any], report: Mapping[str, Any]) -> str:
    """Return the model card (Markdown with YAML front matter) for the Hub repository."""
    config = run_log["config"]
    test = report["splits"]["test"]
    overall = test["overall"]
    rows = "\n".join(
        f"| {name} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['support']} |"
        for name, m in sorted(test["per_category"].items())
    )
    return f"""---
license: apache-2.0
language:
- es
library_name: transformers
pipeline_tag: token-classification
base_model: {config["model_name"]}
tags:
- clinical
- de-identification
- ner
- meddocan
---

# clinical-deid-es (MEDDOCAN)

Token-classification model (BIO tags, original MEDDOCAN types) that detects personal data in
Spanish clinical notes. It is the in-house NER stage of an academic cascade de-identification
tool (Master's final project, BIG school).

- Base model: [`{config["model_name"]}`](https://huggingface.co/{config["model_name"]})
  (Apache-2.0), revision `{config["model_revision"]}`.
- Fine-tuned with `transformers.Trainer` for {config["num_train_epochs"]} epochs,
  learning rate {config["learning_rate"]}.
- Weights in safetensors.

## Evaluation (MEDDOCAN test)

Entity-level, strict span + type, micro-averaged.

| Scope | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- |
| Overall | {overall["precision"]:.3f} | {overall["recall"]:.3f} | {overall["f1"]:.3f} | \
{overall["support"]} |
{rows}

## Data and attribution

Trained and evaluated on the **MEDDOCAN** corpus (Barcelona Supercomputing Center, CNIO and
Hospital 12 de Octubre; Plan TL), licensed **CC BY 4.0**. Marimon et al., *Automatic
De-identification of Medical Texts in Spanish: the MEDDOCAN Track, Corpus, Guidelines, Methods
and Evaluation of Results*, IberLEF@SEPLN 2019, pp. 618–638.
[doi:10.5281/zenodo.4279323](https://doi.org/10.5281/zenodo.4279323)

## Limitations

MEDDOCAN contains clinical case reports with synthetic personal data; performance on real notes
will likely be lower. Academic project: this is not a certified de-identification system and must
not be used on real patient data.
"""


# --- Files and publishing ----------------------------------------------------


def select_files(model_dir: Path) -> dict[str, Path]:
    """Return the allowlisted files of ``model_dir``; fail if the safetensors weights are absent."""
    if not (model_dir / WEIGHTS_FILE).is_file():
        raise FileNotFoundError(f"{WEIGHTS_FILE} not found in {model_dir}")
    return {name: model_dir / name for name in ALLOWED_FILES if (model_dir / name).is_file()}


def publish(hub: Hub, repo_id: str, model_dir: Path, card: str) -> str:
    """Upload the model and its card to a private repository; return the commit SHA."""
    files: dict[str, Path | bytes] = dict(select_files(model_dir))
    files["README.md"] = card.encode("utf-8")
    hub.create_private_repo(repo_id)
    if not hub.is_private(repo_id):
        raise RuntimeError(f"{repo_id} is not private; refusing to upload")
    return hub.upload(repo_id, files, message="Upload fine-tuned model and model card (T2.5)")


def write_model_config(path: Path, repo_id: str, revision: str) -> None:
    """Record the published repository and its pinned revision (a full commit SHA)."""
    if not _COMMIT_SHA.fullmatch(revision):
        raise ValueError(f"revision must be a full commit SHA, got {revision!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps({"repo_id": repo_id, "revision": revision}, indent=2)
    path.write_text(content + "\n", encoding="utf-8")


# --- Real Hub client ---------------------------------------------------------


class HubClient:
    """Thin wrapper over ``huggingface_hub.HfApi`` (needs the ``train`` dependency group)."""

    def __init__(self, token: str) -> None:
        from huggingface_hub import HfApi

        self._api = HfApi(token=token)

    def whoami(self) -> str:
        return self._api.whoami()["name"]

    def create_private_repo(self, repo_id: str) -> None:
        self._api.create_repo(repo_id, repo_type="model", private=True, exist_ok=True)

    def is_private(self, repo_id: str) -> bool:
        return bool(self._api.repo_info(repo_id, repo_type="model").private)

    def upload(self, repo_id: str, files: dict[str, Path | bytes], message: str) -> str:
        from huggingface_hub import CommitOperationAdd

        operations = [
            CommitOperationAdd(path_in_repo=name, path_or_fileobj=source)
            for name, source in files.items()
        ]
        commit = self._api.create_commit(
            repo_id, operations=operations, commit_message=message, repo_type="model"
        )
        return commit.oid


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-name", default=DEFAULT_REPO_NAME)
    args = parser.parse_args(argv)

    run_log = json.loads(args.run_log.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    card = build_model_card(run_log, report)

    token = os.environ.get("HF_TOKEN") or getpass.getpass("Hugging Face token (hidden): ")
    hub = HubClient(token)
    repo_id = f"{hub.whoami()}/{args.repo_name}"
    print(f"Uploading {args.model_dir} to private repository {repo_id} ...")
    revision = publish(hub, repo_id, args.model_dir, card)
    write_model_config(args.config, repo_id, revision)
    print(f"Done. Revision {revision} recorded in {args.config}")


if __name__ == "__main__":
    main()
