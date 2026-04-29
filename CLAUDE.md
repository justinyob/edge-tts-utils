# Edge-TTS Voice Studio — Claude Code Build Guide

## Project overview

A local desktop app for Windows (primary) and Linux that wraps Microsoft's Edge TTS service via the `edge-tts` Python library. Designed for a non-technical writer to browse voices, preview samples, import manuscript files, and export audiobook-quality MP3s with optional SRT subtitles.

**Key constraints:**
- Internet required (edge-tts calls Microsoft's WebSocket TTS service)
- UI must never freeze — all TTS and file I/O runs off the main thread
- Long document support is critical — full chapter synthesis with progress reporting
- Single-file executable output for distribution (no Python install required on target machine)

---

## Tech stack

| Layer | Library | Notes |
|---|---|---|
| UI | `customtkinter` | Modern Tkinter wrapper, dark/light mode, cross-platform |
| TTS | `edge-tts` | Async, WebSocket-based, ~400 voices |
| Audio playback | `pygame` | `pygame.mixer` for MP3 play/pause/stop |
| DOCX reading | `python-docx` | Paragraph extraction, strip formatting |
| TXT encoding | `chardet` | Detect encoding before read |
| Audio concat | `pydub` + `ffmpeg` | Join audio chunks for long docs |
| Config persistence | `json` (stdlib) | Save/load user settings |
| Temp files | `tempfile` (stdlib) | Preview audio lifecycle management |
| Packaging | `pyinstaller` | `--onefile --windowed` for both platforms |
| Auto-update | `requests` + `packaging` | GitHub Releases API, semver comparison |

---

## Project structure

```
voice_studio/
├── main.py                  # Entry point — launches app window
├── config.py                # Constants, defaults, settings load/save
├── requirements.txt
├── build_windows.spec       # PyInstaller spec for Windows
├── build_linux.spec         # PyInstaller spec for Linux
├── assets/
│   └── icon.ico             # App icon (Windows)
├── core/
│   ├── __init__.py
│   ├── tts_engine.py        # TTS synthesis wrapper + chunking logic
│   ├── voice_manager.py     # Voice list fetch, cache, filter
│   ├── audio_player.py      # pygame.mixer wrapper
│   └── file_reader.py       # TXT + DOCX → plain text
├── ui/
│   ├── __init__.py
│   ├── app_window.py        # Root window, layout, tab management
│   ├── voice_browser.py     # Voice list panel + search + sample preview
│   ├── prosody_panel.py     # Rate/pitch/volume sliders
│   ├── text_panel.py        # File import, text area, preview, export
│   └── progress_bar.py      # Reusable progress + cancel widget
└── utils/
    ├── __init__.py
    ├── async_bridge.py      # asyncio-in-thread + root.after() callbacks
    ├── text_chunker.py      # Split long text into synthesis-safe chunks
    ├── paths.py             # resource_path() for frozen vs dev environments
    └── updater.py           # GitHub Releases version check + self-update logic
```

---

## config.py — constants and defaults

```python
APP_NAME = "Voice Studio"
APP_VERSION = "1.0.0"

DEFAULT_SAMPLE_TEXT = "The quick brown fox jumps over the lazy dog. She sells seashells by the seashore. How much wood would a woodchuck chuck?"

# Prosody defaults (edge-tts format)
DEFAULT_RATE   = "+0%"
DEFAULT_VOLUME = "+0%"
DEFAULT_PITCH  = "+0Hz"

# Prosody slider ranges
RATE_MIN, RATE_MAX     = -50, 100   # percent
VOLUME_MIN, VOLUME_MAX = -50, 50    # percent
PITCH_MIN, PITCH_MAX   = -50, 50    # Hz

# Chunking
CHUNK_SIZE_WORDS = 500   # target words per synthesis chunk
CHUNK_OVERLAP    = 0     # no overlap (sentence-boundary split)

SETTINGS_FILE = "settings.json"
TEMP_DIR_PREFIX = "voice_studio_"

ENGLISH_LOCALE_PREFIX = "en-"

# Auto-updater
GITHUB_REPO = "justinyob/edge-tts-utils"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_TIMEOUT = 5   # seconds — fail fast, never block launch
# Asset name pattern in GitHub Release — must match what PyInstaller outputs
WINDOWS_ASSET_NAME = "VoiceStudio.exe"
LINUX_ASSET_NAME   = "VoiceStudio"
```

---

## Phase 0 — Scaffold and environment

**Goal:** Repo and venv ready, all dependencies installable, app launches to an empty window.

```bash
# Bootstrap
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install edge-tts customtkinter python-docx pygame pydub chardet pyinstaller requests packaging
pip freeze > requirements.txt

# Verify edge-tts works
python -c "import asyncio, edge_tts; asyncio.run(edge_tts.list_voices())"
```

**Deliverable:** `main.py` opens a `customtkinter.CTk()` window with `APP_NAME` title and closes cleanly.

---

## Phase 1 — Core engine modules

Build and unit-test each module independently before wiring to UI.

### 1a. `utils/async_bridge.py`

Provides `run_async(coro, callback, error_callback)`.

- Spins up a dedicated background thread with its own `asyncio` event loop (do this once at app start, reuse it)
- Submits coroutines via `asyncio.run_coroutine_threadsafe()`
- Delivers results back to the Tkinter main thread via `root.after(0, callback, result)`
- `error_callback(exc)` is called on exceptions — never let exceptions silently die in threads

```python
# Usage pattern throughout the app
bridge.run_async(
    tts_engine.synthesize(text, voice, rate, pitch, volume),
    on_complete=lambda result: root.after(0, handle_done, result),
    on_error=lambda exc: root.after(0, show_error_dialog, str(exc))
)
```

### 1b. `core/voice_manager.py`

```python
class VoiceManager:
    async def fetch_voices(self) -> list[dict]
    # Calls edge_tts.list_voices()
    # Filters to locales starting with "en-"
    # Caches result in self._voices after first fetch
    # Returns list of dicts with keys: Name, ShortName, Gender, Locale, VoicePersonalities

    def get_voices(self) -> list[dict]
    # Returns cached list; raises if fetch not yet called

    def filter(self, query: str) -> list[dict]
    # Case-insensitive search against ShortName and Locale
```

**Test:** fetch voices, assert list non-empty, assert all locales start with "en-".

### 1c. `utils/text_chunker.py`

```python
def chunk_text(text: str, max_words: int = CHUNK_SIZE_WORDS) -> list[str]:
    """
    Split text into chunks at sentence boundaries.
    Never split mid-sentence.
    Each chunk <= max_words words.
    Preserve paragraph structure where possible.
    Returns list of string chunks.
    """
```

**Test cases:**
- Short text (< max_words) → returns single-item list
- Long text → all chunks ≤ max_words words, no chunk ends mid-sentence
- Text with multiple paragraphs → paragraph breaks respected

### 1d. `core/tts_engine.py`

```python
class TTSEngine:
    async def synthesize(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
        output_path: str,         # full path to write MP3
        srt_path: str | None,     # write SRT if provided
        progress_callback: Callable[[int, int], None] | None = None
        # progress_callback(current_chunk, total_chunks)
    ) -> SynthesisResult

    async def synthesize_preview(
        self,
        text: str,
        voice: str,
        rate: str,
        pitch: str,
        volume: str,
    ) -> str  # returns temp file path
```

**Implementation notes:**

- Call `chunk_text()` on input
- For each chunk, call `edge_tts.Communicate(chunk, voice, rate=rate, pitch=pitch, volume=volume)`
- Stream to individual temp MP3 files
- Use `pydub.AudioSegment` to concatenate chunk files into final output
- Call `progress_callback(i, total)` after each chunk completes
- SRT: collect word boundary data from edge-tts during synthesis, adjust timestamps per chunk offset, write combined SRT
- On cancellation (check a `threading.Event` passed in), stop cleanly and clean up temp files

**SynthesisResult:**
```python
@dataclass
class SynthesisResult:
    output_path: str
    srt_path: str | None
    duration_seconds: float
    chunk_count: int
```

### 1e. `core/audio_player.py`

```python
class AudioPlayer:
    def __init__(self): ...          # initialize pygame.mixer
    def load(self, path: str): ...   # load MP3 file
    def play(self): ...
    def pause(self): ...
    def stop(self): ...
    def is_playing(self) -> bool: ...
    def cleanup(self): ...           # stop + delete temp file
```

**Note:** Call `pygame.mixer.init()` once. Use `pygame.mixer.music` for streaming MP3 (memory-efficient for large files).

### 1f. `core/file_reader.py`

```python
def read_file(path: str) -> str:
    """
    .txt: detect encoding with chardet, read as plain text
    .docx: extract paragraphs with python-docx, join with \n\n
           Skip tables (too complex for TTS), include heading text
    Returns clean plain text string.
    Raises ValueError for unsupported extensions.
    Raises UnicodeDecodeError-safe wrapper for unreadable files.
    """
```

---

## Phase 2 — Voice browser UI

**File:** `ui/voice_browser.py`

### Layout

```
┌─────────────────────────────────────────┐
│ [Search box                           ] │
├────────────────┬────────┬──────────────┤
│ Voice name     │ Locale │ Gender  [▶] │
│ Voice name     │ Locale │ Gender  [▶] │
│ ...            │        │             │
└────────────────┴────────┴──────────────┘
```

### Behavior

- On mount: trigger `VoiceManager.fetch_voices()` via async bridge, show loading spinner until complete
- Scrollable list (use `CTkScrollableFrame`)
- Search box filters in real time (no debounce needed, list is small after English filter)
- Clicking a row: highlights it, fires `on_voice_selected(voice_name: str)` callback
- `[▶]` play button per row:
  - Synthesizes `DEFAULT_SAMPLE_TEXT` using current prosody values
  - Shows spinner on that row's button during generation
  - Plays result via `AudioPlayer`
  - If another preview is playing, stops it first

### Interface

```python
class VoiceBrowserPanel(ctk.CTkFrame):
    def __init__(self, parent, voice_manager, audio_player, async_bridge, on_voice_selected): ...
    def get_selected_voice(self) -> str | None: ...
    def set_prosody_getter(self, fn: Callable[[], dict]): ...
    # fn returns {"rate": str, "pitch": str, "volume": str}
```

---

## Phase 3 — Prosody panel UI

**File:** `ui/prosody_panel.py`

### Layout

```
Rate    [────●────────────] +0%
Volume  [────────●────────] +0%
Pitch   [────────●────────] +0Hz
                      [Reset to defaults]
```

### Behavior

- Three `CTkSlider` widgets with live value labels
- Values formatted as edge-tts strings: `+25%`, `-10%`, `+5Hz`
- Reset button restores all to defaults from `config.py`
- All changes are immediate — no apply button

### Interface

```python
class ProsodyPanel(ctk.CTkFrame):
    def get_prosody(self) -> dict:
        return {"rate": "+25%", "volume": "+0%", "pitch": "-5Hz"}
    def reset(self): ...
```

---

## Phase 4 — Text and file panel UI

**File:** `ui/text_panel.py`

### Layout

```
[📂 Import file]                    [word count: 0 words]
┌────────────────────────────────────────────────────────┐
│                                                        │
│  (large scrollable text area)                          │
│                                                        │
└────────────────────────────────────────────────────────┘
[▶ Preview (first 100 words)]          [🎵 Export audio...]
─────────────────────────────────────────────────────────
[Progress bar                              ] [✕ Cancel]
Status: Ready
```

### Behavior

**Import file:**
- File dialog: `filetypes=[("Text files", "*.txt *.docx")]`
- On selection: call `file_reader.read_file(path)`, populate text area
- Filename displayed above text area after import

**Word count:**
- Updated on text change (debounce 300ms)

**Preview button:**
- Takes first 100 words of current text area content
- Synthesizes via `TTSEngine.synthesize_preview()`
- Plays result via `AudioPlayer`

**Export audio button:**
- Validates: voice selected, text non-empty
- Shows save dialog: `defaultextension=".mp3"`, suggest filename from source file if available
- Checkbox in dialog: "Also export subtitles (.srt)"
- If SRT checked: auto-name `<same_name>.srt` alongside MP3 (no second dialog)
- Kicks off full synthesis with progress updates
- On completion: show success message with file size and estimated duration

**Progress:**
- `CTkProgressBar` + status label
- Updated via `root.after()` callbacks from async bridge
- Cancel button: sets cancellation event on engine, cleans up temp files

### Interface

```python
class TextPanel(ctk.CTkFrame):
    def __init__(self, parent, tts_engine, audio_player, async_bridge,
                 get_voice: Callable, get_prosody: Callable): ...
```

---

## Phase 5 — Root window and layout

**File:** `ui/app_window.py`

### Layout (two-column)

```
┌──────────────────┬─────────────────────────────────┐
│                  │                                  │
│  Voice browser   │  Text & file panel               │
│  (left column)   │  (right column)                  │
│                  │                                  │
│                  ├─────────────────────────────────┤
│                  │  Prosody panel (bottom right)    │
└──────────────────┴─────────────────────────────────┘
[Dark/Light mode toggle]                 [v1.0.0]
```

### App startup sequence

```python
# main.py
1. Create CTk root window, set title/size/min-size
2. Initialize AsyncBridge (starts background asyncio thread)
3. Initialize VoiceManager, TTSEngine, AudioPlayer, FileReader
4. Load settings from settings.json (last voice, prosody, window size)
5. Build UI panels, wire callbacks
6. Kick off VoiceManager.fetch_voices() via AsyncBridge
7. Kick off update check in background thread (non-blocking, silent on failure)
8. root.mainloop()
9. On close: save settings, AudioPlayer.cleanup(), AsyncBridge.shutdown()
```

### Settings persistence

```python
# config.py
def load_settings() -> dict: ...   # reads settings.json, returns defaults if missing
def save_settings(data: dict): ... # writes settings.json atomically

# Keys:
{
  "last_voice": "en-US-JennyNeural",
  "rate": "+0%",
  "volume": "+0%",
  "pitch": "+0Hz",
  "window_width": 1100,
  "window_height": 700,
  "theme": "dark"
}
```

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Import file |
| `Ctrl+S` | Export audio |
| `Space` | Play/pause current preview |
| `Escape` | Cancel active synthesis |

---

## Phase 6 — Error handling

Errors should never surface as raw Python tracebacks to the user.

### Error categories and handling

| Error | Cause | User message |
|---|---|---|
| `NetworkError` | Microsoft TTS service unreachable | "Could not connect to the text-to-speech service. Please check your internet connection and try again." |
| `VoiceFetchError` | Voice list fetch fails | "Could not load voice list. Check your connection and restart the app." |
| `FileReadError` | Unsupported format, encoding failure | "Could not read this file. Supported formats: .txt, .docx" |
| `SynthesisError` | Mid-generation failure | "Audio generation failed. The service may be temporarily unavailable. Try again in a moment." |
| `DiskWriteError` | Save path not writable | "Could not save the file. Check that you have write permission for the selected folder." |

Show errors as `CTkMessageBox` (or a simple `CTkToplevel` dialog). Log full tracebacks to a `voice_studio.log` file in the app directory for debugging.

---

## Phase 7 — Auto-updater

### Overview

The app checks GitHub Releases for a newer version on every launch (silent background thread) and also via a manual "Check for updates" menu item. When an update is found, the user is prompted. On confirmation, the new binary is downloaded and a small helper script is used to replace the running executable after the app exits — solving the Windows restriction that prevents overwriting a running `.exe`.

### GitHub release convention (your side)

Every release must follow this pattern for the updater to work:

- Tag format: `v1.2.3` (semver, `v` prefix required)
- Attach the built `VoiceStudio.exe` as a release asset with the exact filename `VoiceStudio.exe`
- Attach the Linux binary as `VoiceStudio` (no extension)
- The GitHub API will expose the download URL automatically

### `utils/updater.py`

```python
import sys, os, platform, subprocess, tempfile, threading
import requests
from packaging.version import Version
from config import APP_VERSION, GITHUB_API_RELEASES, WINDOWS_ASSET_NAME, LINUX_ASSET_NAME, UPDATE_CHECK_TIMEOUT

@dataclass
class UpdateInfo:
    available: bool
    latest_version: str        # e.g. "1.2.3" (v prefix stripped)
    download_url: str | None
    release_notes: str | None  # body of the GitHub release

def check_for_update() -> UpdateInfo:
    """
    Calls GitHub Releases API.
    Returns UpdateInfo(available=False) silently on any network/parse error.
    Never raises — caller should never need to handle exceptions from this.
    """
    try:
        resp = requests.get(GITHUB_API_RELEASES, timeout=UPDATE_CHECK_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data["tag_name"].lstrip("v")
        if Version(latest_tag) > Version(APP_VERSION):
            asset_name = WINDOWS_ASSET_NAME if platform.system() == "Windows" else LINUX_ASSET_NAME
            url = next(
                (a["browser_download_url"] for a in data["assets"] if a["name"] == asset_name),
                None
            )
            return UpdateInfo(
                available=True,
                latest_version=latest_tag,
                download_url=url,
                release_notes=data.get("body", "")
            )
    except Exception:
        pass  # silent failure — update check must never crash the app
    return UpdateInfo(available=False, latest_version=APP_VERSION, download_url=None, release_notes=None)

def download_update(url: str, progress_callback: Callable[[int, int], None]) -> str:
    """
    Downloads the new binary to a temp file.
    progress_callback(bytes_downloaded, total_bytes)
    Returns path to downloaded temp file.
    Raises requests.RequestException on failure.
    """

def apply_update_windows(new_exe_path: str):
    """
    Windows self-replace strategy:
    1. Write _updater.py to temp dir
    2. Launch _updater.py via pythonw / the bundled Python in _MEIPASS
       with args: --wait-pid <current PID> --src <new_exe_path> --dst <current exe path> --relaunch
    3. Exit the main app — the updater takes over
    """

def apply_update_linux(new_exe_path: str):
    """
    Linux: simpler — can overwrite directly since the file isn't locked.
    1. Copy new binary over current binary (os.replace)
    2. chmod +x
    3. subprocess.Popen to relaunch, then sys.exit()
    """
```

### `_updater.py` — Windows helper script

This is a standalone script bundled with the PyInstaller exe (via `--add-data "_updater.py;."`). It runs as a separate process after the main app exits.

```python
"""
_updater.py — launched by the main app to complete a self-update on Windows.
Args: --wait-pid PID --src NEW_EXE_PATH --dst CURRENT_EXE_PATH [--relaunch]
"""
import sys, os, time, shutil, subprocess, argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-pid", type=int, required=True)
    parser.add_argument("--src", required=True)   # downloaded new exe
    parser.add_argument("--dst", required=True)   # current exe to replace
    parser.add_argument("--relaunch", action="store_true")
    args = parser.parse_args()

    # Wait for the main process to exit (poll every 200ms, timeout 30s)
    for _ in range(150):
        try:
            os.kill(args.wait_pid, 0)  # process still alive
            time.sleep(0.2)
        except OSError:
            break  # process gone

    # Replace the binary
    shutil.copy2(args.src, args.dst)
    os.remove(args.src)

    # Relaunch
    if args.relaunch:
        subprocess.Popen([args.dst])

if __name__ == "__main__":
    main()
```

**Bundling `_updater.py` in PyInstaller:**

```bash
# Add to PyInstaller command:
--add-data "_updater.py;."

# At runtime, locate it via:
updater_script = resource_path("_updater.py")

# Launch it with the Python interpreter bundled in _MEIPASS:
python_exe = os.path.join(sys._MEIPASS, "python.exe")   # Windows
# Fall back to sys.executable if not frozen
```

> **Note:** In `--onefile` mode, `sys._MEIPASS` is a temp dir that disappears when the app exits. `_updater.py` must be **copied to a separate temp location** before the app exits, so it survives long enough to do the replacement. Do this copy step inside `apply_update_windows()` before launching the subprocess.

### Update check threading model

```python
# In main.py, after UI is built:
def _bg_update_check():
    info = updater.check_for_update()
    if info.available:
        # Deliver result to main thread via root.after()
        root.after(0, show_update_dialog, info)

threading.Thread(target=_bg_update_check, daemon=True).start()
```

The thread is daemonized so it doesn't prevent app exit if still running.

### Update dialog UI

Shown when an update is found — either from the background check on launch or manual check.

```
┌─────────────────────────────────────────┐
│  Update available — v1.2.3              │
│                                         │
│  You're running v1.0.0.                 │
│  A new version is available.            │
│                                         │
│  Release notes:                         │
│  ┌─────────────────────────────────┐   │
│  │ (scrollable release notes text) │   │
│  └─────────────────────────────────┘   │
│                                         │
│  [────────────────────] 0%              │
│                                         │
│           [Update now]  [Later]         │
└─────────────────────────────────────────┘
```

- "Update now": begins download, progress bar fills, button disabled during download
- On download complete: inform user app will restart, call `apply_update_*()`, exit
- "Later": dismiss dialog, app continues normally — check will appear again next launch
- Download errors: show inline error message, re-enable "Update now" for retry

### Manual check — "Help > Check for updates" menu item

```python
# In app_window.py, add a simple menu or button in the status bar:
# "Help" → "Check for updates"
# Or a small "⟳ Check for updates" link in the bottom bar next to version label

def on_manual_update_check():
    # Disable the menu item / show spinner
    # Run check_for_update() in a thread
    # If available: show update dialog
    # If not: show brief "You're up to date (v{APP_VERSION})" toast/dialog
    # Re-enable menu item when done
```

### `config.py` additions for updater

```python
APP_VERSION = "1.0.0"   # MUST be updated before each PyInstaller build and GitHub release tag
```

**Critical workflow reminder for you (the developer):**

Before publishing a new release:
1. Bump `APP_VERSION` in `config.py`
2. Build the exe (`pyinstaller ...`)
3. Create GitHub Release with tag `v{APP_VERSION}` (e.g. `v1.1.0`)
4. Upload the built `VoiceStudio.exe` as a release asset with that exact filename

If the asset filename or tag format doesn't match, the updater will find the release but fail to locate the download URL and silently skip the update.

---

## Phase 8 — Packaging

### PyInstaller spec (both platforms share the same pattern)

```bash
# Windows (run on Windows)
pyinstaller --onefile --windowed \
  --name "VoiceStudio" \
  --icon assets/icon.ico \
  --collect-all customtkinter \
  --add-binary "ffmpeg.exe;." \
  --add-data "_updater.py;." \
  main.py

# Linux (run on Linux)
pyinstaller --onefile --windowed \
  --name "VoiceStudio" \
  --collect-all customtkinter \
  --add-data "_updater.py;." \
  main.py
```

### ffmpeg bundling

- **Windows:** Download static `ffmpeg.exe` build, place in project root, add `--add-binary` flag above. In `audio_player.py` / pydub setup, set `AudioSegment.converter` to the bundled path using `sys._MEIPASS` when frozen.
- **Linux:** Do not bundle — system ffmpeg is expected. Document in README: `sudo pacman -S ffmpeg` (Arch) or `sudo apt install ffmpeg` (Debian).

### Frozen path detection

```python
# utils/paths.py — use everywhere you need resource paths
import sys, os

def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)
```

### README minimum content

- Internet connection required
- Windows: just run `VoiceStudio.exe` — no install needed
- Linux: install `ffmpeg` and `python3-tk` first, then run the binary
- Known limitation: voice list requires internet on every launch

---

## Build and test checklist

### Before packaging

- [ ] All TTS synthesis paths tested with short text (< 1 chunk)
- [ ] All TTS synthesis paths tested with long text (> 5 chunks)
- [ ] Cancel mid-synthesis leaves no orphaned temp files
- [ ] App closes cleanly (no hanging threads)
- [ ] Settings persist across restarts
- [ ] File import works for both .txt and .docx
- [ ] SRT export timestamps are correct
- [ ] Error dialogs shown for all failure cases (disconnect network, test each)
- [ ] Update check completes silently when no update available
- [ ] Update check fails silently when GitHub is unreachable (no dialog, no crash)
- [ ] Update dialog appears when a newer version tag exists on GitHub
- [ ] Self-update downloads, replaces binary, and relaunches cleanly on Windows
- [ ] Updater helper script (`_updater.py`) is bundled into the PyInstaller exe

### After packaging

- [ ] Windows .exe runs on machine with no Python installed
- [ ] Linux binary runs on target machine
- [ ] Voice list loads successfully from built binary
- [ ] Long document synthesis completes without temp file errors

---

## Recommended build order

```
Phase 0  →  Phase 1a (async bridge)  →  Phase 1b–f (core modules, test each)
→  Phase 2 (voice browser)  →  Phase 3 (prosody panel)  →  Phase 5 (root window)
→  Phase 4 (text panel)  →  Phase 6 (error handling)  →  Phase 7 (auto-updater)
→  Phase 8 (packaging)
```

Build the async bridge and all core modules before any UI. Wire UI to already-working async backends, not the other way around.
