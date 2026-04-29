## Voice Studio

A text-to-speech app powered by Microsoft Edge's TTS service.

### Requirements

- Internet connection required (voices are synthesized in the cloud)

### Windows

Download `VoiceStudio.exe` from the [latest release](https://github.com/justinyob/edge-tts-utils/releases/latest) and run it. No installation needed.

> **Tip:** Put `VoiceStudio.exe` in its own folder (e.g. `C:\Users\<you>\VoiceStudio\`) before running it. The app writes `settings.json` and `voice_studio.log` next to the executable, and the auto-updater downloads its replacement into the same folder. Keeping it in a dedicated directory avoids cluttering Downloads or Desktop with these files.

### Linux

Install dependencies first:

```
sudo apt install ffmpeg python3-tk     # Debian/Ubuntu
sudo pacman -S ffmpeg tk               # Arch
```

Then run:

```
chmod +x VoiceStudio
./VoiceStudio
```

### Usage

The window has three areas:

- **Voice browser** (left) — the full list of English voices loads after a brief "Loading voices..." message. Type in the search box at the top to filter by voice name or locale (e.g. `Jenny`, `en-GB`). Click a row to select that voice — the row stays highlighted. The ▶ button on each row plays a short sample so you can compare voices before committing.
- **Text panel** (right, top) — where you put the script you want to narrate.
  - **📂 Import file** opens a `.txt` or `.docx` file and drops its contents into the textbox. Tables in Word documents are skipped; everything else (paragraphs and headings) comes through. The filename appears above the textbox once loaded.
  - You can also paste or type directly. The word count in the top-right updates as you type.
  - **▶ Preview** narrates the first 100 words of whatever's in the textbox using the selected voice and current prosody. Use it to spot-check pronunciation before exporting a long file.
  - **🎵 Export audio...** opens a save dialog. Pick a destination, optionally tick **Also export subtitles (.srt)**, then **Export**. A progress bar tracks chunked synthesis (long documents are split into ~500-word pieces and stitched together). **✕ Cancel** stops cleanly. When it finishes, you get a dialog with the duration and file size.
- **Prosody panel** (right, bottom) — three sliders that control the selected voice:
  - **Rate** (-50% to +100%) — speed
  - **Volume** (-50% to +50%) — loudness
  - **Pitch** (-50 to +50 Hz) — vocal pitch
  - **Reset to defaults** zeros all three. Changes apply to the next preview or export — there's no apply button.

**Status bar** at the bottom: a Dark mode toggle and a **⟳ Check for updates** button that polls GitHub for a newer release.

**Settings persist across launches.** Your last-used voice, the three prosody values, window size, and theme are saved next to the binary in `settings.json` and restored automatically on the next run.

**Tips:**

- Need to pick a voice? Hit ▶ on a few candidate rows in the voice browser — the preview uses your current prosody, so you'll hear exactly how that voice will sound in the export.
- Exporting a full audiobook? Set the prosody first, do a 100-word preview, then run the full export. The progress bar will tell you how far along you are; large files can take several minutes.
- The SRT subtitle file uses real word-boundary timestamps from the TTS engine, so it stays accurate across the whole document even with chunked synthesis.
- If anything goes wrong (lost connection mid-export, can't write the file, etc.) the app shows a clear error dialog rather than crashing. Full tracebacks are written to `voice_studio.log` next to the binary if you ever need to debug.

### For developers building from source

1. Python 3.11+ required
2. `pip install -r requirements.txt`
3. **Windows only:** download a static `ffmpeg.exe` build (e.g. from https://www.gyan.dev/ffmpeg/builds/) and place it in the project root
4. `python build.py`

The built binary lands in `dist/VoiceStudio` (Linux) or `dist\VoiceStudio.exe` (Windows).

### Publishing an update

1. Bump `APP_VERSION` in `config.py`
2. Run `python build.py`
3. Create a GitHub Release tagged `v{version}` (e.g. `v1.1.0`)
4. Upload `VoiceStudio.exe` / `VoiceStudio` as a release asset with exactly that filename

The auto-updater in shipped builds polls GitHub Releases on launch and offers an in-app update when a newer tag is found.
