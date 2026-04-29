import logging
import threading

import customtkinter as ctk

from config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_PITCH,
    DEFAULT_RATE,
    DEFAULT_VOLUME,
    load_settings,
    save_settings,
)
from core.audio_player import AudioPlayer
from core.tts_engine import TTSEngine
from core.voice_manager import VoiceManager
from ui.prosody_panel import ProsodyPanel
from ui.text_panel import TextPanel
from ui.voice_browser import VoiceBrowserPanel
from utils.async_bridge import AsyncBridge
from utils.dialogs import show_error_dialog, show_info_dialog
from utils.updater import (
    UpdateInfo,
    apply_update,
    check_for_update,
    download_update,
)

log = logging.getLogger(__name__)


_VOICE_COLUMN_MIN = 340


class AppWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self._settings = load_settings()
        ctk.set_appearance_mode(self._settings.get("theme", "dark"))

        self.title(APP_NAME)
        w = int(self._settings.get("window_width", 1100))
        h = int(self._settings.get("window_height", 700))
        self.geometry(f"{w}x{h}")
        self.minsize(900, 600)

        self._selected_voice: str | None = None

        self.voice_manager = VoiceManager()
        self.tts_engine = TTSEngine()
        self.audio_player = AudioPlayer()
        self.async_bridge = AsyncBridge(self)

        self._build_layout()
        self._wire_callbacks()
        self._restore_settings()
        self._kick_off_update_check()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---- layout ----

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=_VOICE_COLUMN_MIN)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)

        self.voice_panel = VoiceBrowserPanel(
            self,
            voice_manager=self.voice_manager,
            audio_player=self.audio_player,
            async_bridge=self.async_bridge,
            tts_engine=self.tts_engine,
            on_voice_selected=self._on_voice_selected,
        )
        self.voice_panel.grid(row=0, column=0, rowspan=2, sticky="nsew",
                              padx=(8, 4), pady=(8, 4))

        self.text_panel = TextPanel(
            self,
            tts_engine=self.tts_engine,
            audio_player=self.audio_player,
            async_bridge=self.async_bridge,
            get_voice=lambda: self._selected_voice,
            get_prosody=lambda: self.prosody_panel.get_prosody(),
        )
        self.text_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=(8, 4))

        self.prosody_panel = ProsodyPanel(self)
        self.prosody_panel.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(4, 4))

        self._build_status_bar()

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 6))
        bar.grid_columnconfigure(1, weight=1)

        is_dark = self._settings.get("theme", "dark") == "dark"
        self.theme_switch = ctk.CTkSwitch(
            bar, text="Dark mode", command=self._on_theme_toggle,
        )
        if is_dark:
            self.theme_switch.select()
        else:
            self.theme_switch.deselect()
        self.theme_switch.grid(row=0, column=0, padx=(4, 8), sticky="w")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e")
        self.update_btn = ctk.CTkButton(
            right, text="⟳ Check for updates", width=160,
            command=self._on_manual_update_check,
            fg_color="transparent", border_width=1,
        )
        self.update_btn.pack(side="right", padx=(8, 4))
        ctk.CTkLabel(
            right, text=f"v{APP_VERSION}", text_color=("gray40", "gray60"),
        ).pack(side="right")

    # ---- wiring ----

    def _wire_callbacks(self) -> None:
        self.voice_panel.set_prosody_getter(self.prosody_panel.get_prosody)

    def _on_voice_selected(self, short_name: str) -> None:
        self._selected_voice = short_name

    # ---- settings ----

    def _restore_settings(self) -> None:
        self.prosody_panel.set_prosody(
            rate=self._settings.get("rate", DEFAULT_RATE),
            volume=self._settings.get("volume", DEFAULT_VOLUME),
            pitch=self._settings.get("pitch", DEFAULT_PITCH),
        )
        last = self._settings.get("last_voice")
        if last:
            self.voice_panel.select_by_short_name(last)

    def _collect_settings(self) -> dict:
        prosody = self.prosody_panel.get_prosody()
        try:
            geo = self.geometry()  # "WxH+X+Y"
            wh = geo.split("+")[0]
            w, h = wh.split("x")
            width, height = int(w), int(h)
        except Exception:
            width, height = 1100, 700
        theme = "dark" if self.theme_switch.get() == 1 else "light"
        return {
            "last_voice": self._selected_voice or self._settings.get("last_voice", ""),
            "rate": prosody["rate"],
            "volume": prosody["volume"],
            "pitch": prosody["pitch"],
            "window_width": width,
            "window_height": height,
            "theme": theme,
        }

    # ---- theme ----

    def _on_theme_toggle(self) -> None:
        mode = "dark" if self.theme_switch.get() == 1 else "light"
        ctk.set_appearance_mode(mode)

    # ---- updates ----

    def _kick_off_update_check(self) -> None:
        def worker():
            info = check_for_update()
            if info.available:
                try:
                    self.after(0, self._show_update_dialog, info)
                except RuntimeError:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_manual_update_check(self) -> None:
        self.update_btn.configure(state="disabled", text="Checking...")

        def worker():
            info = check_for_update()
            try:
                self.after(0, self._on_manual_update_done, info)
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_manual_update_done(self, info: UpdateInfo) -> None:
        self.update_btn.configure(state="normal", text="⟳ Check for updates")
        if info.available:
            self._show_update_dialog(info)
        else:
            self._show_message("Up to date", f"You're running the latest version (v{APP_VERSION}).")

    def _show_update_dialog(self, info: UpdateInfo) -> None:
        UpdateDialog(self, info)

    def _show_message(self, title: str, message: str) -> None:
        show_info_dialog(self, title, message)

    # ---- close ----

    def on_close(self) -> None:
        try:
            save_settings(self._collect_settings())
        except Exception:
            log.exception("Failed to save settings on close")
        try:
            self.audio_player.cleanup()
        except Exception:
            log.exception("Failed to clean up audio player on close")
        try:
            self.async_bridge.shutdown()
        except Exception:
            log.exception("Failed to shut down async bridge on close")
        self.destroy()


class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, parent: "AppWindow", info: UpdateInfo) -> None:
        super().__init__(parent)
        self._parent = parent
        self._info = info
        self._download_thread: threading.Thread | None = None
        self._download_active = False

        self.title(f"Update available — v{info.latest_version}")
        self.geometry("540x460")
        try:
            self.transient(parent)
            self.grab_set()
        except Exception:
            pass

        ctk.CTkLabel(
            self, text=f"Update available — v{info.latest_version}",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(padx=20, pady=(20, 4), anchor="w")
        ctk.CTkLabel(
            self,
            text=f"You're running v{APP_VERSION}. "
                 f"Version {info.latest_version} is available.",
            text_color=("gray40", "gray60"), wraplength=480, justify="left",
        ).pack(padx=20, pady=(0, 12), anchor="w")

        self.notes_box = ctk.CTkTextbox(self, wrap="word", height=180)
        self.notes_box.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.notes_box.insert("1.0", info.release_notes or "(no release notes)")
        self.notes_box.configure(state="disabled")

        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_lbl = ctk.CTkLabel(
            self, text="", text_color=("gray30", "gray70"), anchor="w",
        )
        self.error_lbl = ctk.CTkLabel(
            self, text="", text_color=("red", "red"), anchor="w",
        )

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 16))
        self.later_btn = ctk.CTkButton(
            btn_row, text="Later", fg_color="transparent", border_width=1,
            command=self._on_later,
        )
        self.later_btn.pack(side="right", padx=(8, 0))
        self.update_btn = ctk.CTkButton(
            btn_row, text="Update now", command=self._on_update,
        )
        self.update_btn.pack(side="right")
        if not info.download_url:
            self.update_btn.configure(state="disabled")
            self.error_lbl.configure(text="No download asset attached to this release.")
            self.error_lbl.pack(fill="x", padx=20, pady=(0, 4))

    # ---- progress + UI helpers ----

    def _show_progress_widgets(self) -> None:
        self.progress_bar.pack(fill="x", padx=20, pady=(0, 4))
        self.progress_lbl.pack(fill="x", padx=20, pady=(0, 4))

    def _set_progress(self, written: int, total: int) -> None:
        if total > 0:
            self.progress_bar.set(min(1.0, written / total))
            mb_w = written / (1024 * 1024)
            mb_t = total / (1024 * 1024)
            self.progress_lbl.configure(text=f"Downloading... {mb_w:.1f} MB / {mb_t:.1f} MB")
        else:
            mb_w = written / (1024 * 1024)
            self.progress_lbl.configure(text=f"Downloading... {mb_w:.1f} MB")

    def _set_error(self, msg: str) -> None:
        self.error_lbl.configure(text=msg)
        try:
            self.error_lbl.pack(fill="x", padx=20, pady=(0, 4))
        except Exception:
            pass

    # ---- button handlers ----

    def _on_later(self) -> None:
        if self._download_active:
            return  # ignore while downloading
        self.destroy()

    def _on_update(self) -> None:
        if self._download_active or not self._info.download_url:
            return
        self._download_active = True
        self.update_btn.configure(state="disabled")
        self.later_btn.configure(state="disabled")
        self.error_lbl.configure(text="")
        self._show_progress_widgets()
        self.progress_lbl.configure(text="Starting download...")

        url = self._info.download_url

        def progress_cb(written: int, total: int) -> None:
            try:
                self.after(0, self._set_progress, written, total)
            except RuntimeError:
                pass

        def worker():
            try:
                path = download_update(url, progress_cb)
            except Exception as exc:
                log.exception("Update download failed")
                try:
                    self.after(0, self._on_download_error, exc)
                except RuntimeError:
                    pass
                return
            try:
                self.after(0, self._on_download_complete, path)
            except RuntimeError:
                pass

        self._download_thread = threading.Thread(target=worker, daemon=True)
        self._download_thread.start()

    def _on_download_error(self, exc: BaseException) -> None:
        self._download_active = False
        self.update_btn.configure(state="normal")
        self.later_btn.configure(state="normal")
        self._set_error("Download failed. Try again.")
        log.error("Download error: %r", exc)

    def _on_download_complete(self, downloaded_path: str) -> None:
        self.progress_lbl.configure(text="Restarting...")
        log.info("Update downloaded to %s, applying", downloaded_path)
        try:
            # Save settings before the parent process is replaced
            try:
                self._parent.on_close
            except Exception:
                pass
            apply_update(downloaded_path)
        except SystemExit:
            raise
        except Exception as exc:
            log.exception("apply_update failed")
            self._download_active = False
            self.update_btn.configure(state="normal")
            self.later_btn.configure(state="normal")
            self._set_error(f"Could not install update: {exc}")
