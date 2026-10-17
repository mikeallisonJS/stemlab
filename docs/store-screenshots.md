# Store screenshots: capture guide

The Microsoft Store requires at least one screenshot and will not accept a
submission without one. This is the shot list, in the order they should appear
in the listing.

You have to take these yourself; they need the app actually running.
`STEMLAB_DEBUG_SCREENSHOT=<file.png>` makes the desktop app save a screenshot
of its window and quit, which gives a clean frame at the window's own size;
for the sizes below, set the window to the target size first or capture the
display.

## Requirements

- **Format**: PNG.
- **Size**: 1366 × 768 or 1920 × 1080. Use one size for all of them; mixed
  aspect ratios look broken in the Store's carousel.
- **Count**: up to 10. Four good ones beat ten repetitive ones.
- **No chrome you did not mean to ship**: no other windows, no notification
  toasts, no personal data in the frame.
- Save them as `docs/store/screenshot-1.png`, `screenshot-2.png`, ... so
  `scripts/store_setup_wizard.sh` finds them.

## Before you start

- Stemlab follows the system theme. Pick light or dark and stay there; a
  carousel that flips between the two looks accidental.
- Set display scaling to 100% so text renders sharply at native resolution.
- Have a run already finished, so the results panel shows real stems with
  waveforms rather than an empty state. Use a track you have the rights to
  show the name of.
- Check every frame for anything you would not publish: file paths with your
  username, window titles from real work.

## The shots

### 1. A finished separation: the hero image

The whole product in one frame: the recipe graph on one side, the results
with the stems listed and playable on the other, a real track name. This is
the only screenshot most people will look at. It has to answer "what does
this do" without a caption.

### 2. The recipe graph

A recipe with more than one step, such as `vocals-instrumental`: separate,
subtract, a second model, export. This is the screenshot that says *this is
not a one-button vocal remover*.

### 3. The model list

The curated models with their published scores, and the chip showing which
backend each runs on. It carries the "any model, on evidence" story visually.

### 4. A model's parameter form

One model's settings open: overlap, shifts, segment, device. For the people
who want every knob, this is the proof.

### 5. The batch queue *(optional)*

Several files queued and one running, with progress. Include if you have a
convincing set of file names that are not private.

### 6. Doctor, in the Models view *(optional)*

The detected OS, GPU and runtime flavor. Reassures the GPU owners that their
hardware is used.

## Captions

Partner Center allows a caption per screenshot. Write them; they are read
more than the description body. Keep each under about 80 characters:

1. "Drop in a song, get the stems: all on your own PC"
2. "Recipes chain models, subtraction and ensembles into one repeatable graph"
3. "Every curated model with its published quality scores"
4. "Every parameter the model accepts, exposed"
5. "Queue a folder and let it run"
6. "Detects your GPU and installs the matching runtime"

## Where to put them

Screenshots do not need to be committed; Partner Center hosts them. Keeping
them in `docs/store/` alongside the logos makes the next submission a copy
rather than a photo shoot.
