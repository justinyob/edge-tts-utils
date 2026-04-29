"""Standalone helper that completes a self-update after the main app exits.

Launched by the running Voice Studio just before it terminates.
Stdlib-only — must be importable from the bundled Python that ships
inside the PyInstaller exe.

Args:
    --wait-pid PID         PID of the main app to wait on
    --src NEW_EXE_PATH     downloaded replacement binary
    --dst CURRENT_EXE_PATH binary to replace
    [--relaunch]           launch the new binary after replacement
"""
import argparse
import os
import shutil
import subprocess
import sys
import time


def _wait_for_exit(pid: int, timeout_seconds: float = 30.0, poll: float = 0.2) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return  # process gone
        time.sleep(poll)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait-pid", type=int, required=True)
    parser.add_argument("--src", required=True)
    parser.add_argument("--dst", required=True)
    parser.add_argument("--relaunch", action="store_true")
    args = parser.parse_args()

    _wait_for_exit(args.wait_pid)

    try:
        shutil.copy2(args.src, args.dst)
    except OSError as e:
        print(f"updater: failed to replace binary: {e}", file=sys.stderr)
        return 1

    try:
        os.remove(args.src)
    except OSError:
        pass

    if args.relaunch:
        try:
            if os.name == "nt":
                subprocess.Popen([args.dst], close_fds=True)
            else:
                os.chmod(args.dst, 0o755)
                subprocess.Popen([args.dst], close_fds=True, start_new_session=True)
        except OSError as e:
            print(f"updater: failed to relaunch: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
