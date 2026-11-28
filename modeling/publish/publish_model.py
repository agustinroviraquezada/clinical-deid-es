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

Regenerating only the model card (T5.1; no token, nothing is uploaded)::

    uv run python -m modeling.publish.publish_model \\
        --run-log modeling/training/runs/run-1.json --card-only model-card.md

The repository is made public by hand at submission (T5.1); a full upload to it is then refused
by design, so the card is updated on its own (see docs/deployment.md).
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
DEFAULT_COMPARISON = Path("src/clinical_deid/api/report/comparison.json")
DEFAULT_SYNTHETIC = Path("src/clinical_deid/api/report/synthetic_examples.json")
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


def _metric_rows(per_category: Mapping[str, Mapping[str, Any]]) -> str:
    return "\n".join(
        f"| {name} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['support']} |"
        for name, m in sorted(per_category.items())
    )


def _metric_table(overall: Mapping[str, Any], per_category: Mapping[str, Mapping[str, Any]]) -> str:
    return (
        "| Scope | Precision | Recall | F1 | Support |\n"
        "| --- | --- | --- | --- | --- |\n"
        f"| Overall | {overall['precision']:.3f} | {overall['recall']:.3f} | "
        f"{overall['f1']:.3f} | {overall['support']} |\n"
        f"{_metric_rows(per_category)}\n"
    )


def _char_level_section(comparison: Mapping[str, Any] | None) -> str:
    model_only = (comparison or {}).get("configurations", {}).get("model_only", {})
    if "overall" not in model_only:
        return ""
    return f"""
### Character level (what the product masks)

Strict character span + category (the 8 product categories), micro-averaged, on the same test
set. Stricter than the token score above: a boundary off by one character is an error.

{_metric_table(model_only["overall"], model_only["per_category"])}"""


def _synthetic_section(synthetic: Mapping[str, Any] | None) -> str:
    scores = (synthetic or {}).get("overall", {}).get("model_only")
    if not scores:
        return ""
    return f"""
### Synthetic notes (other writing styles)

Five invented notes (progress note, abbreviations, discharge report, nursing note, referral
letter), annotated by hand. Character level: precision {scores["precision"]:.3f}, recall
{scores["recall"]:.3f}, F1 {scores["f1"]:.3f}. A handful of notes: an illustration of domain
shift, not a benchmark.
"""


def build_model_card(
    run_log: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    comparison: Mapping[str, Any] | None = None,
    synthetic: Mapping[str, Any] | None = None,
) -> str:
    """Return the model card (Markdown with YAML front matter) for the Hub repository.

    ``report`` is the BIO-token model-only report (T2.4). The optional ``comparison`` (T3.4) and
    ``synthetic`` (T4.4) reports add the character-level and out-of-domain results (T5.1).
    """
    config = run_log["config"]
    test = report["splits"]["test"]
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
tool (Master's final project, BIG school): entities below a confidence threshold are checked by
an LLM, sentence by sentence. Code: <https://github.com/agustinroviraquezada/clinical-deid-es>.

- Base model: [`{config["model_name"]}`](https://huggingface.co/{config["model_name"]})
  (Apache-2.0), revision `{config["model_revision"]}`.
- Fine-tuned with `transformers.Trainer` for {config["num_train_epochs"]} epochs,
  learning rate {config["learning_rate"]}.
- Weights in safetensors.

## Intended use

Research and teaching: detecting personal data (names, dates, locations, identifiers, contacts,
ages, professions and the other MEDDOCAN types) in Spanish clinical text similar to the MEDDOCAN
case reports, as a first stage whose output a person or a second system reviews.

## Out-of-scope use

- De-identifying real patient data, or any use where a missed entity has legal or clinical
  consequences: the model is not certified and it does miss entities.
- Languages other than Spanish, or non-clinical text.

## How to use

```python
from transformers import pipeline

ner = pipeline(
    "token-classification",
    model="ahrovira/clinical-deid-es-meddocan",
    aggregation_strategy="simple",
)
ner("Paciente de 45 años atendido en Valencia por el Dr. Martínez.")
```

## Evaluation (MEDDOCAN test)

### BIO token level

Entity-level, strict span + type, micro-averaged (seqeval).

{_metric_table(test["overall"], test["per_category"])}{_char_level_section(comparison)}\
{_synthetic_section(synthetic)}
## Data and attribution

Trained and evaluated on the **MEDDOCAN** corpus (Barcelona Supercomputing Center, CNIO and
Hospital 12 de Octubre; Plan TL), licensed **CC BY 4.0**. Marimon et al., *Automatic
De-identification of Medical Texts in Spanish: the MEDDOCAN Track, Corpus, Guidelines, Methods
and Evaluation of Results*, IberLEF@SEPLN 2019, pp. 618–638.
[doi:10.5281/zenodo.4279323](https://doi.org/10.5281/zenodo.4279323)

## Limitations

- MEDDOCAN contains clinical case reports with synthetic personal data; performance on real notes
  will likely be lower.
- Character-level scores are lower than token-level ones: span boundaries are sometimes off by a
  few characters, mostly in identifiers (ID), which are the weakest category at character level.
- PROFESSION has only 9 test examples: its scores are unstable.
- Academic project: this is not a certified de-identification system and must not be used on
  real patient data.
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


def _read_optional_json(path: Path) -> Mapping[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--comparison", type=Path, default=DEFAULT_COMPARISON)
    parser.add_argument("--synthetic", type=Path, default=DEFAULT_SYNTHETIC)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-name", default=DEFAULT_REPO_NAME)
    parser.add_argument(
        "--card-only",
        type=Path,
        metavar="OUT",
        help="write the model card to OUT and stop: no token, no upload",
    )
    args = parser.parse_args(argv)
    if args.card_only is None and args.model_dir is None:
        parser.error("--model-dir is required unless --card-only is given")

    run_log = json.loads(args.run_log.read_text(encoding="utf-8"))
    report = json.loads(args.report.read_text(encoding="utf-8"))
    card = build_model_card(
        run_log,
        report,
        comparison=_read_optional_json(args.comparison),
        synthetic=_read_optional_json(args.synthetic),
    )
    if args.card_only is not None:
        args.card_only.write_text(card, encoding="utf-8")
        print(f"Model card written to {args.card_only}")
        return

    token = os.environ.get("HF_TOKEN") or getpass.getpass("Hugging Face token (hidden): ")
    hub = HubClient(token)
    repo_id = f"{hub.whoami()}/{args.repo_name}"
    print(f"Uploading {args.model_dir} to private repository {repo_id} ...")
    revision = publish(hub, repo_id, args.model_dir, card)
    write_model_config(args.config, repo_id, revision)
    print(f"Done. Revision {revision} recorded in {args.config}")


if __name__ == "__main__":
    main()
