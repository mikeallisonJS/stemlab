# Microsoft Store listing copy

Draft content for the Partner Center submission. Paste into the matching
fields; the headings below are Partner Center's own field names.
`scripts/store_setup_wizard.sh` walks the submission and points here.

Everything here is checked against the code, not aspirational. If a claim
stops being true, change it here and in the listing.

---

## Short description

*(Partner Center limit: 1,000 characters, but only the first 270 show in some
Store views, so Microsoft recommends staying under 270. This one is 196.)*

> Stem separation for people who want every knob. Run any separation model on
> your own PC, chain models into recipes, and export the stems. Nothing is
> uploaded: no cloud, no account, no subscription.

---

## Description

*(Partner Center limit: 10,000 characters.)*

> **A stem separation workbench that runs on your own computer.**
>
> Drop in a song and pull it apart: vocals, drums, bass, guitar, piano, and
> whatever else the model you choose can isolate. Stemlab runs the open
> separation models the community benchmarks against, including Demucs and the
> Mel-Band RoFormer, SCNet and BS-RoFormer families, on your own hardware. Pick
> a model from a list that shows each one's published quality scores, or add a
> checkpoint of your own.
>
> **Recipes, not presets.** A separation in Stemlab is a graph of steps:
> separate with one model, subtract the result from the mix to get a
> sample-exact instrumental, run a second model on what is left, average two
> models' opinions, clean up, analyze, and export. Save the graph as a recipe
> and run it on any file, or on a whole folder through the batch queue. Every
> run writes a `run.json` with the exact parameters and model checksums it
> used, so a result can always be reproduced.
>
> **Every parameter exposed.** Overlap, shifts, segment length, chunking,
> precision, device: each model's settings are shown as a form built from what
> that model actually accepts. Nothing is hidden behind a quality slider.
>
> **What you get**
>
> - **Any model.** Curated open models with their published scores, and your
>   own checkpoints alongside them.
> - **Recipes.** Separate, subtract, ensemble, post-process, analyze and export
>   steps composed into a graph you can rerun.
> - **Batch queue.** Line up files and let them run.
> - **Reproducible runs.** Resolved parameters and model checksums saved with
>   every result.
> - **GPU acceleration** on NVIDIA and AMD cards, with a processor fallback on
>   everything else. Stemlab detects your hardware and installs the matching
>   build of the model runtime.
> - **Exports** as FLAC, WAV or MP3, named the way you ask.
>
> **Privacy**
>
> Stemlab processes audio on your machine and only there. It has no account,
> no backend of its own, and no analytics or telemetry of any kind. Your audio
> files, stems, recipes and settings are plain files in your own user folders,
> and deleting those folders deletes all of it.
>
> **What Stemlab downloads, and when**
>
> The installer contains the application and its audio engine, but not the
> Python runtime and machine-learning libraries the engine runs on, which
> would add several gigabytes to every download. On first start, Stemlab
> fetches a Python runtime and the engine's libraries from their public
> package repositories, then offers to install the build of PyTorch that
> matches your graphics card. Each download is shown with its progress; none of
> them starts without the app telling you. Separation models are downloaded
> individually when you first choose them, with their size shown beforehand,
> from the public repositories their authors publish them on. After that,
> separation works with the network switched off. Stemlab also checks its own
> update feed every few hours and downloads a newer version in the background,
> and asks before it restarts.
>
> **Requirements**
>
> Windows 10 or 11, 64-bit. An internet connection for the first start and for
> model downloads. Disk space for the runtime (around 1 GB on the processor,
> several gigabytes with a GPU build) plus the models you choose, which range
> from under 100 MB to over 1 GB each. 16 GB of memory is recommended for the
> larger models; a GPU makes separation many times faster but is not required.
>
> Stemlab is free and open source.

*(End of the Description field. Everything above this line, and nothing below
it, goes in the box.)*

**Keep URLs out of the Description.** Microsoft's guidance is explicit: *"Do
not include HTML, code snippets, or URLs in the description field. Instead,
provide support, privacy policy, and website links in their designated
submission fields."* The repository link belongs in **Website**, set below.

---

## Product features

*(Short bullets, 200 characters each.)*

- Run any open stem separation model on your own PC, or add your own checkpoints
- Models listed with their published quality scores, so you can pick on evidence
- Recipes: chain separate, subtract, ensemble, post-process and export steps, and rerun them on any file
- Every model parameter exposed, with a form built from what the model accepts
- Batch queue for whole folders
- Reproducible: each run saves its exact parameters and model checksums
- GPU acceleration on NVIDIA and AMD, processor fallback everywhere else
- No account, no cloud, no telemetry: audio never leaves your machine

---

## Partner Center fields

| Field | Value |
| --- | --- |
| Category | Music |
| Subcategory | Pick from whatever Partner Center offers under Music; the list changes, so choose at submission time rather than trusting a value written here |
| Privacy policy URL | `https://github.com/mikeallisonJS/Stemlab/blob/main/docs/privacy-policy.md` |
| Website | `https://github.com/mikeallisonJS/Stemlab` |
| Support contact | `https://github.com/mikeallisonJS/Stemlab/issues` |
| Install switches | `/S` |
| Uninstall switches | `/S` |
| Package URL | `https://downloads.mikeallisonjs.com/stemlab/Stemlab-Setup-X.Y.Z.exe`, the file the tag build publishes to R2 |

**Not the GitHub Release asset URL.** It answers `302` and redirects to a
signed link that expires within the hour; Partner Center rejects it with "The
package URL redirects to another URL." The R2 copy exists for this reason, and
`scripts/store_submit.py` checks it answers `200` before touching the draft.

**The switches.** The installer is NSIS, built by electron-builder.
`/S` installs silently for the current user, with no UI, no prompts and no
elevation; the uninstaller honours the same switch. There is no separate
"suppress message boxes" or "no restart" switch to add.

### Product declarations

MSI/EXE submissions have no capability manifest, so there is nothing to
declare about files or devices here; that belongs in System requirements
below. The declarations page offers exactly four boxes:

| Declaration | Stemlab | Why |
| --- | --- | --- |
| Depends on non-Microsoft drivers or NT services | **No** | Installs no driver and no service. The engine is a local process the app starts and stops; GPU work uses whatever driver is already present, with a processor fallback. |
| Tested to meet accessibility guidelines | **No** | This asks whether the UI has been engineered and verified for accessibility: accessible names, keyboard navigation, contrast, checked with Narrator and Inspect. That pass has not been done. Microsoft: "Do not list your app as accessible unless you have specifically engineered and tested it for that purpose." |
| Supports pen and ink input | **No** | Mouse and keyboard. |
| Incorporates generative AI features | **No** | Separation models take a mix apart into the stems that were already in it; they transform audio rather than generate new content. Revisit if a model that synthesizes audio is ever added. |

### System requirements

Optional, and softer than it reads: customers whose device lacks a stated
requirement can still download the app, but **they cannot rate or review it
on that device**. Every unnecessary minimum quietly suppresses reviews, which a
new listing cannot afford. Mark what is genuinely needed and nothing else.

| Item | Setting | Why |
| --- | --- | --- |
| Memory | **Recommended, 16 GB** | Not a minimum. Small models run in far less; the large RoFormer models on the processor want this much. |
| Processor | **Recommended, 4+ cores** | Processor separation is slow on fewer; nothing refuses to run. |
| DirectX, Dedicated GPU Memory, Graphics | **Leave blank** | GPU is optional acceleration with a processor fallback throughout. A minimum here would misdescribe the app and silence reviews from the majority who have no dedicated GPU. |
| Microphone, Keyboard, Mouse, Touch screen, Camera, NFC, Bluetooth LE, Telephony | **No** | None apply; the app is used with whatever pointing device is present. |

### Additional system requirements

Free text, 200 characters per entry, 11 entries maximum:

- `64-bit (x64) Windows 10 or 11.`
- `Internet connection on first start: Stemlab downloads its Python runtime and engine libraries (about 1 GB, more with a GPU build), and each separation model when first chosen.`
- `Disk space for the runtime plus the models you choose, from under 100 MB to over 1 GB each.`

### Age rating

Complete the questionnaire. Stemlab is a utility with no user-generated
content shared with anyone, no social features and no ads, so it should come
out at the lowest rating.

### Notes for certification

*(2,000 character limit. The draft below is about 1,700.)*

This field carries more risk than any checkbox on the page. Microsoft warns
that "apps that appear to be incomplete may fail certification", and Stemlab
downloads its runtime on first start and cannot separate anything until a
model has downloaded. A tester who installs it, waits, and cannot make it work
is a plausible rejection. Fill this in.

> Stemlab is a stem separation workbench. No account or login is required.
>
> FIRST START: the installer contains the app and its audio engine but not the
> Python runtime and machine-learning libraries the engine runs on. On first
> launch Stemlab downloads a Python runtime from GitHub and the engine's
> libraries from the Python Package Index (about 1 GB), showing progress on a
> loading screen, then offers to install the build of PyTorch for the
> machine's GPU; "CPU" is fine for testing. This is disclosed in the listing.
> Please let the first start finish before testing; it takes a few minutes on
> a fast connection.
>
> TO TEST A SEPARATION: open the Models view and fetch "htdemucs", the
> smallest curated model (about 80 MB, with its size shown first). Then drop
> any audio file onto the app, choose the "four-stems" recipe and run it. The
> stems (vocals, drums, bass, other) are listed in the Results view and
> written to the outputs folder shown there. On the processor a three-minute
> song takes a few minutes.
>
> NETWORK: all separation runs locally. Stemlab contacts the internet only to
> download the runtime, libraries and models described above, and to check
> its own update feed. It uploads nothing and has no backend service.
>
> Notes entered [TODAY'S DATE].

Fill in the date. Microsoft asks for it explicitly, so testers can judge
whether a problem you mention was temporary.

### Search terms

Listed in priority order. Microsoft's MSI/EXE listing page documents no
keywords field at all, and the familiar seven-term cap belongs to the MSIX
listing, so treat the count as unknown until you see the field. If it caps,
take them from the top.

1. `stem separation`
2. `vocal remover`
3. `demucs`
4. `karaoke`
5. `instrumental`
6. `acapella`
7. `audio separation`
8. `roformer`
9. `music production`
10. `offline`

---

## A note on the first-start download

Do not leave this out to keep the listing tidy. The Python runtime and the
model libraries are executable code that arrives after installation, and a
reviewer who finds that undisclosed is entitled to read it as dynamically
included code, which is a policy problem. Stated plainly and up front, with
its size, its sources and the reason for it, it reads as a considered design
decision, which is what it is. If certification still objects, the fix is a
product change rather than copy: bundling the runtime into the installer,
which `app/scripts/prepare-engine.mjs` is the place to grow.
