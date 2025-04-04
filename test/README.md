# Test Files

This directory contains test files for CaptainStems.

## Sample Audio

To test the application, you'll need sample audio files. You can use your own audio files, or download public domain or Creative Commons licensed music from sites like:

- [Free Music Archive](https://freemusicarchive.org/)
- [Incompetech](https://incompetech.com/music/royalty-free/music.html)
- [SampleSwap](https://sampleswap.org/)

## Testing Process

1. Download a test audio file (ideally in .mp3, .wav, or .flac format)
2. Drag and drop the file into the CaptainStems application
3. Process the file with Demucs v4
4. Check the output stems for quality

## Expected Results

When using Demucs v4 with the "two-stems" option, you should get:

- `vocals.mp3` - Contains the vocals/lead elements
- `no_vocals.mp3` - Contains the instrumental/backing track
