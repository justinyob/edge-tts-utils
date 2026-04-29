import logging
import os
import threading
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from core.exceptions import (
    MSG_FILE_READ_FAILED,
    CancellationError,
    FileReadError,
    friendly_message,
)
from core.file_reader import read_file
from ui.progress_bar import ProgressBar
from utils.dialogs import show_error_dialog, show_info_dialog

log = logging.getLogger(__name__)


def _suggest_dir() -> str:
    home = os.path.expanduser("~")
    desktop = os.path.join(home, "Desktop")
    return desktop if os.path.isdir(desktop) else home


def _show_message(parent, title: str, message: str) -> None:
    show_info_dialog(parent, title, message)


class _ExportOptionsDialog(ctk.CTkToplevel):
    def __init__(self, parent, default_name: str) -> None:
        super().__init__(parent)
        self.title("Export audio")
        self.geometry("520x240")
        self.transient(parent)
        self.grab_set()

        self.result: Optional[dict] = None
        self._chosen_path: Optional[str] = None

        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Output file:", anchor="w").grid(
            row=0, column=0, padx=(16, 6), pady=(20, 6), sticky="w"
        )
        self.path_var = ctk.StringVar(value="(not selected)")
        ctk.CTkLabel(
            self, textvariable=self.path_var, anchor="w", text_color=("gray30", "gray70"),
        ).grid(row=0, column=1, padx=(0, 6), pady=(20, 6), sticky="ew")
        ctk.CTkButton(
            self, text="Choose...", width=90,
            command=lambda: self._pick_path(default_name),
        ).grid(row=0, column=2, padx=(0, 16), pady=(20, 6))

        self.srt_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self, text="Also export subtitles (.srt)", variable=self.srt_var,
        ).grid(row=1, column=0, columnspan=3, padx=16, pady=12, sticky="w")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, columnspan=3, sticky="e", padx=16, pady=(8, 16))
        self.export_btn = ctk.CTkButton(
            btn_row, text="Export", state="disabled", command=self._on_export,
        )
        self.export_btn.pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            btn_row, text="Cancel", fg_color="transparent",
            border_width=1, command=self._on_cancel,
        ).pack(side="right")

        # Auto-prompt for path immediately
        self.after(50, lambda: self._pick_path(default_name))

    def _pick_path(self, default_name: str) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save audio as",
            defaultextension=".mp3",
            initialdir=_suggest_dir(),
            initialfile=default_name,
            filetypes=[("MP3 audio", "*.mp3")],
        )
        if path:
            self._chosen_path = path
            self.path_var.set(path)
            self.export_btn.configure(state="normal")

    def _on_export(self) -> None:
        if not self._chosen_path:
            return
        srt = None
        if self.srt_var.get():
            base, _ = os.path.splitext(self._chosen_path)
            srt = base + ".srt"
        self.result = {"output_path": self._chosen_path, "srt_path": srt}
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


class TextPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        tts_engine,
        audio_player,
        async_bridge,
        get_voice: Callable[[], Optional[str]],
        get_prosody: Callable[[], dict],
    ) -> None:
        super().__init__(parent)
        self._tts_engine = tts_engine
        self._audio_player = audio_player
        self._async_bridge = async_bridge
        self._get_voice = get_voice
        self._get_prosody = get_prosody

        self._source_path: Optional[str] = None
        self._wc_after_id: Optional[str] = None
        self._cancel_event: Optional[threading.Event] = None
        self._exporting = False
        self._previewing = False
        self._preview_path: Optional[str] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Top row: import + word count
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.grid_columnconfigure(1, weight=1)
        self.import_btn = ctk.CTkButton(
            top, text="📂 Import file", command=self._on_import,
        )
        self.import_btn.grid(row=0, column=0, sticky="w")
        self.wc_lbl = ctk.CTkLabel(top, text="0 words", anchor="e")
        self.wc_lbl.grid(row=0, column=1, sticky="e")

        # Source filename label
        self.source_lbl = ctk.CTkLabel(
            self, text="", anchor="w", text_color=("gray40", "gray60"),
        )
        self.source_lbl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        self.source_lbl.grid_remove()

        # Textbox
        self.textbox = ctk.CTkTextbox(self, wrap="word")
        self.textbox.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        self.textbox.bind("<KeyRelease>", self._schedule_wc)

        # Bottom buttons
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=3, column=0, sticky="ew", padx=8, pady=(4, 4))
        bottom.grid_columnconfigure(0, weight=1)
        self.preview_btn = ctk.CTkButton(
            bottom, text="▶ Preview", command=self._on_preview, width=140,
        )
        self.preview_btn.grid(row=0, column=0, sticky="w")
        self.export_btn = ctk.CTkButton(
            bottom, text="🎵 Export audio...", command=self._on_export, width=160,
        )
        self.export_btn.grid(row=0, column=1, sticky="e")

        # Inline error label
        self.error_lbl = ctk.CTkLabel(
            self, text="", text_color=("red", "red"), anchor="w",
        )
        self.error_lbl.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 2))

        # Progress bar
        self.progress = ProgressBar(self)
        # Initially hidden; show() will pack it inside us, but we want it
        # under the bottom row — re-parent management via pack inside this frame.

    # ---- text + word count ----

    def _get_text(self) -> str:
        return self.textbox.get("1.0", "end-1c")

    def _set_text(self, text: str) -> None:
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", text)
        self._update_word_count()

    def _schedule_wc(self, _event=None) -> None:
        if self._wc_after_id is not None:
            try:
                self.after_cancel(self._wc_after_id)
            except Exception:
                pass
        self._wc_after_id = self.after(300, self._update_word_count)

    def _update_word_count(self) -> None:
        self._wc_after_id = None
        words = len(self._get_text().split())
        self.wc_lbl.configure(text=f"{words:,} words")

    def _clear_error(self) -> None:
        self.error_lbl.configure(text="")

    def _set_error(self, msg: str) -> None:
        self.error_lbl.configure(text=msg)

    # ---- import ----

    def _on_import(self) -> None:
        self._clear_error()
        path = filedialog.askopenfilename(
            parent=self,
            title="Import text or document",
            filetypes=[("Text and Word documents", "*.txt *.docx"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            text = read_file(path)
        except FileReadError as e:
            log.exception("Failed to read imported file: %s", path)
            show_error_dialog(self, "Could not read file", MSG_FILE_READ_FAILED)
            return
        except ValueError as e:
            log.warning("Unsupported import file type: %s", path)
            show_error_dialog(self, "Unsupported file type", str(e))
            return
        except Exception as e:
            log.exception("Unexpected error reading file: %s", path)
            show_error_dialog(self, "Could not read file", MSG_FILE_READ_FAILED)
            return
        self._source_path = path
        self.source_lbl.configure(text=f"📄 {os.path.basename(path)}")
        self.source_lbl.grid()
        self._set_text(text)

    # ---- preview ----

    def _on_preview(self) -> None:
        self._clear_error()
        text = self._get_text().strip()
        if not text:
            self._set_error("Type or import some text before previewing.")
            return
        voice = self._get_voice()
        if not voice:
            self._set_error("Select a voice from the list first.")
            return
        if self._previewing:
            return

        snippet = " ".join(text.split()[:100])
        prosody = self._get_prosody()

        self._previewing = True
        self.preview_btn.configure(state="disabled", text="Generating...")
        self._audio_player.stop()

        coro = self._tts_engine.synthesize_preview(
            text=snippet, voice=voice,
            rate=prosody["rate"], pitch=prosody["pitch"], volume=prosody["volume"],
        )
        self._async_bridge.run_async(
            coro,
            on_complete=self._on_preview_ready,
            on_error=self._on_preview_error,
        )

    def _on_preview_ready(self, path: str) -> None:
        try:
            self._audio_player.cleanup()
            self._audio_player.load(path)
            self._audio_player.play()
            self._preview_path = path
        finally:
            self._previewing = False
            self.preview_btn.configure(state="normal", text="▶ Preview")

    def _on_preview_error(self, exc: BaseException) -> None:
        self._previewing = False
        self.preview_btn.configure(state="normal", text="▶ Preview")
        log.error("Preview synthesis failed: %r", exc)
        show_error_dialog(self, "Preview failed", friendly_message(exc))

    # ---- export ----

    def _on_export(self) -> None:
        self._clear_error()
        text = self._get_text().strip()
        if not text:
            self._set_error("Type or import some text before exporting.")
            return
        voice = self._get_voice()
        if not voice:
            self._set_error("Select a voice from the list first.")
            return
        if self._exporting:
            return

        if self._source_path:
            base = os.path.splitext(os.path.basename(self._source_path))[0]
            default_name = f"{base}.mp3"
        else:
            default_name = "output.mp3"

        dlg = _ExportOptionsDialog(self, default_name)
        self.wait_window(dlg)
        if not dlg.result:
            return

        output_path = dlg.result["output_path"]
        srt_path = dlg.result["srt_path"]
        prosody = self._get_prosody()

        self._exporting = True
        self._cancel_event = threading.Event()
        self.export_btn.configure(state="disabled")
        self.preview_btn.configure(state="disabled")
        self.progress.reset()
        self.progress.set_status("Preparing...")
        self.progress.set_cancel_callback(self._on_cancel_export)
        self.progress.grid(row=5, column=0, sticky="ew", padx=8, pady=(2, 8))
        self.progress._visible = True  # we packed via grid so mark visible

        def progress_cb(current: int, total: int) -> None:
            # Called from the asyncio thread — marshal to UI thread
            self.after(0, self.progress.set_progress, current, total)

        coro = self._tts_engine.synthesize(
            text=text,
            voice=voice,
            rate=prosody["rate"],
            pitch=prosody["pitch"],
            volume=prosody["volume"],
            output_path=output_path,
            srt_path=srt_path,
            progress_callback=progress_cb,
            cancel_event=self._cancel_event,
        )
        self._async_bridge.run_async(
            coro,
            on_complete=lambda result: self._on_export_done(result, output_path),
            on_error=self._on_export_error,
        )

    def _on_cancel_export(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        self.progress.set_status("Cancelling...")

    def _finish_export_ui(self) -> None:
        self._exporting = False
        self._cancel_event = None
        self.export_btn.configure(state="normal")
        self.preview_btn.configure(state="normal")
        self.progress.grid_remove()
        self.progress._visible = False
        self.progress.reset()

    def _on_export_done(self, result, output_path: str) -> None:
        self._finish_export_ui()
        minutes = result.duration_seconds / 60.0
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        msg = (
            f"Saved to:\n{output_path}\n\n"
            f"Duration: {minutes:.1f} minutes\n"
            f"File size: {size_mb:.1f} MB"
        )
        if result.srt_path:
            msg += f"\nSubtitles: {result.srt_path}"
        show_info_dialog(self, "Export complete", msg)

    def _on_export_error(self, exc: BaseException) -> None:
        self._finish_export_ui()
        if isinstance(exc, CancellationError):
            show_info_dialog(self, "Export cancelled", "Audio export was cancelled.")
            return
        log.error("Export synthesis failed: %r", exc)
        show_error_dialog(self, "Export failed", friendly_message(exc))
