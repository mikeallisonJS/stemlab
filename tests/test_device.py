import json

import pytest
from typer.testing import CliRunner

from captainstems import bootstrap
from captainstems.backends import device
from captainstems.cli import app

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
