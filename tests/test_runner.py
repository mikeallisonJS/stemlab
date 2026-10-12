import json
import threading

import numpy as np
import pytest
import soundfile as sf
from conftest import add_fake_model, write_tone

from captainstems import audio, recipe, runner
from captainstems.backends.base import Cancelled
from captainstems.recipe import RecipeError

SEPARATE_EXPORT = """
name: two-node
nodes:
  split: {op: separate, model: two-stem}
  out: {op: export, inputs: [split.vocals, split.other]}
"""

VOCALS_INSTRUMENTAL = """
name: vox-inst
nodes:
  vox: {op: separate, model: vocal-model, targets: [vocals]}
  inst: {op: subtract, inputs: {a: mix, b: vox.vocals}}
  check: {op: analyze, inputs: {stems: [vox.vocals, inst.out]}}
  out: {op: export, inputs: {vocals: vox.vocals, instrumental: inst.out}}
"""


def run(text, clip, tmp_path, registry, **kwargs):
    events = []
    record = runner.run_recipe(
        recipe.loads(text), clip, tmp_path / "out", registry=registry, events=events.append, **kwargs
    )
    return record, events


def read(path):
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return data.T, rate


# The basics ------------------------------------------------------------------------


def test_separate_then_export_writes_stems_and_run_json(clip, tmp_path, registry):
    record, events = run(SEPARATE_EXPORT, clip, tmp_path, registry)
    out = tmp_path / "out"
    assert sorted(path.name for path in out.iterdir()) == ["clip-5s_other.flac", "clip-5s_vocals.flac", "run.json"]

    mix, rate = audio.load(clip)
    vocals, vocals_rate = read(out / "clip-5s_vocals.flac")
    assert vocals_rate == rate and vocals.shape == mix.shape
    assert sf.info(str(out / "clip-5s_vocals.flac")).subtype == "PCM_24"

    assert record == json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert record["status"] == "finished"
    assert [output["stem"] for output in record["outputs"]] == ["vocals", "other"]
    assert [event["type"] for event in events][0] == "run_started"
    assert [event["type"] for event in events][-1] == "run_finished"
    assert not list(out.glob(".staging-*"))


def test_run_json_records_what_is_needed_to_reproduce(clip, tmp_path, registry, fake_backend):
    record, _ = run(SEPARATE_EXPORT, clip, tmp_path, registry)
    assert record["input"]["sha256"] == audio.file_sha256(clip)
    assert record["input"]["sample_rate"] == 44100
    model = record["models"]["two-stem"]
    assert model["sha256"] == registry.get("two-stem").sha256()
    assert set(model["files"]) == {"config.yaml", "model.ckpt"}
    assert record["backends"] == {"msst": {"fake": "1.0"}}

    node = record["nodes"]["split"]
    # Fully resolved: every knob the backend has, with the device chosen
    assert set(node["params"]) == set(fake_backend.supported_params)
    assert node["params"]["device"] == "cpu" and node["params"]["dtype"] == "fp32"
    assert node["params"] == fake_backend.calls[0]["params"]
    assert record["recipe"]["nodes"]["split"]["model"] == "two-stem"


def test_progress_and_node_events(clip, tmp_path, registry):
    _, events = run(VOCALS_INSTRUMENTAL, clip, tmp_path, registry)
    started = [event["node"] for event in events if event["type"] == "node_started"]
    finished = [event["node"] for event in events if event["type"] == "node_finished"]
    assert started == finished == ["vox", "inst", "check", "out"]
    fractions = [event["fraction"] for event in events if event["type"] == "node_progress" and event["node"] == "vox"]
    assert fractions and fractions == sorted(fractions) and fractions[-1] == 1.0
    assert all(event["run_id"] == events[0]["run_id"] for event in events)


# Graph operations -----------------------------------------------------------------


def test_subtract_gives_a_sample_exact_complement(clip, tmp_path, registry):
    record, _ = run(
        VOCALS_INSTRUMENTAL.replace(
            "{vocals: vox.vocals, instrumental: inst.out}", "{vocals: vox.vocals, instrumental: inst.out}"
        ).replace("op: export,", "op: export, params: {format: wav, bit_depth: 32},"),
        clip,
        tmp_path,
        registry,
    )
    mix, _ = audio.load(clip)
    vocals, _ = read(tmp_path / "out" / "clip-5s_vocals.wav")
    instrumental, _ = read(tmp_path / "out" / "clip-5s_instrumental.wav")
    assert np.array_equal(vocals + instrumental, mix), "the two stems must add up to the mix exactly"
    metrics = record["nodes"]["check"]["info"]["metrics"]
    assert metrics["residual_rms_db"] == -120.0


def test_subtracting_the_mix_from_itself_is_silence(clip, tmp_path, registry):
    text = """
nodes:
  nothing: {op: subtract, inputs: {a: mix, b: mix}}
  out: {op: export, inputs: [nothing.out], params: {format: wav, bit_depth: 32}}
"""
    run(text, clip, tmp_path, registry)
    silence, _ = read(tmp_path / "out" / "clip-5s_nothing.wav")
    assert silence.shape[-1] == 5 * 44100
    assert not silence.any()


def test_subtract_gain(clip, tmp_path, registry):
    text = """
nodes:
  half: {op: subtract, inputs: {a: mix, b: mix}, params: {gain_b: 0.5}}
  out: {op: export, inputs: [half.out], params: {format: wav, bit_depth: 32}}
"""
    run(text, clip, tmp_path, registry)
    half, _ = read(tmp_path / "out" / "clip-5s_half.wav")
    mix, _ = audio.load(clip)
    assert np.allclose(half, mix * 0.5, atol=1e-7)


@pytest.mark.parametrize("method", ["avg", "median", "max_spec", "min_spec"])
def test_ensemble_methods(method, clip, tmp_path, registry):
    text = f"""
nodes:
  a: {{op: separate, model: two-stem, targets: [vocals]}}
  b: {{op: separate, model: four-stem, targets: [vocals]}}
  both: {{op: ensemble, inputs: [a.vocals, b.vocals], params: {{method: {method}}}}}
  out: {{op: export, inputs: [both.out], params: {{format: wav, bit_depth: 32}}}}
"""
    run(text, clip, tmp_path, registry)
    combined, _ = read(tmp_path / "out" / "clip-5s_both.wav")
    mix, _ = audio.load(clip)
    assert combined.shape == mix.shape, "the ensemble keeps the length of its inputs"
    assert np.isfinite(combined).all()
    # Both inputs are mix * 0.5, so every method must return that
    assert np.allclose(combined, mix * 0.5, atol=2e-3)


def test_ensemble_weights(clip, tmp_path, registry):
    text = """
nodes:
  a: {op: separate, model: four-stem, targets: [vocals, drums]}
  both: {op: ensemble, inputs: [a.vocals, a.drums], params: {weights: [3, 1]}}
  out: {op: export, inputs: [both.out], params: {format: wav, bit_depth: 32}}
"""
    run(text, clip, tmp_path, registry)
    combined, _ = read(tmp_path / "out" / "clip-5s_both.wav")
    mix, _ = audio.load(clip)
    assert np.allclose(combined, mix * (0.75 * 0.5 + 0.25 * 0.25), atol=1e-6)


def test_postprocess_keeps_one_stem(clip, tmp_path, registry, fake_backend):
    text = """
nodes:
  vox: {op: separate, model: vocal-model}
  dry: {op: postprocess, model: dereverb, inputs: {audio: vox.vocals}}
  out: {op: export, inputs: [dry.out]}
"""
    record, _ = run(text, clip, tmp_path, registry)
    assert record["nodes"]["dry"]["info"]["kept"] == "dry"
    assert (tmp_path / "out" / "clip-5s_dry.flac").is_file()
    assert fake_backend.loads == ["vocal-model", "dereverb"]


def test_analyze_reports_what_the_chain_lost(clip, tmp_path, registry):
    text = """
nodes:
  split: {op: separate, model: four-stem}
  check: {op: analyze, inputs: {stems: [split.vocals, split.drums]}}
"""
    record, _ = run(text, clip, tmp_path, registry)
    metrics = record["nodes"]["check"]["info"]["metrics"]
    # vocals (0.5) + drums (0.25) leave a quarter of the mix: -12 dB
    assert metrics["residual_vs_mix_db"] == pytest.approx(-12.04, abs=0.05)
    assert set(metrics["stems"]) == {"split.vocals", "split.drums"}
    residual, _ = read(record["nodes"]["check"]["stems"]["residual"])
    mix, _ = audio.load(clip)
    assert np.allclose(residual, mix * 0.25, atol=1e-6)
    assert record["outputs"] == [], "a recipe without export writes only run.json"


def test_analyze_scores_against_a_reference(clip, tmp_path, registry):
    reference = tmp_path / "reference.wav"
    mix, rate = audio.load(clip)
    audio.write(reference, mix * 0.5, rate, "wav", 32)
    text = f"""
nodes:
  vox: {{op: separate, model: vocal-model}}
  check: {{op: analyze, inputs: {{stems: [vox.vocals]}}, params: {{reference: '{reference.as_posix()}'}}}}
"""
    record, _ = run(text, clip, tmp_path, registry)
    assert record["nodes"]["check"]["info"]["metrics"]["si_sdr_db"] > 60


def test_export_options(clip, tmp_path, registry):
    text = """
name: opts
nodes:
  split: {op: separate, model: two-stem}
  out:
    op: export
    inputs: [split.vocals]
    params: {format: wav, bit_depth: 16, sample_rate: 22050, naming: "{recipe}/{node}-{stem} of {track}"}
"""
    record, _ = run(text, clip, tmp_path, registry)
    written = tmp_path / "out" / "opts_out-vocals of clip-5s.wav"
    assert written.is_file(), "path separators in a naming template cannot escape the output folder"
    info = sf.info(str(written))
    assert (info.samplerate, info.subtype) == (22050, "PCM_16")
    assert info.frames == pytest.approx(5 * 22050, abs=2)
    assert record["outputs"][0]["path"] == str(written)


# Parameters -----------------------------------------------------------------------


def test_parameter_layers_override_each_other_in_order(clip, tmp_path, registry, fake_backend):
    add_fake_model(registry, "tuned", ["vocals"], defaults={"overlap": 5, "shifts": 2})
    fake_backend.config_defaults = {"chunk_size": 485100}
    text = """
defaults: {shifts: 3, normalize: true, not_a_knob_of_this_backend: 1}
nodes:
  a: {op: separate, model: tuned, params: {shifts: 4}}
  b: {op: separate, model: tuned}
  c: {op: separate, model: two-stem}
"""
    record, _ = run(text, clip, tmp_path, registry)
    a, b, c = (record["nodes"][name]["params"] for name in "abc")
    assert a["shifts"] == 4, "the node's own params win"
    assert b["shifts"] == 3, "then the recipe defaults"
    assert a["overlap"] == b["overlap"] == 5, "then the manifest defaults"
    assert c["overlap"] == 3 and c["batch_size"] == 2, "then the device defaults"
    assert a["chunk_size"] == 485100, "the model's config sets the chunk size"
    assert a["normalize"] is True


def test_bad_parameters_name_the_node(clip, tmp_path, registry):
    def fails(params, match):
        text = f"nodes:\n  vox: {{op: separate, model: vocal-model, params: {params}}}\n"
        with pytest.raises(RecipeError, match=match):
            run(text, clip, tmp_path, registry)

    fails("{chunk: 1}", "node 'vox': 'chunk' is not a parameter of the msst backend")
    fails("{overlap: 99}", "node 'vox': overlap must be at most 32")
    fails("{overlap: 2.5}", "overlap must be a whole number")
    fails("{normalize: 1}", "normalize must be true or false")
    fails("{dtype: fp8}", "dtype must be one of")
    fails("{device: cuda}", "node 'vox': device 'cuda' was requested")


def test_models_and_stems_are_checked_before_anything_runs(clip, tmp_path, registry, fake_backend):
    def fails(text, match):
        with pytest.raises(RecipeError, match=match):
            run(text, clip, tmp_path, registry)

    fails("nodes:\n  a: {op: separate, model: missing}\n", "node 'a': Model 'missing' is not installed")
    fails("nodes:\n  a: {op: separate, model: two-stem, targets: [drums]}\n", r"has no stem \['drums'\]")
    fails(
        "nodes:\n  a: {op: separate, model: two-stem}\n  o: {op: export, inputs: [a.piano]}\n",
        r"'a' only emits \['vocals', 'other'\]",
    )
    fails("nodes:\n  a: {op: postprocess, model: dereverb, inputs: {audio: mix}, target: wet}\n", "has no stem 'wet'")
    assert fake_backend.calls == []
    assert not (tmp_path / "out").exists()


# Caching --------------------------------------------------------------------------


def test_rerunning_a_recipe_reuses_the_cache(clip, tmp_path, registry, fake_backend):
    first, _ = run(VOCALS_INSTRUMENTAL, clip, tmp_path, registry)
    second, events = run(VOCALS_INSTRUMENTAL, clip, tmp_path, registry)
    assert len(fake_backend.calls) == 1, "the model ran once"
    assert [first["nodes"][n]["cached"] for n in ("vox", "inst", "check")] == [False, False, False]
    assert [second["nodes"][n]["cached"] for n in ("vox", "inst", "check")] == [True, True, True]
    assert second["nodes"]["vox"]["cache_key"] == first["nodes"]["vox"]["cache_key"]
    assert second["nodes"]["check"]["info"]["metrics"] == first["nodes"]["check"]["info"]["metrics"]
    assert (tmp_path / "out" / "clip-5s_instrumental.flac").is_file()


def test_cache_follows_what_affects_the_result(clip, tmp_path, registry, fake_backend):
    run(SEPARATE_EXPORT, clip, tmp_path, registry)
    run(SEPARATE_EXPORT.replace("model: two-stem}", "model: two-stem, params: {shifts: 2}}"), clip, tmp_path, registry)
    assert len(fake_backend.calls) == 2, "a changed parameter is a different result"

    # Asking for fewer stems needs no new run: all of the model's stems are cached
    run(
        SEPARATE_EXPORT.replace("model: two-stem}", "model: two-stem, targets: [vocals]}").replace(
            "[split.vocals, split.other]", "[split.vocals]"
        ),
        clip,
        tmp_path,
        registry,
    )
    assert len(fake_backend.calls) == 2

    other = write_tone(tmp_path / "other.wav", seconds=1.0)
    runner.run_recipe(recipe.loads(SEPARATE_EXPORT), other, tmp_path / "out2", registry=registry)
    assert len(fake_backend.calls) == 3, "another input file is a different result"

    run(SEPARATE_EXPORT, clip, tmp_path, registry, use_cache=False)
    assert len(fake_backend.calls) == 4


def test_changed_weights_invalidate_the_cache(clip, tmp_path, registry, fake_backend):
    from captainstems.registry import Registry

    run(SEPARATE_EXPORT, clip, tmp_path, registry)
    folder = registry.get("two-stem").folder
    manifest = json.loads((folder / "manifest.json").read_text())
    (folder / "model.ckpt").write_bytes(b"retrained weights")
    del manifest["sha256"]
    (folder / "manifest.json").write_text(json.dumps(manifest))
    run(SEPARATE_EXPORT, clip, tmp_path, Registry())
    assert len(fake_backend.calls) == 2


def test_run_json_reproduces_the_run(clip, tmp_path, registry, fake_backend):
    record, _ = run(VOCALS_INSTRUMENTAL, clip, tmp_path, registry)
    pinned = runner.recipe_from_run(record)
    assert pinned.nodes["vox"].params == record["nodes"]["vox"]["params"]
    again = runner.run_recipe(pinned, clip, tmp_path / "again", registry=registry)
    assert again["nodes"]["vox"]["cache_key"] == record["nodes"]["vox"]["cache_key"]
    assert len(fake_backend.calls) == 1


# Cancelling and failing ------------------------------------------------------------


def test_cancel_mid_run_leaves_no_output_files(clip, tmp_path, registry, fake_backend):
    cancel = threading.Event()
    fake_backend.cancel_flag = cancel
    fake_backend.cancel_after = 1  # set while the second model is running
    text = """
nodes:
  a: {op: separate, model: vocal-model}
  out_a: {op: export, inputs: [a.vocals]}
  b: {op: separate, model: four-stem}
  out_b: {op: export, inputs: [b.drums]}
"""
    events = []
    with pytest.raises(Cancelled):
        runner.run_recipe(
            recipe.loads(text), clip, tmp_path / "out", registry=registry, cancel=cancel, events=events.append
        )
    assert not (tmp_path / "out").exists(), "the already exported stem must not be left behind"
    assert events[-1]["type"] == "run_cancelled"


def test_cancel_before_the_start_does_nothing(clip, tmp_path, registry, fake_backend):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        runner.run_recipe(recipe.loads(SEPARATE_EXPORT), clip, tmp_path / "out", registry=registry, cancel=cancel)
    assert fake_backend.calls == [] and not (tmp_path / "out").exists()


def test_a_failing_node_leaves_no_output_files(clip, tmp_path, registry, fake_backend):
    text = """
nodes:
  a: {op: subtract, inputs: {a: mix, b: mix}}
  out_a: {op: export, inputs: [a.out]}
  b: {op: separate, model: vocal-model}
"""
    fake_backend.fail = True
    events = []
    with pytest.raises(RuntimeError, match="fake model failed"):
        runner.run_recipe(recipe.loads(text), clip, tmp_path / "out", registry=registry, events=events.append)
    assert not (tmp_path / "out").exists()
    assert events[-1] == {"type": "run_failed", "error": "the fake model failed", "run_id": events[0]["run_id"]}

    # Existing outputs of an earlier run survive a failed one
    fake_backend.fail = False
    run(text, clip, tmp_path, registry)
    fake_backend.fail = True
    with pytest.raises(RuntimeError):
        run(text.replace("vocal-model", "two-stem"), clip, tmp_path, registry)
    assert (tmp_path / "out" / "run.json").is_file() and (tmp_path / "out" / "clip-5s_a.flac").is_file()


def test_out_of_memory_adjustments_are_surfaced(clip, tmp_path, registry, fake_backend):
    fake_backend.adjustments = ["GPU out of memory: batch_size lowered to 2"]
    record, events = run(SEPARATE_EXPORT, clip, tmp_path, registry)
    assert record["warnings"] == [{"node": "split", "message": "GPU out of memory: batch_size lowered to 2"}]
    assert record["nodes"]["split"]["info"]["adjustments"] == fake_backend.adjustments
    assert any(event["type"] == "warning" for event in events)


# Inputs ---------------------------------------------------------------------------


def test_mono_and_other_sample_rates(tmp_path, registry, fake_backend):
    mono = write_tone(tmp_path / "mono.wav", seconds=1.0, sample_rate=48000, channels=1)
    add_fake_model(registry, "at-44k", ["vocals"], sample_rate=44100)
    text = """
nodes:
  vox: {op: separate, model: at-44k}
  inst: {op: subtract, inputs: {a: mix, b: vox.vocals}}
  out: {op: export, inputs: [vox.vocals, inst.out]}
"""
    record, _ = run(text, mono, tmp_path, registry)
    assert record["input"]["channels"] == 1 and record["input"]["sample_rate"] == 48000
    call = fake_backend.calls[0]
    assert call["sample_rate"] == 44100 and call["shape"] == (2, 44100), "the model gets stereo at its own rate"
    info = sf.info(str(tmp_path / "out" / "mono_vocals.flac"))
    assert (info.samplerate, info.frames, info.channels) == (48000, 48000, 2), "stems come back at the source rate"


def test_default_output_folder_sits_next_to_the_input(tmp_path, registry):
    source = write_tone(tmp_path / "My Song.wav")
    record = runner.run_recipe(recipe.loads(SEPARATE_EXPORT), source, registry=registry)
    assert record["output_dir"] == str(tmp_path / "My Song [two-node]")
    assert (tmp_path / "My Song [two-node]" / "run.json").is_file()


def test_missing_input_file(tmp_path, registry):
    with pytest.raises(audio.AudioError, match="File not found"):
        runner.run_recipe(recipe.loads(SEPARATE_EXPORT), tmp_path / "nope.wav", registry=registry)


# Found in review -------------------------------------------------------------------


def test_a_default_is_skipped_where_it_does_not_fit_but_must_fit_somewhere(clip, tmp_path, registry, fake_backend):
    """`overlap` is a chunk count for one backend and a fraction for another."""
    from conftest import FakeBackend

    from captainstems.backends import base
    from captainstems.backends.base import ParamSpec

    fractional = FakeBackend()
    fractional.name = "demucs"
    fractional.supported_params = {
        "device": fractional.supported_params["device"],
        "overlap": ParamSpec("float", 0.25, "fraction", minimum=0.0, maximum=0.95),
    }
    fractional.device_defaults = lambda device, vram_mb: {}
    base._instances["demucs"] = fractional
    add_fake_model(registry, "fraction-model", ["vocals"], backend="demucs")

    text = """
defaults: {overlap: OVERLAP}
nodes:
  counted: {op: separate, model: vocal-model}
  fraction: {op: separate, model: fraction-model}
"""
    record, _ = run(text.replace("OVERLAP", "4"), clip, tmp_path, registry)
    assert record["nodes"]["counted"]["params"]["overlap"] == 4
    assert record["nodes"]["fraction"]["params"]["overlap"] == 0.25, "the count does not fit a fraction; default kept"

    record, _ = run(text.replace("OVERLAP", "0.5"), clip, tmp_path, registry)
    assert record["nodes"]["fraction"]["params"]["overlap"] == 0.5
    assert record["nodes"]["counted"]["params"]["overlap"] == 3, "falls back to the device default"

    with pytest.raises(RecipeError, match="defaults.overlap fits no node"):
        run(text.replace("OVERLAP", "500"), clip, tmp_path, registry)


def test_same_named_inputs_get_separate_output_folders(tmp_path, registry):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = write_tone(tmp_path / "a" / "song.wav", frequency=440)
    second = write_tone(tmp_path / "b" / "song.wav", frequency=880)
    parsed = recipe.loads(SEPARATE_EXPORT)
    out = tmp_path / "out"

    one = runner.run_recipe(parsed, first, registry=registry, out_parent=out)
    two = runner.run_recipe(parsed, second, registry=registry, out_parent=out)
    again = runner.run_recipe(parsed, first, registry=registry, out_parent=out)

    assert one["output_dir"] == str(out / "song [two-node]")
    assert two["output_dir"] == str(out / "song [two-node] (2)"), "another file with the same name must not overwrite"
    assert again["output_dir"] == one["output_dir"], "running the same file again replaces its own results"
    assert json.loads((out / "song [two-node]" / "run.json").read_text())["input"]["path"] == str(first.resolve())


def test_a_changed_reference_file_is_not_served_from_the_cache(clip, tmp_path, registry):
    mix, rate = audio.load(clip)
    reference = tmp_path / "ref.wav"
    text = f"""
nodes:
  vox: {{op: separate, model: vocal-model}}
  check: {{op: analyze, inputs: {{stems: [vox.vocals]}}, params: {{reference: '{reference.as_posix()}'}}}}
"""
    audio.write(reference, mix * 0.5, rate, "wav", 32)
    good, _ = run(text, clip, tmp_path, registry)
    rng = np.random.default_rng(0)
    audio.write(reference, rng.standard_normal(mix.shape).astype(np.float32) * 0.1, rate, "wav", 32)
    bad, _ = run(text, clip, tmp_path, registry)

    assert bad["nodes"]["check"]["cached"] is False
    assert bad["nodes"]["check"]["cache_key"] != good["nodes"]["check"]["cache_key"]
    assert good["nodes"]["check"]["info"]["metrics"]["si_sdr_db"] > 60
    assert bad["nodes"]["check"]["info"]["metrics"]["si_sdr_db"] < 0
    assert bad["nodes"]["vox"]["cached"] is True, "only the node that reads the reference is recomputed"

    reference.unlink()
    with pytest.raises(RecipeError, match="node 'check': reference file not found"):
        run(text, clip, tmp_path, registry)


def test_a_perfect_score_is_still_valid_json(clip, tmp_path, registry):
    mix, rate = audio.load(clip)
    reference = tmp_path / "same.wav"
    audio.write(reference, mix * 0.5, rate, "wav", 32)
    text = f"""
nodes:
  vox: {{op: separate, model: vocal-model}}
  check: {{op: analyze, inputs: {{stems: [vox.vocals]}}, params: {{reference: '{reference.as_posix()}'}}}}
"""
    record, _ = run(text, clip, tmp_path, registry)
    assert record["nodes"]["check"]["info"]["metrics"]["si_sdr_db"] == 120.0
    json.dumps(record, allow_nan=False)
    json.loads((tmp_path / "out" / "run.json").read_text(), parse_constant=lambda name: pytest.fail(name))
