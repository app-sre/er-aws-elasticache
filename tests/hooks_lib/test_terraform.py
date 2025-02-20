from subprocess import CalledProcessError  # noqa: S404

import pytest

from hooks_lib.terraform import tf_run


def test_terraform_tf_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERRAFORM_CMD", "echo")
    monkeypatch.setenv("DRY_RUN", "0")
    assert tf_run(["foo bar"]) == "foo bar\n"
    assert tf_run(["version"], dry_run=True) == ""  # noqa: PLC1901


def test_terraform_tf_run_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TERRAFORM_CMD", "ls")
    with pytest.raises(CalledProcessError):
        tf_run(["what ever - will throw an error"], dry_run=False)
