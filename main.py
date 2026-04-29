import logging
import os
import sys

from ui.app_window import AppWindow


def _log_path() -> str:
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "voice_studio.log")


def setup_logging() -> None:
    log_file = _log_path()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Avoid duplicating handlers if main() is called more than once
    if not any(isinstance(h, logging.FileHandler)
               and getattr(h, "baseFilename", None) == handler.baseFilename
               for h in root.handlers):
        root.addHandler(handler)


def main() -> None:
    setup_logging()
    log = logging.getLogger("main")
    log.info("Voice Studio starting")
    try:
        app = AppWindow()
        app.mainloop()
    except Exception:
        log.exception("Fatal error during app startup")
        raise
    log.info("Voice Studio exited")


if __name__ == "__main__":
    main()
