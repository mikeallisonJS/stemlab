# Tests

This directory contains the test suite for CaptainStems.

## Running the tests

```
pip install -r requirements-dev.txt
python -m pytest
```

These tests need no installed model and no audio files: they generate short test tones and use a stand-in
model. They run without a display (Qt's offscreen platform) and keep away from your real application data
by pointing `CAPTAINSTEMS_HOME` at a temporary directory.

| File               | What it covers                                                        |
| ------------------ | --------------------------------------------------------------------- |
| `test_process.py`  | Running subprocesses, cancellation, progress bar parsing              |
| `test_ffmpeg.py`   | Decoding, validation and export in every format                       |
| `test_audio.py`    | Waveform envelopes                                                    |
| `test_envs.py`     | Isolated model environments and their install state                   |
| `test_models.py`   | Model catalog, command lines, the shared processing workflow          |
| `test_pipeline.py` | Separation workflow and export                                        |
| `test_settings.py` | Persistent preferences                                                |
| `test_ui.py`       | Main window, file queue, results window and dialogs                   |

## Testing the real models

`test_integration.py` runs every installed model on a short synthetic mix and checks the stems. It is
skipped unless you enable it, and models that are not installed are skipped individually:

```
python captain.py --install-model all

# Windows (PowerShell)
$env:CAPTAINSTEMS_INTEGRATION = "1"; python -m pytest test/test_integration.py

# macOS / Linux
CAPTAINSTEMS_INTEGRATION=1 python -m pytest test/test_integration.py
```

The first run downloads the model weights.

## Sample Audio

To judge separation quality you need real music. You can use your own audio files, or download public
domain or Creative Commons licensed music from sites like:

- [Free Music Archive](https://freemusicarchive.org/)
- [Incompetech](https://incompetech.com/music/royalty-free/music.html)
- [SampleSwap](https://sampleswap.org/)

Audio files in `test/samples/` are ignored by git.

## Manual Testing Process

1. Download a test audio file (ideally in .mp3, .wav, or .flac format)
2. Drag and drop the file into the CaptainStems application
3. Process the file with Demucs v4
4. Check the output stems for quality

## Expected Results

When using Demucs v4 with the "vocals/instrumental only" option, saving all files gives you:

- `vocals.wav` - Contains the vocals/lead elements
- `no_vocals.wav` - Contains the instrumental/backing track

(with the extension of the export format you selected)
