import threading

import pytest
import soundfile as sf

from conftest import write_tone
from core import ffmpeg
from core.process import ProcessCancelled
from models import registry
from models.bandsplit_model import BandSplitModel
from models.base_model import ModelError, ModelNotInstalledError
from models.d3net_model import D3NetModel
from models.demucs_model import DemucsModel
from models.spleeter_model import SpleeterModel


# Registry -------------------------------------------------------------------

def test_every_family_has_a_valid_default():
    for family in registry.FAMILIES.values():
        assert family.default in family.models
        assert family.backend in registry.BACKEND_TITLES
    assert len(registry.default_model_ids()) == len(registry.FAMILIES)


def test_every_model_can_be_created_and_knows_its_stems():
    for family in registry.FAMILIES.values():
        for model_name in family.models:
            identifier = registry.model_id(family.key, model_name)
            model = registry.create_model(identifier)
            assert model.model_name == model_name
            assert len(model.get_stems()) >= 2, identifier
            assert not model.available, "no model is installed in the test environment"
            assert registry.display_name(identifier) == f"{family.title} ({model_name})"


def test_model_identifiers():
    assert registry.parse_model_id("demucs4:htdemucs") == ("demucs4", "htdemucs")
    assert registry.parse_model_id("demucs4:mdx") is None, "mdx is a v3 model"
    assert registry.parse_model_id("nonsense") is None
    assert registry.parse_model_id("") is None
    with pytest.raises(ValueError):
        registry.create_model("demucs4:nope")


def test_find_model_by_short_name():
    assert registry.find_model_id("htdemucs_ft") == "demucs4:htdemucs_ft"
    assert registry.find_model_id("spleeter:4stems") == "spleeter:4stems"
    assert registry.find_model_id("d3net") == "d3net:standard"
    # "standard" would be ambiguous if several families had it; it must resolve or be rejected
    assert registry.find_model_id("6stems") == "bandsplit:6stems"
    assert registry.find_model_id("unknown") is None


def test_backends_are_shared_between_demucs_families():
    backends = registry.backend_models()
    assert set(backends) == {"demucs", "spleeter", "bandsplit", "d3net"}
    assert registry.FAMILIES["demucs3"].backend == registry.FAMILIES["demucs4"].backend == "demucs"


# Individual models ------------------------------------------------------------

def test_demucs_stems_and_two_stems_mode():
    assert DemucsModel("htdemucs").get_stems() == ["drums", "bass", "other", "vocals"]
    assert DemucsModel("htdemucs_6s").get_stems() == ["drums", "bass", "other", "vocals", "guitar", "piano"]
    assert DemucsModel("mdx_extra").is_v3 and not DemucsModel("htdemucs").is_v3
    assert DemucsModel("mdx").get_stems(two_stems=True) == ["vocals", "no_vocals"]
    assert DemucsModel("htdemucs").supports_two_stems
    assert not SpleeterModel("2stems").supports_two_stems


def test_demucs_command_arguments():
    model = DemucsModel("htdemucs_ft")
    assert model.get_model_cmd_args() == ["-n", "htdemucs_ft"]
    args = model.get_model_cmd_args(True, {"device": "cpu", "demucs_shifts": 3, "demucs_overlap": 0.5})
    assert args == ["-n", "htdemucs_ft", "--two-stems=vocals", "-d", "cpu", "--shifts", "3",
                    "--overlap", "0.50"]
    # "auto" leaves the device choice to Demucs
    assert "-d" not in model.get_model_cmd_args(False, {"device": "auto"})


def test_unknown_model_names_are_rejected():
    for model_class in (DemucsModel, SpleeterModel, BandSplitModel, D3NetModel):
        with pytest.raises(ValueError):
            model_class("does-not-exist")


def test_bandsplit_recognises_stems_in_output_names():
    pattern = BandSplitModel._STEM_IN_FILENAME
    assert pattern.search("input_(Vocals)_model_bs_roformer_ep_317_sdr_12.wav").group(1) == "Vocals"
    assert pattern.search("input_(drums)_BS-Roformer-SW.wav").group(1) == "drums"
    assert pattern.search("input.wav") is None


def test_spleeter_pins_a_tensorflow_build_for_each_platform():
    model = SpleeterModel("2stems")
    requirements = model._tensorflow_requirements()
    assert any(requirement.startswith("tensorflow") for requirement in requirements)
    model.is_apple_silicon = True
    assert model._tensorflow_requirements() == ["tensorflow-macos==2.12.0"]


def test_uninstalled_model_refuses_to_process(tmp_path, tone_wav):
    with pytest.raises(ModelNotInstalledError):
        DemucsModel("htdemucs").process(str(tone_wav), str(tmp_path / "out"))


# The shared processing workflow -------------------------------------------------

def test_process_writes_one_wav_per_stem(tmp_path, tone_wav, fake_model_class):
    model = fake_model_class()
    progress, statuses = [], []
    out = model.process(str(tone_wav), str(tmp_path / "out"),
                        progress_callback=progress.append, status_callback=statuses.append,
                        options={"device": "cpu"})
    produced = sorted(path.name for path in (tmp_path / "out").iterdir())
    assert produced == ["drums.wav", "vocals.wav"], "working files must be cleaned up"
    assert out == str(tmp_path / "out")
    assert progress[0] == 0 and progress[-1] == 100
    assert progress == sorted(progress)
    assert "Separating stems..." in statuses
    assert model.calls == [{"two_stems": False, "options": {"device": "cpu"}}]


def test_process_converts_other_formats_first(tmp_path, fake_model_class):
    source = write_tone(tmp_path / "source.flac", sample_rate=48000, channels=1)
    model = fake_model_class()
    statuses = []
    model.process(str(source), str(tmp_path / "out"), status_callback=statuses.append)
    assert statuses[0] == "Converting audio..."
    # The fake model copies its input, so the stem shows what the model was given
    assert ffmpeg.is_standard_wav(tmp_path / "out" / "vocals.wav")


def test_process_gives_backends_a_plain_file_name(tmp_path, fake_model_class):
    """Backends derive output names from the input name, so it must be predictable."""
    seen = []

    class Recording(fake_model_class):
        def _separate(self, input_wav, raw_dir, *args):
            seen.append(input_wav.name)
            return super()._separate(input_wav, raw_dir, *args)

    Recording().process(str(write_tone(tmp_path / "Weird (name) [x].wav")), str(tmp_path / "out"))
    assert seen == ["input.wav"]


def test_process_two_stems(tmp_path, tone_wav, fake_model_class):
    model = fake_model_class()
    model.process(str(tone_wav), str(tmp_path / "out"), two_stems=True)
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == ["no_vocals.wav", "vocals.wav"]


def test_process_reports_missing_stems(tmp_path, tone_wav, fake_model_class):
    class Incomplete(fake_model_class):
        def _separate(self, input_wav, raw_dir, *args):
            stems = super()._separate(input_wav, raw_dir, *args)
            stems["drums"].unlink()
            return stems

    with pytest.raises(ModelError, match="drums"):
        Incomplete().process(str(tone_wav), str(tmp_path / "out"))
    assert not list((tmp_path / "out").glob("work_*")), "working files must be cleaned up"


def test_process_cleans_up_after_failure_and_cancel(tmp_path, tone_wav, fake_model_class):
    with pytest.raises(ModelError, match="broken"):
        fake_model_class("broken").process(str(tone_wav), str(tmp_path / "failed"))
    assert not list((tmp_path / "failed").glob("work_*"))

    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ProcessCancelled):
        fake_model_class().process(str(tone_wav), str(tmp_path / "cancelled"), cancel_event=cancel)
    assert not list((tmp_path / "cancelled").glob("work_*"))


def test_stems_keep_the_length_of_the_input(tmp_path, tone_wav, fake_model_class):
    fake_model_class().process(str(tone_wav), str(tmp_path / "out"))
    assert sf.info(str(tmp_path / "out" / "vocals.wav")).frames == sf.info(str(tone_wav)).frames


def stub_environment(model):
    """Replace creating a virtual environment (slow, needs network) by an empty directory."""
    def create(log=None, cancel_event=None):
        model.env.remove()
        model.env.python.parent.mkdir(parents=True)
        model.env.python.write_text("")
    model.env.create = create


def test_failed_install_cleans_up_and_reports(fake_model_class):
    class FailingInstall(fake_model_class):
        BACKEND = "fake_failing"

        def _install(self, log, cancel_event):
            raise RuntimeError("no network")

    model = FailingInstall()
    stub_environment(model)
    log = []
    assert model.install_dependencies(log=log.append) is False
    assert "no network" in model.last_error
    assert any("no network" in line for line in log)
    assert not model.env.exists(), "a failed installation must not leave an environment behind"
    assert not model.available


def test_install_and_uninstall_roundtrip(fake_model_class):
    class Installable(fake_model_class):
        BACKEND = "fake_installable"

        def _verify(self, log, cancel_event):
            return {"package": "fake==1.0"}

    model = Installable()
    stub_environment(model)
    model.available = False
    assert model.install_dependencies(log=lambda line: None)
    assert model.check_dependencies() and model.available
    assert model.env.info()["package"] == "fake==1.0"
    (model.weights_dir / "weights.bin").write_bytes(b"123")
    assert model.installed_size() > 3

    assert model.uninstall_dependencies()
    assert not model.env.exists() and not model.weights_dir.exists()
    assert not model.available
