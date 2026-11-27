"""scripts/make_env.py: writes the demo login secrets into a local .env (T4.2)."""

import importlib.util
from pathlib import Path

import pytest
from argon2 import PasswordHasher
from dotenv import dotenv_values

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_env.py"
spec = importlib.util.spec_from_file_location("make_env", SCRIPT)
make_env = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_env)

PASSWORD = "contraseña-de-prueba-123"  # noqa: S105 - made-up test credential
OLD_SECRET = "old"  # noqa: S105 - made-up test value


@pytest.fixture
def typed_password(monkeypatch):
    monkeypatch.setattr(make_env.getpass, "getpass", lambda prompt="": PASSWORD)


def test_render_env_replaces_keys_and_keeps_everything_else():
    template = "# Demo\nMAX_CHARACTERS=10000\nDEMO_PASSWORD_HASH=\nSESSION_SECRET=old\n"

    values = {"DEMO_PASSWORD_HASH": "$argon2id$x", "SESSION_SECRET": "s"}

    text = make_env.render_env(template, values)

    assert text == (
        "# Demo\nMAX_CHARACTERS=10000\nDEMO_PASSWORD_HASH='$argon2id$x'\nSESSION_SECRET='s'\n"
    )


def test_render_env_appends_missing_keys():
    text = make_env.render_env("LLM_ENABLED=false", {"SESSION_SECRET": "s"})

    assert text == "LLM_ENABLED=false\n\nSESSION_SECRET='s'\n"


def test_new_env_file_is_readable_by_dotenv_and_matches_the_password(tmp_path, typed_password):
    (tmp_path / ".env.example").write_text("LLM_ENABLED=false\nDEMO_PASSWORD_HASH=\n", "utf-8")
    env_file = tmp_path / ".env"

    assert make_env.main(["--env-file", str(env_file)]) == 0

    values = dotenv_values(env_file)
    assert values["LLM_ENABLED"] == "false"
    assert values["DEMO_USERNAME"] == "demo"
    assert PasswordHasher().verify(values["DEMO_PASSWORD_HASH"], PASSWORD)
    assert len(values["SESSION_SECRET"]) >= 32
    assert not env_file.read_bytes().startswith(b"\xef\xbb\xbf")
    assert PASSWORD not in env_file.read_text("utf-8")


def test_existing_utf16_env_is_backed_up_and_rewritten_as_utf8(tmp_path, typed_password):
    env_file = tmp_path / ".env"
    env_file.write_text("MAX_CHARACTERS=5000\nSESSION_SECRET=old\n", encoding="utf-16")

    assert make_env.main(["--env-file", str(env_file)]) == 0

    assert (tmp_path / ".env.bak").exists()
    values = dotenv_values(env_file)
    assert values["MAX_CHARACTERS"] == "5000"
    assert values["SESSION_SECRET"] != OLD_SECRET


def test_model_path_is_written_when_the_folder_exists(tmp_path, typed_password):
    model = tmp_path / "model"
    model.mkdir()
    env_file = tmp_path / ".env"

    assert make_env.main(["--env-file", str(env_file), "--model-path", str(model)]) == 0

    assert dotenv_values(env_file)["MODEL_PATH"] == str(model.resolve())


def test_missing_model_folder_writes_nothing(tmp_path, typed_password):
    env_file = tmp_path / ".env"

    assert make_env.main(["--env-file", str(env_file), "--model-path", str(tmp_path / "x")]) == 1
    assert not env_file.exists()


def test_short_or_mismatched_password_writes_nothing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(make_env.getpass, "getpass", lambda prompt="": "corta")

    assert make_env.main(["--env-file", str(env_file)]) == 1
    assert not env_file.exists()

    answers = iter([PASSWORD, PASSWORD + "x"])
    monkeypatch.setattr(make_env.getpass, "getpass", lambda prompt="": next(answers))

    assert make_env.main(["--env-file", str(env_file)]) == 1
    assert not env_file.exists()
