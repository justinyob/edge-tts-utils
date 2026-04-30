"""GitHub Releases auto-updater.

Public functions never propagate exceptions for the version check so the
app can never crash while looking for an update.
"""
import logging
import os
import platform
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


_UPDATE_BAT_TEMPLATE = r"""@echo off
setlocal
echo Voice Studio updater
echo Waiting for process %1 to exit...
set /a TRIES=0
:wait
tasklist /FI "PID eq %1" 2>NUL | find "%1" >NUL
if %ERRORLEVEL% NEQ 0 goto settle
set /a TRIES+=1
if %TRIES% GEQ 60 goto settle
timeout /t 1 /nobreak >NUL
goto wait

:settle
rem Process may be gone from tasklist before Windows has released the
rem file handle on its exe. Give it a moment.
timeout /t 2 /nobreak >NUL

:swap
echo Replacing "%~3"
set /a SWAP_TRIES=0
:swap_retry
move /Y "%~2" "%~3" >NUL 2>&1
if %ERRORLEVEL% EQU 0 goto launched
set /a SWAP_TRIES+=1
if %SWAP_TRIES% GEQ 10 goto swap_failed
echo Replace attempt %SWAP_TRIES% failed, retrying...
timeout /t 1 /nobreak >NUL
goto swap_retry

:swap_failed
echo Failed to replace "%~3" after 10 attempts
pause
exit /b 1

:launched
echo Relaunching...
start "" "%~3"
(goto) 2>nul & del "%~f0"
"""


def _write_update_bat() -> str:
    """Write the Windows update helper .bat to a temp file. Returns the path.

    The .bat takes three positional args: <parent_pid> <src_exe> <dst_exe>.
    It waits for the parent to exit, replaces dst with src, relaunches dst,
    and then deletes itself.
    """
    fd, path = tempfile.mkstemp(prefix="voice_studio_update_", suffix=".bat")
    os.close(fd)
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write(_UPDATE_BAT_TEMPLATE)
    return path


def apply_update_windows(new_exe_path: str) -> None:
    bat_path = _write_update_bat()
    args = [
        "cmd.exe", "/c", bat_path,
        str(os.getpid()), new_exe_path, sys.executable,
    ]
    log.info("Launching Windows updater bat: %s", args)

    CREATE_NEW_CONSOLE = 0x00000010
    subprocess.Popen(args, close_fds=True, creationflags=CREATE_NEW_CONSOLE)
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
