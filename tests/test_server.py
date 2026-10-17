import json
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="install the server extra: uv sync --inexact --extra server")

from fastapi.testclient import TestClient

from stemlab.server.app import create_app
from stemlab.server.jobs import JobManager

RECIPE = {
    "name": "api",
    "nodes": {
        "vox": {"op": "separate", "model": "vocal-model"},
        "inst": {"op": "subtract", "inputs": {"a": "mix", "b": "vox.vocals"}},
        "check": {"op": "analyze", "inputs": {"stems": ["vox.vocals", "inst.out"]}},
        "out": {"op": "export", "inputs": {"vocals": "vox.vocals", "instrumental": "inst.out"}},
    },
}

WORKED_EXAMPLE = Path(__file__).parent.parent / "recipes" / "full-split-v1.yaml"


@pytest.fixture
def client(registry):
    manager = JobManager()
    with TestClient(create_app(manager), base_url="http://127.0.0.1:8787") as client:
        client.manager = manager
        yield client


def wait(client, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("the job did not finish")


def submit(client, clip, tmp_path, recipe=RECIPE, **extra):
    response = client.post(
        "/jobs", json={"recipe": recipe, "inputs": [str(clip)], "out_dir": str(tmp_path / "out"), **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


# System, schema, recipes -------------------------------------------------------------


def test_system_reports_hardware_and_backends(client):
    info = client.get("/system").json()
    assert info["flavor"] in ("cuda", "rocm", "mps", "cpu") and info["version"]
    assert set(info["backends"]) == {"msst", "demucs", "onnx"}


def test_system_config_overrides_flavor_and_target(client, home):
    info = client.get("/system").json()
    assert info["flavor_source"] == "detected"
    assert "commands" in info["bootstrap"] or "error" in info["bootstrap"]

    info = client.put("/system/config", json={"torch_flavor": "cpu"}).json()
    assert (info["flavor"], info["flavor_source"]) == ("cpu", "override")
    assert any("whl/cpu" in command for command in info["bootstrap"]["commands"])

    assert client.put("/system/config", json={"torch_flavor": "vulkan"}).status_code == 400
    assert client.put("/system/config", json={"rocm_target": "navi"}).status_code == 400
    assert (
        client.put("/system/config", json={"torch_flavor": "rocm", "rocm_target": "gfx1100"}).json()["flavor"] == "rocm"
    )

    info = client.put("/system/config", json={}).json()
    assert info["flavor_source"] == "detected"


def test_schema_carries_what_the_forms_need(client):
    schema = client.get("/schema").json()
    assert set(schema["ops"]) == {"separate", "subtract", "ensemble", "postprocess", "analyze", "export"}
    assert schema["ops"]["subtract"]["inputs"] == [{"name": "a", "many": False}, {"name": "b", "many": False}]
    assert "overlap" in schema["backends"]["msst"]["properties"]
    assert "ExportParams" in schema["recipe"]["$defs"]


def test_shipped_recipes_are_listed(client):
    names = [item["name"] for item in client.get("/recipes").json()]
    assert "full-split-v1" in names and "four-stems" in names


def test_recipe_round_trips_through_yaml_without_loss(client):
    text = WORKED_EXAMPLE.read_text(encoding="utf-8")
    data = client.post("/recipes/parse", json={"yaml": text}).json()["recipe"]
    written = client.post("/recipes/yaml", json={"recipe": data}).json()["yaml"]
    again = client.post("/recipes/parse", json={"yaml": written}).json()["recipe"]
    assert again == data
    assert client.post("/recipes/yaml", json={"recipe": again}).json()["yaml"] == written
    assert data["nodes"]["drums"]["params"] == {"weights": [0.6, 0.4]}, "defaults are not spelled out"


def test_recipe_errors_are_reported_as_422(client):
    response = client.post("/recipes/parse", json={"yaml": "nodes:\n  a: {op: subtract, inputs: {a: mix, b: x.out}}"})
    assert response.status_code == 422 and "there is no node 'x'" in response.json()["detail"]


def test_validate_resolves_parameters_or_explains(client):
    ok = client.post("/recipes/validate", json={"recipe": RECIPE}).json()
    assert ok["ok"] and ok["order"] == ["vox", "inst", "check", "out"]
    assert ok["nodes"]["vox"]["params"]["overlap"] == 3 and ok["nodes"]["vox"]["outputs"] == ["vocals"]

    bad = json.loads(json.dumps(RECIPE))
    bad["nodes"]["vox"]["model"] = "absent"
    result = client.post("/recipes/validate", json={"recipe": bad}).json()
    assert result == {"ok": False, "error": "node 'vox': Model 'absent' is not installed."}


# Jobs --------------------------------------------------------------------------------


def test_a_job_runs_and_reports_its_result(client, clip, tmp_path):
    created = submit(client, clip, tmp_path)
    assert created["status"] in ("queued", "running", "finished") and created["order"] == [
        "vox",
        "inst",
        "check",
        "out",
    ]
    job = wait(client, created["id"])
    assert job["status"] == "finished" and job["error"] is None
    assert [job["nodes"][name]["status"] for name in job["order"]] == ["done"] * 4
    assert sorted(output["stem"] for output in job["outputs"]) == ["instrumental", "vocals"]
    assert (tmp_path / "out" / "run.json").is_file()
    assert job["record"]["nodes"]["check"]["info"]["metrics"]["residual_rms_db"] == -120.0
    assert job["recipe_data"]["nodes"]["vox"]["model"] == "vocal-model"
    assert [item["id"] for item in client.get("/jobs").json()] == [created["id"]]


def test_events_are_replayed_and_followed_over_the_websocket(client, clip, tmp_path):
    created = submit(client, clip, tmp_path)
    events = []
    with client.websocket_connect(f"ws://127.0.0.1:8787/jobs/{created['id']}/events") as socket:
        while True:
            event = socket.receive_json()
            events.append(event)
            if event["type"] == "job_done":
                break
    kinds = [event["type"] for event in events]
    assert kinds[0] == "job_queued" and kinds[-1] == "job_done" and "run_finished" in kinds
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert any(event["type"] == "node_progress" and event["node"] == "vox" for event in events)
    assert events[-1]["status"] == "finished"

    # Connecting after the end still delivers the whole history
    with client.websocket_connect(f"ws://127.0.0.1:8787/jobs/{created['id']}/events") as socket:
        replay = []
        while True:
            event = socket.receive_json()
            replay.append(event)
            if event["type"] == "job_done":
                break
    assert replay == events


def test_several_inputs_make_several_jobs(client, clip, tmp_path):
    from conftest import write_tone

    other = write_tone(tmp_path / "other.wav")
    response = client.post(
        "/jobs", json={"recipe": RECIPE, "inputs": [str(clip), str(other)], "out_dir": str(tmp_path / "batch")}
    )
    created = response.json()
    assert len(created) == 2
    for item in created:
        assert wait(client, item["id"])["status"] == "finished"
    assert sorted(path.name for path in (tmp_path / "batch").iterdir()) == ["clip-5s [api]", "other [api]"]


def test_bad_requests_are_rejected_before_queueing(client, clip, tmp_path):
    assert client.post("/jobs", json={"recipe": RECIPE, "inputs": [str(tmp_path / "nope.wav")]}).status_code == 404
    bad = json.loads(json.dumps(RECIPE))
    bad["nodes"]["vox"]["params"] = {"overlap": 99}
    response = client.post("/jobs", json={"recipe": bad, "inputs": [str(clip)]})
    assert response.status_code == 422 and "overlap must be at most 32" in response.json()["detail"]
    assert client.post("/jobs", json={"inputs": [str(clip)]}).status_code == 422
    assert client.get("/jobs").json() == []
    assert client.get("/jobs/unknown").status_code == 404


def test_a_failing_job_reports_the_error(client, clip, tmp_path, fake_backend):
    fake_backend.fail = True
    job = wait(client, submit(client, clip, tmp_path)["id"])
    assert job["status"] == "failed" and job["error"] == "the fake model failed"
    assert job["nodes"]["vox"]["status"] == "failed"
    assert not (tmp_path / "out").exists()


def test_cancelling_a_queued_job(client, clip, tmp_path, fake_backend):
    # Jobs run one at a time: hold the first so the second stays queued
    import threading

    gate = threading.Event()
    original = fake_backend.load

    def slow_load(manifest, params):
        gate.wait(10)
        return original(manifest, params)

    fake_backend.load = slow_load
    first = submit(client, clip, tmp_path)
    second = submit(client, clip, tmp_path / "second")
    assert client.delete(f"/jobs/{second['id']}").status_code == 409, "an active job cannot be deleted"
    assert client.post(f"/jobs/{second['id']}/cancel").json()["status"] == "cancelled"

    # Whoever follows the cancelled job is told that it is over
    with client.websocket_connect(f"ws://127.0.0.1:8787/jobs/{second['id']}/events") as socket:
        kinds = []
        while not kinds or kinds[-1] != "job_done":
            kinds.append(socket.receive_json()["type"])
    assert kinds == ["job_queued", "run_cancelled", "job_done"]
    gate.set()
    assert wait(client, first["id"])["status"] == "finished"
    assert client.get(f"/jobs/{second['id']}").json()["status"] == "cancelled"
    assert client.delete(f"/jobs/{second['id']}").status_code == 204
    assert client.get(f"/jobs/{second['id']}").status_code == 404


def test_cancelling_a_running_job_leaves_no_outputs(client, clip, tmp_path, fake_backend):
    import threading

    started, release = threading.Event(), threading.Event()
    original = fake_backend.load

    def slow_load(manifest, params):
        started.set()
        release.wait(10)
        return original(manifest, params)

    fake_backend.load = slow_load
    created = submit(client, clip, tmp_path)
    assert started.wait(10)
    client.post(f"/jobs/{created['id']}/cancel")
    release.set()
    job = wait(client, created["id"])
    assert job["status"] == "cancelled"
    assert not (tmp_path / "out").exists()


# Results -----------------------------------------------------------------------------


def test_stems_can_be_played_and_drawn(client, clip, tmp_path):
    job = wait(client, submit(client, clip, tmp_path)["id"])
    for node, stem in [("mix", "mix"), ("vox", "vocals"), ("inst", "out"), ("check", "residual")]:
        response = client.get(f"/jobs/{job['id']}/audio/{node}/{stem}")
        assert response.status_code == 200 and response.headers["content-type"] == "audio/flac"
        assert response.content[:4] == b"fLaC"

        peaks = client.get(f"/jobs/{job['id']}/peaks/{node}/{stem}?buckets=100").json()
        assert len(peaks["peaks"]) == 100 and peaks["duration"] == pytest.approx(5.0)

        image = client.get(f"/jobs/{job['id']}/spectrogram/{node}/{stem}?width=200&height=64")
        assert image.headers["content-type"] == "image/png" and image.content[:4] == b"\x89PNG"

    # The residual of an exact split is silence
    assert client.get(f"/jobs/{job['id']}/peaks/check/residual").json()["rms_db"] == -120.0
    ranged = client.get(f"/jobs/{job['id']}/audio/vox/vocals", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206 and len(ranged.content) == 100, "seeking needs range requests"
    assert client.get(f"/jobs/{job['id']}/audio/vox/drums").status_code == 404
    assert client.get(f"/jobs/{job['id']}/audio/out/anything").status_code == 404


def test_a_finished_run_can_be_opened_again(client, clip, tmp_path):
    job = wait(client, submit(client, clip, tmp_path)["id"])
    client.delete(f"/jobs/{job['id']}")

    opened = client.post("/runs/open", json={"path": str(tmp_path / "out")})
    assert opened.status_code == 201, opened.text
    reopened = opened.json()
    assert reopened["status"] == "finished" and reopened["id"] != job["id"]
    assert reopened["nodes"]["vox"]["status"] == "done"
    assert client.get(f"/jobs/{reopened['id']}/audio/inst/out").status_code == 200
    assert client.get(f"/jobs/{reopened['id']}/audio/mix/mix").status_code == 200
    assert client.post("/runs/open", json={"path": str(tmp_path / "nothing")}).status_code == 404
    (tmp_path / "bad.json").write_text("{}")
    assert client.post("/runs/open", json={"path": str(tmp_path / "bad.json")}).status_code == 422


# Models ------------------------------------------------------------------------------


def test_models_are_listed_added_and_removed(client, tmp_path):
    listed = client.get("/models").json()
    assert {"vocal-model", "four-stem"} <= {model["id"] for model in listed["models"] if model["installed"]}
    assert any(model.get("curated") and not model["installed"] for model in listed["models"])

    weights = tmp_path / "w.ckpt"
    weights.write_bytes(b"abc")
    config = tmp_path / "c.yaml"
    config.write_text("x: 1\n")
    manifest = {
        "id": "from-api",
        "backend": "msst",
        "arch": "mdx23c",
        "config": "c.yaml",
        "weights": "w.ckpt",
        "stems": ["vocals"],
    }
    body = {"manifest": manifest, "files": {"w.ckpt": str(weights), "c.yaml": str(config)}}
    assert client.post("/models", json=body).status_code == 201
    assert client.post("/models", json=body).status_code == 409
    assert client.post("/models", json={"manifest": {**manifest, "id": "bad id"}}).status_code == 422
    assert client.delete("/models/from-api").status_code == 204
    assert client.delete("/models/from-api").status_code == 404
    assert client.post("/models/not-curated/fetch").status_code == 404


# Picking files -----------------------------------------------------------------------


def test_browsing_lists_folders_and_audio_files(client, tmp_path):
    library = tmp_path / "library"
    (library / "music").mkdir(parents=True)
    (library / "song.flac").write_bytes(b"x")
    (library / "notes.txt").write_text("x")
    (library / ".hidden").mkdir()
    listing = client.get("/fs", params={"path": str(library)}).json()
    assert [item["name"] for item in listing["folders"]] == ["music"]
    assert [item["name"] for item in listing["files"]] == ["song.flac"]
    assert listing["parent"] == str(tmp_path)
    assert client.get("/fs").json()["folders"], "without a path the starting points are listed"
    assert client.get("/fs", params={"path": str(library / "nope")}).status_code == 404


def test_uploads_become_usable_inputs(client, clip, tmp_path):
    response = client.post("/uploads", params={"name": "../../dropped song.flac"}, content=clip.read_bytes())
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["name"] == "dropped song.flac" and uploaded["duration"] == 5.0
    assert Path(uploaded["path"]).parent.parent.name == "uploads", "the name cannot escape the upload folder"
    assert wait(client, submit(client, uploaded["path"], tmp_path)["id"])["status"] == "finished"

    # Without a chosen folder the stems of a dropped file go to the outputs folder, not into the upload
    response = client.post("/jobs", json={"recipe": RECIPE, "inputs": [uploaded["path"]]})
    job = wait(client, response.json()[0]["id"])
    outputs = Path(client.get("/system").json()["outputs_dir"])
    assert Path(job["output_dir"]) == outputs / "dropped song [api]"
    assert (outputs / "dropped song [api]" / "run.json").is_file()

    assert client.post("/uploads", params={"name": "x.exe"}, content=b"MZ").status_code == 415
    assert client.post("/uploads", params={"name": "fake.wav"}, content=b"not audio").status_code == 415
    assert client.post("/uploads", params={"name": "empty.wav"}, content=b"").status_code == 400
    assert client.get("/audio/info", params={"path": str(clip)}).json()["sample_rate"] == 44100


# Safety ------------------------------------------------------------------------------


def test_requests_for_other_hosts_are_refused(client):
    assert client.get("/system", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/system", headers={"Host": "testserver"}).status_code == 400
    assert client.get("/system", headers={"Host": "localhost"}).status_code == 200
    assert client.get("/system", headers={"Host": "[::1]:8787"}).status_code == 200


def test_serving_on_another_address_accepts_that_address(registry):
    lan = TestClient(
        create_app(JobManager(), allowed_hosts=["127.0.0.1", "192.168.1.20"]), base_url="http://192.168.1.20"
    )
    with lan:
        assert lan.get("/system").status_code == 200
        assert lan.get("/system", headers={"Host": "evil.example"}).status_code == 400


def test_same_named_inputs_in_one_request_stay_apart(client, tmp_path):
    from conftest import write_tone

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    inputs = [str(write_tone(tmp_path / "a" / "song.wav")), str(write_tone(tmp_path / "b" / "song.wav", frequency=880))]
    created = client.post("/jobs", json={"recipe": RECIPE, "inputs": inputs, "out_dir": str(tmp_path / "out")}).json()
    folders = sorted(Path(wait(client, item["id"])["output_dir"]).name for item in created)
    assert folders == ["song [api]", "song [api] (2)"]


def test_old_uploads_are_cleaned_up(home):
    import os
    import time

    from stemlab import paths
    from stemlab.server.app import clean_uploads

    old = paths.uploads_dir() / "old"
    fresh = paths.uploads_dir() / "fresh"
    for folder in (old, fresh):
        folder.mkdir()
        (folder / "song.wav").write_bytes(b"x")
    stale = time.time() - 30 * 86400
    os.utime(old / "song.wav", (stale, stale))
    os.utime(old, (stale, stale))
    assert clean_uploads() == 1
    assert not old.exists() and fresh.exists()


def test_only_local_pages_may_read_the_api(client):
    local = client.get("/system", headers={"Origin": "http://localhost:5173"})
    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"
    foreign = client.get("/system", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in foreign.headers
