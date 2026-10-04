from __future__ import annotations

from pathlib import Path

from gridform_core.data_workbench.state import resolve_data_workbench_root


def test_state_root_is_derived_from_application_state_not_current_directory(
    tmp_path: Path, monkeypatch
) -> None:
    application_state = tmp_path / "application-state"
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    resolved = resolve_data_workbench_root(application_state)

    assert resolved == application_state.resolve() / "data-workbench"
    assert not resolved.exists()
