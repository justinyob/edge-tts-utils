import logging
import os
import platform
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
    # Quiet noisy libraries that emit large DEBUG volumes
    logging.getLogger("urllib3").setLevel(logging.INFO)


def _log_environment(log: logging.Logger) -> None:
    log.info("Python %s on %s %s", sys.version.split()[0], platform.system(), platform.release())
    log.info("Frozen=%s, executable=%s", getattr(sys, "frozen", False), sys.executable)
    try:
        import edge_tts
        log.info("edge-tts version: %s", getattr(edge_tts, "__version__", "unknown"))
    except Exception as e:
        log.error("Could not import edge_tts: %r", e)
    try:
        import aiohttp
        log.info("aiohttp version: %s", getattr(aiohttp, "__version__", "unknown"))
    except Exception as e:
        log.error("Could not import aiohttp: %r", e)


def main() -> None:
    setup_logging()
    log = logging.getLogger("main")
    log.info("Voice Studio starting")
    _log_environment(log)
    try:
        app = AppWindow()
        app.mainloop()
    except Exception:
        log.exception("Fatal error during app startup")
        raise
    log.info("Voice Studio exited")


if __name__ == "__main__":
    main()
