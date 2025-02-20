import pytest
from environs import EnvError

from hooks_lib.env import Env


def test_env_action_default() -> None:
    assert Env.ACTION == "apply"


def test_env_action(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTION", "fake")
    assert Env.ACTION == "fake"


def test_env_dry_run_default() -> None:
    with pytest.raises(EnvError):
        assert Env.DRY_RUN


def test_env_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRY_RUN", "false")
    assert not Env.DRY_RUN


def test_env_log_level_default() -> None:
    assert Env.LOG_LEVEL == "INFO"


def test_env_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert Env.LOG_LEVEL == "debug"


def test_env_outputs_file_default() -> None:
    with pytest.raises(EnvError):
        assert Env.OUTPUTS_FILE


def test_env_outputs_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTPUTS_FILE", "fake")
    assert Env.OUTPUTS_FILE == "fake"


def test_env_plan_file_json_default() -> None:
    with pytest.raises(EnvError):
        assert Env.PLAN_FILE_JSON


def test_env_plan_file_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLAN_FILE_JSON", "fake")
    assert Env.PLAN_FILE_JSON == "fake"


def test_env_terraform_cmd_default() -> None:
    with pytest.raises(EnvError):
        assert Env.TERRAFORM_CMD


def test_env_terraform_cmd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERRAFORM_CMD", "fake")
    assert Env.TERRAFORM_CMD == "fake"


def test_env_tf_vars_file_default() -> None:
    with pytest.raises(EnvError):
        assert Env.TF_VARS_FILE


def test_env_tf_vars_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TF_VARS_FILE", "fake")
    assert Env.TF_VARS_FILE == "fake"


def test_env_unknownt() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        assert Env.WHATEVER
