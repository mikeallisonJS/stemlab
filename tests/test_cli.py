import json

from typer.testing import CliRunner

from captainstems.cli import app

runner = CliRunner()

RECIPE = """
name: cli
nodes:
  vox: {op: separate, model: vocal-model}
  inst: {op: subtract, inputs: {a: mix, b: vox.vocals}}
  check: {op: analyze, inputs: {stems: [vox.vocals, inst.out]}}
  out: {op: export, inputs: {vocals: vox.vocals, instrumental: inst.out}}
"""


def write_recipe(tmp_path, text=RECIPE):
    path = tmp_path / "recipe.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_run_writes_stems(clip, tmp_path, registry):
    out = tmp_path / "out"
    result = runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(clip), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in out.iterdir()) == [
        "clip-5s_instrumental.flac",
        "clip-5s_vocals.flac",
        "run.json",
    ]
    assert "2 files" in result.output and "residual" in result.output


def test_run_can_repeat_a_run_json(clip, tmp_path, registry, fake_backend):
    out = tmp_path / "out"
    runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(clip), "--out", str(out)])
    again = tmp_path / "again"
    result = runner.invoke(app, ["run", str(out / "run.json"), str(clip), "--out", str(again)])
    assert result.exit_code == 0, result.output
    first = json.loads((out / "run.json").read_text())
    second = json.loads((again / "run.json").read_text())
    assert second["nodes"]["vox"]["params"] == first["nodes"]["vox"]["params"]
    assert second["nodes"]["vox"]["cached"] is True
    assert len(fake_backend.calls) == 1


def test_run_several_files_into_one_parent_folder(clip, tmp_path, registry):
    from conftest import write_tone

    other = write_tone(tmp_path / "other.wav")
    out = tmp_path / "batch"
    result = runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(clip), str(other), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in out.iterdir()) == ["clip-5s [cli]", "other [cli]"]

    # Two files with the same name from different folders stay apart
    (tmp_path / "elsewhere").mkdir()
    twin = write_tone(tmp_path / "elsewhere" / "other.wav", frequency=880)
    result = runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(other), str(twin), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in out.iterdir()) == ["clip-5s [cli]", "other [cli]", "other [cli] (2)"]


def test_run_emits_json_events(clip, tmp_path, registry):
    result = runner.invoke(
        app, ["run", str(write_recipe(tmp_path)), str(clip), "--out", str(tmp_path / "o"), "--events"]
    )
    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in result.output.splitlines() if line.startswith("{")]
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_finished"


def test_events_mode_reports_failures_that_happen_before_the_run(clip, tmp_path, registry):
    missing_model = write_recipe(tmp_path, "nodes:\n  a: {op: separate, model: absent}\n")
    result = runner.invoke(app, ["run", str(missing_model), str(clip), "--events"])
    assert result.exit_code == 1
    events = [json.loads(line) for line in result.output.splitlines() if line.startswith("{")]
    assert [event["type"] for event in events] == ["run_failed"]
    assert "is not installed" in events[0]["error"] and events[0]["input"] == str(clip)

    result = runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(tmp_path / "nope.wav"), "--events"])
    events = [json.loads(line) for line in result.output.splitlines() if line.startswith("{")]
    assert result.exit_code == 1 and events[-1]["type"] == "run_failed" and "File not found" in events[-1]["error"]


def test_run_reports_problems_without_a_traceback(clip, tmp_path, registry):
    bad = write_recipe(tmp_path, "nodes:\n  a: {op: subtract, inputs: {a: mix, b: nope.out}}\n")
    result = runner.invoke(app, ["run", str(bad), str(clip)])
    assert result.exit_code == 2 and "there is no node 'nope'" in result.output

    missing_model = write_recipe(tmp_path, "nodes:\n  a: {op: separate, model: absent}\n")
    result = runner.invoke(app, ["run", str(missing_model), str(clip)])
    assert result.exit_code == 1 and "is not installed" in result.output and "Traceback" not in result.output

    result = runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(tmp_path / "missing.flac")])
    assert result.exit_code == 1 and "File not found" in result.output
    assert runner.invoke(app, ["run", str(tmp_path / "missing.yaml"), str(clip)]).exit_code == 2


def test_validate_shows_resolved_parameters(tmp_path, registry):
    result = runner.invoke(app, ["validate", str(write_recipe(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "vocal-model" in result.output and "overlap=3" in result.output
    bad = write_recipe(tmp_path, "nodes:\n  a: {op: separate, model: vocal-model, targets: [drums]}\n")
    assert runner.invoke(app, ["validate", str(bad)]).exit_code == 2


def test_schema(registry):
    schema = json.loads(runner.invoke(app, ["schema"]).output)
    assert "nodes" in schema["properties"]
    full = json.loads(runner.invoke(app, ["schema", "--backends"]).output)
    assert set(full["backends"]) == {"msst", "demucs", "onnx"}
    assert "overlap" in full["backends"]["msst"]["properties"]


def test_cache_commands(clip, tmp_path, registry):
    runner.invoke(app, ["run", str(write_recipe(tmp_path)), str(clip), "--out", str(tmp_path / "o")])
    assert "MB" in runner.invoke(app, ["cache", "info"]).output
    assert "Freed" in runner.invoke(app, ["cache", "clear"]).output
    assert " 0 B" in runner.invoke(app, ["cache", "info"]).output
