"""
Tests that run real models.

They need the bootstrapped backends (`stemlab bootstrap`) and model
weights, which are fetched into the real registry on first use. Without torch
they are skipped. Run only these with: pytest -m models
"""

import time

import numpy as np
import pytest
import soundfile as sf

from stemlab import audio, recipe, runner
from stemlab.registry import Registry, load_curated

pytestmark = pytest.mark.models

torch = pytest.importorskip("torch", reason="run `stemlab bootstrap` first")


def model(real_home, model_id):
    """A curated model, downloaded when missing."""
    registry = Registry()
    if not registry.has(model_id):
        if model_id not in load_curated():
            pytest.skip(f"{model_id} is not installed")
        try:
            registry.fetch(model_id)
        except OSError as e:
            pytest.skip(f"cannot download {model_id}: {e}")
    return registry


def stems_add_up(out, names, clip, tolerance_db=-20.0):
    mix, _ = audio.load(clip)
    total = sum(sf.read(str(out / f"clip-5s_{name}.wav"), dtype="float32", always_2d=True)[0].T for name in names)
    residual = mix - total
    level = 10 * np.log10(np.mean(residual**2) / np.mean(mix**2))
    assert level < tolerance_db, f"stems are {level:.1f} dB away from the mix"


def test_two_node_recipe_with_the_smallest_demucs_model_on_cpu(real_home, clip, tmp_path):
    """Phase 1 acceptance: separate -> export on the 5 second fixture, CPU, under 60 seconds."""
    registry = model(real_home, "htdemucs")
    text = """
name: acceptance
nodes:
  split: {op: separate, model: htdemucs, params: {device: cpu}}
  out: {op: export, inputs: [split.vocals, split.drums, split.bass, split.other], params: {format: wav, bit_depth: 32}}
"""
    started = time.time()
    record = runner.run_recipe(recipe.loads(text), clip, tmp_path / "out", registry=registry, use_cache=False)
    elapsed = time.time() - started
    assert elapsed < 60, f"took {elapsed:.1f} s"
    assert record["nodes"]["split"]["params"]["device"] == "cpu"
    assert len(record["models"]["htdemucs"]["sha256"]) == 64
    assert record["backends"]["demucs"]["demucs"]
    stems_add_up(tmp_path / "out", ["vocals", "drums", "bass", "other"], clip)

    # Same recipe again: served from the cache
    again = runner.run_recipe(recipe.loads(text), clip, tmp_path / "again", registry=registry)
    assert again["nodes"]["split"]["cached"] is True
    assert again["nodes"]["split"]["cache_key"] == record["nodes"]["split"]["cache_key"]


def test_demucs_shifts_and_progress(real_home, clip, tmp_path):
    registry = model(real_home, "htdemucs")
    text = """
nodes:
  split: {op: separate, model: htdemucs, targets: [vocals], params: {shifts: 2, overlap: 0.5}}
"""
    events = []
    runner.run_recipe(
        recipe.loads(text), clip, tmp_path / "out", registry=registry, use_cache=False, events=events.append
    )
    fractions = [event["fraction"] for event in events if event["type"] == "node_progress"]
    assert fractions and fractions == sorted(fractions) and fractions[-1] == 1.0


@pytest.mark.gpu
def test_mel_band_roformer_runs_on_the_gpu(real_home, clip, tmp_path):
    if not torch.cuda.is_available():
        pytest.skip("no CUDA device")
    registry = model(real_home, "mel-band-roformer-vocals-kim")
    text = """
nodes:
  vox: {op: separate, model: mel-band-roformer-vocals-kim, targets: [vocals]}
  inst: {op: subtract, inputs: {a: mix, b: vox.vocals}}
  out: {op: export, inputs: {vocals: vox.vocals, inst: inst.out}, params: {format: wav, bit_depth: 32}}
"""
    record = runner.run_recipe(recipe.loads(text), clip, tmp_path / "out", registry=registry, use_cache=False)
    params = record["nodes"]["vox"]["params"]
    assert params["device"] == "cuda" and params["dtype"] == "fp16"
    assert params["chunk_size"] == 352800, "taken from the model's config"
    assert record["backends"]["msst"]["msst"] != "unknown"
    stems_add_up(tmp_path / "out", ["vocals", "inst"], clip, tolerance_db=-90.0)


@pytest.mark.gpu
def test_msst_knobs_change_the_work_done(real_home, clip, tmp_path):
    if not torch.cuda.is_available():
        pytest.skip("no CUDA device")
    registry = model(real_home, "scnet-large")
    text = """
nodes:
  split: {op: separate, model: scnet-large, params: PARAMS}
  out: {op: export, inputs: [split.drums], params: {format: wav, bit_depth: 32}}
"""
    plain = runner.run_recipe(
        recipe.loads(text.replace("PARAMS", "{}")), clip, tmp_path / "a", registry=registry, use_cache=False
    )
    tuned = runner.run_recipe(
        recipe.loads(text.replace("PARAMS", "{tta: true, shifts: 2, overlap: 2, batch_size: 1, dtype: fp32}")),
        clip,
        tmp_path / "b",
        registry=registry,
        use_cache=False,
    )
    assert plain["nodes"]["split"]["cache_key"] != tuned["nodes"]["split"]["cache_key"]
    a = sf.read(str(tmp_path / "a" / "clip-5s_drums.wav"), dtype="float32")[0]
    b = sf.read(str(tmp_path / "b" / "clip-5s_drums.wav"), dtype="float32")[0]
    assert a.shape == b.shape and np.isfinite(b).all()
    assert not np.array_equal(a, b), "different settings give a different result"
    assert np.corrcoef(a.ravel(), b.ravel())[0, 1] > 0.9, "but still the same stem"


def test_mdx_net_onnx_model(real_home, clip, tmp_path):
    pytest.importorskip("onnxruntime", reason="run `stemlab bootstrap` first")
    registry = model(real_home, "uvr-mdx-kim-vocal-2")
    text = """
nodes:
  vox: {op: separate, model: uvr-mdx-kim-vocal-2}
  inst: {op: subtract, inputs: {a: mix, b: vox.vocals}}
  out: {op: export, inputs: {vocals: vox.vocals, inst: inst.out}, params: {format: wav, bit_depth: 32}}
"""
    record = runner.run_recipe(recipe.loads(text), clip, tmp_path / "out", registry=registry, use_cache=False)
    params = record["nodes"]["vox"]["params"]
    assert params["compensate"] == 1.009, "taken from the manifest's onnx_params"
    assert params["device"] in ("cuda", "dml", "coreml", "cpu")
    assert record["backends"]["onnx"]["onnxruntime"]
    stems_add_up(tmp_path / "out", ["vocals", "inst"], clip, tolerance_db=-90.0)


@pytest.mark.parametrize("overlap, batch_size", [(1, 1), (1, 3), (2, 1), (4, 2)])
def test_msst_overlap_add_has_no_gaps(overlap, batch_size):
    """An identity network must hand back its input, also when chunks only touch (overlap 1)."""
    from stemlab.backends.msst import MsstModel, _import_upstream

    _, _, windowing = _import_upstream()
    model = MsstModel(lambda batch: batch.unsqueeze(1), {}, "scnet", "cpu", ["same"], 44100, windowing)
    signal = np.ones((2, 44100 * 3 + 1234), dtype=np.float32)
    out = model._demix(torch.from_numpy(signal), 44100, overlap, batch_size, False, lambda fraction: None, None)
    assert out.shape == (1, 2, signal.shape[1])
    assert np.allclose(out, 1.0, atol=1e-5), f"dropouts at {np.flatnonzero(np.abs(out[0, 0] - 1) > 1e-5)[:6]}"


def test_demucs_runs_are_repeatable(real_home, clip, tmp_path):
    """Demucs shifts the audio by a random amount; the seed in run.json pins it down."""
    registry = model(real_home, "htdemucs")
    text = """
nodes:
  split: {op: separate, model: htdemucs, targets: [vocals], params: {device: cpu, seed: SEED}}
  out: {op: export, inputs: [split.vocals], params: {format: wav, bit_depth: 32}}
"""

    def vocals(seed, folder):
        record = runner.run_recipe(
            recipe.loads(text.replace("SEED", str(seed))), clip, tmp_path / folder, registry=registry, use_cache=False
        )
        assert record["nodes"]["split"]["params"]["seed"] == seed
        return sf.read(str(tmp_path / folder / "clip-5s_vocals.wav"), dtype="float32")[0]

    first, second, other = vocals(0, "a"), vocals(0, "b"), vocals(7, "c")
    assert np.array_equal(first, second), "the same seed must give the same samples"
    assert not np.array_equal(first, other), "another seed shifts differently"
