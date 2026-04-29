import json
import os
import sys
import tempfile

APP_NAME = "Voice Studio"
APP_VERSION = "1.0.3"

DEFAULT_SAMPLE_TEXT = (
    "I love my friend Micah. "
    "He is a swell fellow indeed, and his wife is pretty cool too."
)

DEFAULT_RATE = "+0%"
DEFAULT_VOLUME = "+0%"
DEFAULT_PITCH = "+0Hz"

RATE_MIN, RATE_MAX = -50, 100
VOLUME_MIN, VOLUME_MAX = -50, 50
PITCH_MIN, PITCH_MAX = -50, 50

CHUNK_SIZE_WORDS = 500
CHUNK_OVERLAP = 0

SETTINGS_FILENAME = "settings.json"
TEMP_DIR_PREFIX = "voice_studio_"


def _app_data_dir() -> str:
    """Directory to store settings and logs — next to the binary when frozen,
    next to this file in development."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def settings_path() -> str:
    return os.path.join(_app_data_dir(), SETTINGS_FILENAME)


# Backwards-compat alias for tests/imports that referenced SETTINGS_FILE
SETTINGS_FILE = SETTINGS_FILENAME

ENGLISH_LOCALE_PREFIX = "en-"

GITHUB_REPO = "justinyob/edge-tts-utils"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_TIMEOUT = 5
WINDOWS_ASSET_NAME = "VoiceStudio.exe"
LINUX_ASSET_NAME = "VoiceStudio"

DEFAULT_SETTINGS = {
    "last_voice": "en-US-JennyNeural",
    "rate": DEFAULT_RATE,
    "volume": DEFAULT_VOLUME,
    "pitch": DEFAULT_PITCH,
    "window_width": 1100,
    "window_height": 700,
    "theme": "dark",
}


def load_settings() -> dict:
    path = settings_path()
    if not os.path.exists(path):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_SETTINGS)


def save_settings(data: dict) -> None:
    path = settings_path()
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".settings_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
