import sys

import pytest

from core import envs, paths
from core.envs import BackendEnv, EnvError


def fake_install(env):
    """Make an environment look installed without creating a real one."""
    env.python.parent.mkdir(parents=True, exist_ok=True)
    env.python.write_text("")
    env.mark_installed(package="example==1.0")


def test_environment_lives_in_app_data_dir():
    env = BackendEnv("unit_location")
    assert env.path == paths.envs_dir() / "unit_location"
    assert paths.app_data_dir() in env.path.parents


def test_install_marker_controls_installed_state():
    env = BackendEnv("unit_marker")
    assert not env.is_installed()
    assert env.info() == {}

    fake_install(env)
    assert env.is_installed()
    assert env.info()["package"] == "example==1.0"
    assert env.info()["backend"] == "unit_marker"

    assert env.remove()
    assert not env.exists()
    assert not env.is_installed()


def test_interrupted_install_is_not_installed():
    """An environment without marker (installation did not finish) does not count."""
    env = BackendEnv("unit_partial")
    env.python.parent.mkdir(parents=True, exist_ok=True)
    env.python.write_text("")
    assert env.exists()
    assert not env.is_installed()
    env.remove()


def test_changed_recipe_requires_reinstall():
    fake_install(BackendEnv("unit_recipe", recipe=1))
    assert BackendEnv("unit_recipe", recipe=1).is_installed()
    assert not BackendEnv("unit_recipe", recipe=2).is_installed()
    BackendEnv("unit_recipe").remove()


def test_corrupt_marker_is_not_installed():
    env = BackendEnv("unit_corrupt")
    fake_install(env)
    env.marker.write_text("{not json")
    assert env.info() == {}
    assert not env.is_installed()
    env.remove()


def test_venv_command_uses_running_interpreter_when_supported():
    current = sys.version_info[:2]
    command = BackendEnv("unit_venv", python_versions=(current,))._venv_command()
    assert command[-3:-1] == ["-m", "venv"]
    assert command[-1].endswith("unit_venv")


def test_venv_command_reports_missing_python(monkeypatch):
    monkeypatch.setattr(envs, "_interpreter_version", lambda command: (2, 7))
    monkeypatch.setattr(envs.shutil, "which", lambda name: None)
    with pytest.raises(EnvError, match="needs Python 3.10"):
        BackendEnv("unit_missing", python_versions=((3, 10),))._venv_command()


def test_venv_command_falls_back_to_uv(monkeypatch):
    monkeypatch.setattr(envs, "_interpreter_version", lambda command: (2, 7))
    monkeypatch.setattr(envs.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    command = BackendEnv("unit_uv", python_versions=((3, 10),))._venv_command()
    assert command[:2] == ["/usr/bin/uv", "venv"]
    assert "3.10" in command


def test_torch_build_matches_hardware(monkeypatch):
    monkeypatch.setattr(envs, "IS_MACOS", False)
    monkeypatch.setattr(envs, "has_nvidia_gpu", lambda: True)
    assert envs.torch_install_args()[-1] == envs.TORCH_CUDA_INDEX
    monkeypatch.setattr(envs, "has_nvidia_gpu", lambda: False)
    assert envs.torch_install_args()[-1] == envs.TORCH_CPU_INDEX
    monkeypatch.setattr(envs, "IS_MACOS", True)
    assert envs.torch_install_args() is None


def test_subprocess_env_is_isolated(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    env = BackendEnv("unit_env").subprocess_env({"EXTRA": 1})
    assert "PYTHONPATH" not in env and "VIRTUAL_ENV" not in env
    assert env["EXTRA"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_create_and_run_real_environment():
    """Creating an environment and running its Python works end to end."""
    current = sys.version_info[:2]
    env = BackendEnv("unit_real", python_versions=(current,))
    lines = []
    try:
        env.remove()
        command = env._venv_command()
        env._run(command, lines.append, None, "create the environment")
        assert env.python.exists()
        env.run_python(["-c", "import sys; print('prefix', sys.prefix)"], lines.append)
        assert any(line.startswith("prefix") and "unit_real" in line for line in lines)
        with pytest.raises(EnvError, match="exit code 7"):
            env.run_python(["-c", "raise SystemExit(7)"], lines.append)
    finally:
        assert env.remove()


def test_path_helpers(tmp_path):
    assert paths.safe_name('a<b>:"c"/d\\e|f?g*h') == "a_b___c__d_e_f_g_h"
    assert paths.safe_name("trailing dot. ") == "trailing dot"
    assert paths.safe_name("   ") == "audio"
    assert paths.format_size(512) == "512 B"
    assert paths.format_size(5 * 1024 ** 3) == "5.0 GB"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "file.bin").write_bytes(b"x" * 1000)
    assert paths.dir_size(tmp_path) == 1000
    assert paths.remove_tree(tmp_path / "sub")
    assert paths.remove_tree(tmp_path / "does-not-exist")


def test_only_sessions_of_dead_processes_are_cleaned():
    import os
    import subprocess

    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    assert paths.process_alive(os.getpid())
    assert not paths.process_alive(finished.pid)
    assert not paths.process_alive(0)

    root = paths.temp_root()
    mine = paths.new_session_dir()
    stale = root / f"{paths.SESSION_PREFIX}{finished.pid}_crashed"
    stale.mkdir()
    (stale / "stems.wav").write_bytes(b"x")
    unrelated = root / "not-a-session"
    unrelated.mkdir(exist_ok=True)
    try:
        assert paths.clean_stale_sessions() >= 1
        assert not stale.exists()
        assert mine.exists(), "the session of a running process must be kept"
        assert unrelated.exists()
    finally:
        paths.remove_tree(mine)
        paths.remove_tree(unrelated)
