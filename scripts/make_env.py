"""Create or update the local .env with the demo login secrets (T4.2, design §7, §10).

Asks for the demo password without echo, stores only its argon2 hash, generates a random
SESSION_SECRET and optionally sets MODEL_PATH. Other variables already in .env (or, for a new
file, in .env.example) are kept. An existing .env is backed up to .env.bak first.

Usage:
    uv run python scripts/make_env.py [--model-path PATH] [--username demo]

Then start the API with:
    uv run uvicorn clinical_deid.api.app:app --reload --port 8000 --env-file .env
"""

import argparse
import getpass
import re
import secrets
import shutil
import sys
from pathlib import Path

from argon2 import PasswordHasher

ROOT = Path(__file__).resolve().parents[1]
MIN_PASSWORD_LENGTH = 12


def _quote(value: str) -> str:
    # Single quotes: python-dotenv takes the value literally, so the `$` in an argon2 hash
    # is never read as a variable reference.
    return f"'{value}'"


def render_env(template: str, values: dict[str, str]) -> str:
    """Set each key in ``values`` in a dotenv text, replacing existing lines or appending them.

    Comments, blank lines and any other variable are left as they are.
    """
    lines = template.splitlines()
    pending = dict(values)
    for index, line in enumerate(lines):
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in pending:
            key = match.group(1)
            lines[index] = f"{key}={_quote(pending.pop(key))}"
    if pending and lines and lines[-1].strip():
        lines.append("")
    lines.extend(f"{key}={_quote(value)}" for key, value in pending.items())
    return "\n".join(lines) + "\n"


def _read_text(path: Path) -> str:
    """Read a dotenv file as UTF-8, also accepting UTF-16 or a BOM (PowerShell `echo >`)."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _ask_password() -> str | None:
    password = getpass.getpass("Demo password (not shown): ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Use at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return None
    if getpass.getpass("Repeat it: ") != password:
        print("The passwords do not match.", file=sys.stderr)
        return None
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--username", default="demo", help="demo username (default: demo)")
    parser.add_argument("--model-path", type=Path, help="local folder of the fine-tuned model")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.model_path and not args.model_path.is_dir():
        print(f"Model folder not found: {args.model_path}", file=sys.stderr)
        return 1

    password = _ask_password()
    if password is None:
        return 1

    values = {
        "DEMO_USERNAME": args.username,
        "DEMO_PASSWORD_HASH": PasswordHasher().hash(password),
        "SESSION_SECRET": secrets.token_urlsafe(32),
    }
    if args.model_path:
        values["MODEL_PATH"] = str(args.model_path.resolve())

    env_file: Path = args.env_file
    example = env_file.with_name(".env.example")
    if env_file.exists():
        template = _read_text(env_file)
        backup = env_file.with_name(".env.bak")
        shutil.copyfile(env_file, backup)
        print(f"Backed up the previous file to {backup.name} (ignored by git).")
    elif example.exists():
        template = _read_text(example)
    else:
        template = ""

    # UTF-8 without BOM and LF endings, whatever the Windows defaults are.
    env_file.write_text(render_env(template, values), encoding="utf-8", newline="\n")
    print(f"Wrote {env_file.name}: {', '.join(values)} (secrets not shown).")
    if "MODEL_PATH" not in values:
        print("MODEL_PATH not set: login and Comparison work; De-identify needs the model.")
    print(
        "Start the API with:\n"
        "  uv run uvicorn clinical_deid.api.app:app --reload --port 8000 --env-file .env"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
