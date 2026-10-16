import json
import os
from pathlib import Path
import stat

import pytest

from integration import runtime_config as config


KEY = "sk-synthetic-test-key-not-a-real-account"


def test_initialize_has_no_secret_and_is_repeatable(tmp_path):
    config.initialize(tmp_path)
    config.initialize(tmp_path)
    values = config.read_config(tmp_path)
    assert values == config.DEFAULTS
    status = config.status(tmp_path, {})
    assert not status["provider_key_present"] and not status["service_ready"]
    assert status["configured"]["BACKEND_BASE_URL"]
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / ".env.runtime").stat().st_mode) == 0o600


def test_secret_prompt_does_not_print_key_and_preserves_tokens(tmp_path, capsys):
    config.write_config({"AI_SERVICE_TOKEN": "existing-service-token", "BACKEND_TOOL_TOKEN": "existing-tool-token"}, tmp_path)
    replies = iter([KEY, KEY])
    config.set_key(tmp_path, prompt=lambda _: next(replies))
    values = config.read_config(tmp_path)
    assert values["DEEPSEEK_API_KEY"] == KEY
    assert values["AI_SERVICE_TOKEN"] == "existing-service-token"
    assert values["BACKEND_TOOL_TOKEN"] == "existing-tool-token"
    assert KEY not in capsys.readouterr().out
    public = json.dumps(config.status(tmp_path, {}))
    assert KEY not in public and "existing-service-token" not in public


@pytest.mark.parametrize("key", ["", "too-short", "sk-key\nINJECTED=value", "sk-key with a space"])
def test_invalid_key_does_not_change_existing_configuration(tmp_path, key):
    config.initialize(tmp_path)
    before = (tmp_path / ".env.runtime").read_bytes()
    with pytest.raises(config.ConfigError):
        config.set_key(tmp_path, prompt=lambda _: key)
    assert (tmp_path / ".env.runtime").read_bytes() == before


def test_mismatched_confirmation_preserves_saved_key(tmp_path):
    config.write_config({"DEEPSEEK_API_KEY": KEY}, tmp_path)
    before = (tmp_path / ".env.runtime").read_bytes()
    replies = iter(["sk-another-synthetic-valid-length-key", KEY])
    with pytest.raises(config.ConfigError):
        config.set_key(tmp_path, prompt=lambda _: next(replies))
    assert (tmp_path / ".env.runtime").read_bytes() == before


def test_file_is_read_as_data_not_shell_code(tmp_path):
    config.write_config({"DEEPSEEK_API_KEY": KEY, "OTHER": "$(touch do-not-create)"}, tmp_path)
    assert config.read_config(tmp_path)["OTHER"] == "$(touch do-not-create)"
    assert not (tmp_path / "do-not-create").exists()


@pytest.mark.parametrize("text", ["BAD LINE\n", "P3_ENGINE=deepseek\nP3_ENGINE=rules\n", "KEY='unclosed\n"])
def test_invalid_existing_config_is_not_overwritten(tmp_path, text):
    path = tmp_path / ".env.runtime"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.initialize(tmp_path)
    assert path.read_text(encoding="utf-8") == text


def test_existing_key_is_preserved_and_deepseek_enabled(tmp_path):
    config.write_config({"DEEPSEEK_API_KEY": KEY, "P3_ENGINE": "rules"}, tmp_path)
    config.initialize(tmp_path)
    assert config.read_config(tmp_path)["DEEPSEEK_API_KEY"] == KEY
    assert config.read_config(tmp_path)["P3_ENGINE"] == "deepseek"


def test_loader_keeps_deployment_auth_and_container_backend_address(tmp_path):
    config.initialize(tmp_path)
    inherited = {"DEEPSEEK_API_KEY": KEY, "AI_SERVICE_TOKEN": "service", "BACKEND_TOOL_TOKEN": "tool",
                 "BACKEND_BASE_URL": "http://backend:8000", "P3_ENGINE": "rules"}
    env = config.environment(tmp_path, inherited)
    assert env["DEEPSEEK_API_KEY"] == KEY
    assert env["BACKEND_BASE_URL"] == "http://backend:8000"
    assert env["AI_SERVICE_TOKEN"] == "service" and env["BACKEND_TOOL_TOKEN"] == "tool"
    assert env["P3_ENGINE"] == "deepseek"


def test_missing_backend_tokens_refuses_to_start(tmp_path):
    config.write_config({**config.DEFAULTS, "DEEPSEEK_API_KEY": KEY}, tmp_path)
    executed = []
    with pytest.raises(config.ConfigError) as error:
        config.run_service(tmp_path, {}, execute=lambda *args: executed.append(args))
    assert "AI_SERVICE_TOKEN" in str(error.value) and "BACKEND_TOOL_TOKEN" in str(error.value)
    assert executed == []


def test_launch_uses_only_environment_for_secrets_and_local_listener(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config.write_config({**config.DEFAULTS, "DEEPSEEK_API_KEY": KEY}, tmp_path)
    executed = []
    config.run_service(tmp_path, {"AI_SERVICE_TOKEN": "service", "BACKEND_TOOL_TOKEN": "tool"},
                       execute=lambda *args: executed.append(args))
    executable, argv, env = executed[0]
    assert KEY not in " ".join(argv) and env["DEEPSEEK_API_KEY"] == KEY
    assert "127.0.0.1" in argv and "v1.app:create_app" in argv
    assert env["BACKEND_BASE_URL"] == "http://127.0.0.1:8000"


def test_symlink_target_is_never_followed(tmp_path):
    target = tmp_path / "untouched"
    target.write_text("leave unchanged", encoding="utf-8")
    try:
        (tmp_path / ".env.runtime").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable on this test account")
    with pytest.raises(config.ConfigError):
        config.initialize(tmp_path)
    assert target.read_text(encoding="utf-8") == "leave unchanged"


def test_noninteractive_input_is_rejected_before_requesting_a_key(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(config.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(config.ConfigError):
        config.set_key(tmp_path)
    assert not (tmp_path / ".env.runtime").exists()


def test_echoing_getpass_fallback_is_never_allowed(tmp_path, monkeypatch):
    import warnings
    from types import SimpleNamespace
    monkeypatch.setattr(config.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    def unavailable(message):
        warnings.warn("Input cannot be hidden", config.getpass.GetPassWarning)
        raise AssertionError("Echo fallback must never be reached")

    monkeypatch.setattr(config.getpass, "getpass", unavailable)
    with pytest.raises(config.ConfigError):
        config.set_key(tmp_path)
    assert not (tmp_path / ".env.runtime").exists()
