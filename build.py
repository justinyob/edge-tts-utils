"""Build helper — picks the right PyInstaller spec for the current platform.

Usage:
    python build.py [--clean]
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true",
                        help="Remove dist/ and build/ before building.")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)

    system = platform.system()
    if system == "Windows":
        spec = "build_windows.spec"
        ffmpeg = os.path.join(project_root, "ffmpeg.exe")
        if not os.path.exists(ffmpeg):
            print(
                "ERROR: ffmpeg.exe not found in project root.\n"
                "Download a static ffmpeg build from https://www.gyan.dev/ffmpeg/builds/\n"
                "and place ffmpeg.exe next to build.py before building.",
                file=sys.stderr,
            )
            return 2
    elif system == "Linux":
        spec = "build_linux.spec"
        if shutil.which("ffmpeg") is None:
            print(
                "WARNING: system ffmpeg not found on PATH. Users will need\n"
                "to install ffmpeg themselves (sudo pacman -S ffmpeg / apt install ffmpeg).",
                file=sys.stderr,
            )
    else:
        print(f"ERROR: unsupported build platform: {system}", file=sys.stderr)
        return 1

    if args.clean:
        for d in ("dist", "build"):
            full = os.path.join(project_root, d)
            if os.path.isdir(full):
                print(f"Removing {full}")
                shutil.rmtree(full)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", spec]
    print(f"Running: {' '.join(cmd)}")
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
