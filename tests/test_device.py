import json

import pytest
from typer.testing import CliRunner

from stemlab import bootstrap
from stemlab.backends import device
from stemlab.cli import app

runner = CliRunner()


def test_doctor_reports_the_system(home):
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    info = json.loads(result.output)
    assert info["flavor"] in device.FLAVORS
    assert info["python"].startswith("3.")
    assert set(info["backends"]) == {"msst", "demucs", "onnx"}
    assert info["home"] == str(home)


def test_doctor_prints_a_table(home):
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "Torch flavor" in result.output


def test_flavor_can_be_overridden_and_reset(home):
    assert runner.invoke(app, ["doctor", "--set-flavor", "cpu"]).exit_code == 0
    assert device.chosen_flavor() == ("cpu", "override")
    assert runner.invoke(app, ["doctor", "--set-flavor", "auto"]).exit_code == 0
    assert device.chosen_flavor()[1] == "detected"
    assert runner.invoke(app, ["doctor", "--set-flavor", "vulkan"]).exit_code == 2


def test_detection_order(monkeypatch):
    device.detect_gpu.cache_clear()
    monkeypatch.setattr(device.shutil, "which", lambda name: "/bin/nvidia-smi" if name == "nvidia-smi" else None)
    monkeypatch.setattr(device, "_run", lambda command, timeout=15: "GeForce RTX 3060, 12288\n")
    assert device.detect_gpu() == ("cuda", "GeForce RTX 3060", 12288)

    device.detect_gpu.cache_clear()
    monkeypatch.setattr(device.shutil, "which", lambda name: "/bin/rocminfo" if name == "rocminfo" else None)
    monkeypatch.setattr(device.sys, "platform", "linux")
    assert device.detect_gpu()[0] == "rocm"

    device.detect_gpu.cache_clear()
    monkeypatch.setattr(device.shutil, "which", lambda name: None)
    monkeypatch.setattr(device.sys, "platform", "darwin")
    monkeypatch.setattr(device.platform, "machine", lambda: "arm64")
    assert device.detect_gpu()[0] == "mps"

    device.detect_gpu.cache_clear()
    monkeypatch.setattr(device.platform, "machine", lambda: "x86_64")
    assert device.detect_gpu() == ("cpu", None, None)
    device.detect_gpu.cache_clear()


def test_device_defaults_follow_the_handoff_table():
    assert device.device_defaults("cuda", 24000) == {
        "dtype": "fp16",
        "chunk_size": 352800,
        "overlap": 4,
        "batch_size": 4,
    }
    assert device.device_defaults("cuda", 8192)["batch_size"] == 1
    assert device.device_defaults("mps")["dtype"] == "fp32"
    assert device.device_defaults("cpu")["chunk_size"] == 176400


def test_dtype_resolution():
    assert device.resolve_dtype("auto", "cuda") == "fp16"
    assert device.resolve_dtype("auto", "mps") == "fp32"
    assert device.resolve_dtype("auto", "cpu") == "fp32"
    assert device.resolve_dtype("fp32", "cuda") == "fp32"
    with pytest.raises(ValueError):
        device.resolve_dtype("fp8", "cuda")


def test_bootstrap_plan_picks_one_torch_index_and_one_onnxruntime(monkeypatch):
    cuda = bootstrap.plan("cuda")
    assert cuda[0][-2:] == ["--index-url", device.TORCH_INDEX["cuda"]]
    assert cuda[-1][-1].startswith("onnxruntime-gpu") and "<1.24" in cuda[-1][-1], "must match torch's CUDA 12"

    monkeypatch.setattr(bootstrap.sys, "platform", "darwin")
    mps = bootstrap.plan("mps")
    assert "--index-url" not in mps[0]
    assert mps[-1][-1] == "onnxruntime"

    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    assert bootstrap.plan("cpu")[-1][-1] == "onnxruntime-directml"
    # torch is never bundled with the other packages, so its index applies to it alone
    assert not any("torch" in arg and arg.startswith("torch") for arg in cuda[1])
    with pytest.raises(ValueError):
        bootstrap.plan("vulkan")


def test_bootstrap_dry_run_prints_the_exact_commands(home):
    result = runner.invoke(app, ["bootstrap", "--flavor", "cpu", "--dry-run"])
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert len(lines) == 3 and "whl/cpu" in lines[0]


STRIX_HALO = {"name": "AMD Radeon(TM) 8060S Graphics", "pci": "pci\\ven_1002&dev_1586", "memory": 32 * 1024**3}
UNKNOWN_AMD = {"name": "AMD Radeon(TM) Vega 8 Graphics", "pci": "pci\\ven_1002&dev_15d8", "memory": 2 * 1024**3}
INTEL = {"name": "Intel(R) UHD Graphics", "pci": "pci\\ven_8086&dev_9a49", "memory": 128 * 1024**2}


def _windows_with(monkeypatch, *adapters):
    device.detect_gpu.cache_clear()
    monkeypatch.setattr(device.shutil, "which", lambda name: None)
    monkeypatch.setattr(device.sys, "platform", "win32")
    monkeypatch.setattr(device, "_windows_display_adapters", lambda: list(adapters))


def test_windows_amd_gpu_is_rocm_when_amd_builds_wheels_for_it(monkeypatch, home):
    _windows_with(monkeypatch, INTEL, STRIX_HALO)
    assert device.detect_gpu() == ("rocm", "AMD Radeon(TM) 8060S Graphics", 32768)
    assert device.rocm_target() == "gfx1151"
    assert device.torch_index("rocm") == device.ROCM_WINDOWS_INDEX

    # Other AMD GPUs keep torch on the CPU, but are still named
    _windows_with(monkeypatch, UNKNOWN_AMD)
    assert device.detect_gpu() == ("cpu", "AMD Radeon(TM) Vega 8 Graphics", 2048)
    assert device.rocm_target() is None

    _windows_with(monkeypatch, INTEL)
    assert device.detect_gpu() == ("cpu", None, None)
    device.detect_gpu.cache_clear()


def test_rocm_targets_cover_the_gpus_amd_lists():
    assert device.rocm_target_for("AMD Radeon(TM) 8060S Graphics") == "gfx1151"
    assert device.rocm_target_for("AMD Radeon 890M Graphics") == "gfx1150"
    assert device.rocm_target_for("AMD Radeon RX 7900 XTX") == "gfx1100"
    assert device.rocm_target_for("AMD Radeon RX 7800 XT") == "gfx1101"
    assert device.rocm_target_for("AMD Radeon RX 7700S") == "gfx1102"
    assert device.rocm_target_for("AMD Radeon RX 9070 XT") == "gfx1201"
    assert device.rocm_target_for("AMD Radeon RX 9060 XT") == "gfx1200"
    assert device.rocm_target_for("AMD Radeon RX 6800 XT") is None


def test_rocm_target_can_be_overridden(monkeypatch, home):
    _windows_with(monkeypatch, UNKNOWN_AMD)
    assert runner.invoke(app, ["doctor", "--set-rocm-target", "gfx1100"]).exit_code == 0
    assert device.rocm_target() == "gfx1100"
    assert runner.invoke(app, ["doctor", "--set-rocm-target", "navi"]).exit_code == 2
    assert runner.invoke(app, ["doctor", "--set-rocm-target", "auto"]).exit_code == 0
    assert device.rocm_target() is None
    device.detect_gpu.cache_clear()


def test_bootstrap_plan_for_rocm_on_windows_uses_amd_wheels(monkeypatch, home):
    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.setattr(device.sys, "platform", "win32")
    monkeypatch.setattr(device, "rocm_target", lambda: "gfx1151")
    commands = bootstrap.plan("rocm")
    assert commands[0][-4:] == [
        "torch[device-gfx1151]>=2.6,<2.15",
        "torchaudio",
        "--index-url",
        device.ROCM_WINDOWS_INDEX,
    ]
    assert "--reinstall-package" in commands[0] or "--force-reinstall" in commands[0]
    assert commands[-1][-1] == "onnxruntime-directml", "no onnxruntime ROCm build exists for Windows"

    monkeypatch.setattr(device, "rocm_target", lambda: None)
    with pytest.raises(ValueError, match="set-rocm-target"):
        bootstrap.plan("rocm")

    # Linux keeps the pytorch.org build
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setattr(device.sys, "platform", "linux")
    assert bootstrap.plan("rocm")[0][-2:] == ["--index-url", device.TORCH_INDEX["rocm"]]


def test_packaged_app_overrides(monkeypatch, tmp_path, home):
    # The packaged app installs the engine as a wheel and ships recipes, MSST and
    # the UI in a folder it names in STEMLAB_ROOT; bootstrap uses its uv
    import importlib

    from stemlab import paths

    monkeypatch.setenv("STEMLAB_ROOT", str(tmp_path / "engine"))
    importlib.reload(paths)
    assert paths.REPO_ROOT == tmp_path / "engine"
    assert paths.MSST_DIR == tmp_path / "engine" / "third_party" / "msst"
    monkeypatch.delenv("STEMLAB_ROOT")
    importlib.reload(paths)
    assert (paths.REPO_ROOT / "pyproject.toml").is_file()

    monkeypatch.setenv("STEMLAB_UV", str(tmp_path / "uv.exe"))
    assert bootstrap.installer()[:3] == [str(tmp_path / "uv.exe"), "pip", "install"]
