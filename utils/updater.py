"""GitHub Releases auto-updater.

Public functions never propagate exceptions for the version check so the
app can never crash while looking for an update.
"""
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

import requests
from packaging.version import Version

from config import (
    APP_VERSION,
    GITHUB_API_RELEASES,
    LINUX_ASSET_NAME,
    UPDATE_CHECK_TIMEOUT,
    WINDOWS_ASSET_NAME,
)
from utils.paths import resource_path

log = logging.getLogger(__name__)


@dataclass
class UpdateInfo:
    available: bool
    latest_version: str
    download_url: Optional[str]
    release_notes: Optional[str]


def _asset_name() -> str:
    return WINDOWS_ASSET_NAME if platform.system() == "Windows" else LINUX_ASSET_NAME


def check_for_update() -> UpdateInfo:
    """Return UpdateInfo. Never raises."""
    try:
        resp = requests.get(GITHUB_API_RELEASES, timeout=UPDATE_CHECK_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        latest = data["tag_name"].lstrip("v")
        if Version(latest) > Version(APP_VERSION):
            wanted = _asset_name()
            url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if a.get("name") == wanted),
                None,
            )
            return UpdateInfo(
                available=True,
                latest_version=latest,
                download_url=url,
                release_notes=data.get("body", "") or "",
            )
    except Exception:
        log.exception("Update check failed")
    return UpdateInfo(
        available=False, latest_version=APP_VERSION,
        download_url=None, release_notes=None,
    )


def download_update(
    url: str,
    progress_callback: Callable[[int, int], None],
) -> str:
    """Stream-download the new binary into a temp file. Returns path.
    Raises requests.RequestException on failure."""
    suffix = os.path.splitext(_asset_name())[1] or ""
    fd, dest = tempfile.mkstemp(prefix="voice_studio_update_", suffix=suffix)
    os.close(fd)

    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0) or 0)
            written = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    written += len(chunk)
                    try:
                        progress_callback(written, total)
                    except Exception:
                        log.exception("Progress callback raised during download")
        return dest
    except Exception:
        log.exception("Update download failed: %s", url)
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
        raise


def _copy_updater_script() -> str:
    """Copy _updater.py out of _MEIPASS to a stable temp location.

    Required because in --onefile builds, _MEIPASS is wiped on app exit and
    the helper script must outlive the parent process.
    """
    src = resource_path("_updater.py")
    if not os.path.exists(src):
        raise FileNotFoundError(f"_updater.py not found at {src}")
    fd, dst = tempfile.mkstemp(prefix="voice_studio_updater_", suffix=".py")
    os.close(fd)
    shutil.copy2(src, dst)
    return dst


def apply_update_windows(new_exe_path: str) -> None:
    updater_script = _copy_updater_script()

    python_exe = None
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = os.path.join(meipass, "python.exe")
        if os.path.exists(candidate):
            python_exe = candidate
    if python_exe is None:
        python_exe = sys.executable

    args = [
        python_exe,
        updater_script,
        "--wait-pid", str(os.getpid()),
        "--src", new_exe_path,
        "--dst", sys.executable,
        "--relaunch",
    ]
    log.info("Launching Windows updater helper: %s", args)

    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    creationflags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(args, close_fds=True, creationflags=creationflags)
    sys.exit(0)


def apply_update_linux(new_exe_path: str) -> None:
    target = sys.executable
    log.info("Replacing %s with %s", target, new_exe_path)
    os.replace(new_exe_path, target)
    os.chmod(target, 0o755)
    subprocess.Popen([target], close_fds=True, start_new_session=True)
    sys.exit(0)


def apply_update(new_exe_path: str) -> None:
    if platform.system() == "Windows":
        apply_update_windows(new_exe_path)
    else:
        apply_update_linux(new_exe_path)
