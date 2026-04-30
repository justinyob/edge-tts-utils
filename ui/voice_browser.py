import logging
from typing import Callable, Optional

import customtkinter as ctk

from config import DEFAULT_SAMPLE_TEXT, ENGLISH_LOCALE_PREFIX
from core.exceptions import friendly_message
from utils.dialogs import show_error_dialog

log = logging.getLogger(__name__)


_ROW_BG = ("gray92", "gray18")
_ROW_BG_HOVER = ("gray86", "gray24")
_ROW_BG_SELECTED = ("#cfe2ff", "#1f3a5f")
_MUTED_COLOR = ("gray40", "gray60")


class _VoiceRow(ctk.CTkFrame):
    def __init__(
        self,
        parent: "VoiceBrowserPanel",
        voice: dict,
    ) -> None:
        super().__init__(parent.scroll, fg_color=_ROW_BG, corner_radius=6)
        self._panel = parent
        self.voice = voice
        self._selected = False

        short = voice.get("ShortName", "")
        display = short
        if display.startswith(ENGLISH_LOCALE_PREFIX):
            display = display[len(ENGLISH_LOCALE_PREFIX):]

        self.grid_columnconfigure(0, weight=1)

        self.name_lbl = ctk.CTkLabel(self, text=display, anchor="w")
        self.name_lbl.grid(row=0, column=0, sticky="w", padx=(8, 4), pady=(4, 0))

        meta_text = f"{voice.get('Locale', '')}  •  {voice.get('Gender', '')}"
        self.meta_lbl = ctk.CTkLabel(
            self, text=meta_text, anchor="w",
            text_color=_MUTED_COLOR, font=ctk.CTkFont(size=11),
        )
        self.meta_lbl.grid(row=1, column=0, sticky="w", padx=(8, 4), pady=(0, 4))

        self.play_btn = ctk.CTkButton(
            self, text="▶", width=32, height=32,
            command=self._on_play,
        )
        self.play_btn.grid(row=0, column=1, rowspan=2, padx=(4, 6), pady=4)

        for w in (self, self.name_lbl, self.meta_lbl):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_click(self, _event=None) -> None:
        self._panel._select_row(self)

    def _on_enter(self, _event=None) -> None:
        if not self._selected:
            self.configure(fg_color=_ROW_BG_HOVER)

    def _on_leave(self, _event=None) -> None:
        if not self._selected:
            self.configure(fg_color=_ROW_BG)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.configure(fg_color=_ROW_BG_SELECTED if selected else _ROW_BG)

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.play_btn.configure(text="…", state="disabled")
        else:
            self.play_btn.configure(text="▶", state="normal")

    def _on_play(self) -> None:
        self._panel._preview_voice(self)


class VoiceBrowserPanel(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        voice_manager,
        audio_player,
        async_bridge,
        tts_engine,
        on_voice_selected: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._voice_manager = voice_manager
        self._audio_player = audio_player
        self._async_bridge = async_bridge
        self._tts_engine = tts_engine
        self._on_voice_selected = on_voice_selected
        self._prosody_getter: Optional[Callable[[], dict]] = None

        self._rows: list[_VoiceRow] = []
        self._selected_row: Optional[_VoiceRow] = None
        self._busy_row: Optional[_VoiceRow] = None
        self._pending_selection: Optional[str] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.header = ctk.CTkLabel(
            self, text="Voices", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        self.search_var = ctk.StringVar()
        self.search = ctk.CTkEntry(
            self, placeholder_text="Search voices...",
            textvariable=self.search_var,
        )
        self.search.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        self.search.bind("<KeyRelease>", self._on_search)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self.scroll.grid_columnconfigure(0, weight=1)

        self.loading_lbl = ctk.CTkLabel(
            self, text="Loading voices...", text_color=_MUTED_COLOR,
        )
        self.loading_lbl.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        self._kick_off_fetch()

    def set_prosody_getter(self, fn: Callable[[], dict]) -> None:
        self._prosody_getter = fn

    def get_selected_voice(self) -> Optional[str]:
        if self._selected_row is None:
            return None
        return self._selected_row.voice.get("ShortName")

    def select_by_short_name(self, short_name: str) -> bool:
        """Programmatically select a row by ShortName. Safe to call before
        voices have loaded — selection is queued and applied once rows exist."""
        if not short_name:
            return False
        if not self._rows:
            self._pending_selection = short_name
            return False
        for row in self._rows:
            if row.voice.get("ShortName") == short_name:
                self._select_row(row)
                return True
        return False

    def _kick_off_fetch(self) -> None:
        log.info("VoiceBrowserPanel: submitting fetch_voices() to async bridge")
        self._async_bridge.run_async(
            self._voice_manager.fetch_voices(),
            on_complete=self._on_voices_loaded,
            on_error=self._on_voices_error,
        )

    def _on_voices_loaded(self, voices: list[dict]) -> None:
        log.info("VoiceBrowserPanel: voices loaded (%d) — building rows", len(voices))
        self.loading_lbl.grid_remove()
        self._build_rows(voices)
        if self._pending_selection:
            short = self._pending_selection
            self._pending_selection = None
            self.select_by_short_name(short)

    def _on_voices_error(self, exc: BaseException) -> None:
        log.error("Voice list fetch failed: %r", exc)
        self.loading_lbl.configure(
            text="Could not load voices — see error dialog.",
            text_color=("red", "red"),
        )
        show_error_dialog(self, "Could not load voices", friendly_message(exc))

    def _build_rows(self, voices: list[dict]) -> None:
        for r in self._rows:
            r.destroy()
        self._rows = []

        for v in voices:
            row = _VoiceRow(self, v)
            self._rows.append(row)

        self._render_rows(voices)

    def _render_rows(self, voices: list[dict]) -> None:
        # Hide all, then re-grid the matching ones in order
        for r in self._rows:
            r.grid_forget()

        wanted = {id(v) for v in voices}
        idx = 0
        for r in self._rows:
            if id(r.voice) in wanted:
                r.grid(row=idx, column=0, sticky="ew", padx=4, pady=2)
                idx += 1

    def _on_search(self, _event=None) -> None:
        query = self.search_var.get().strip()
        if not query:
            voices = self._voice_manager.get_voices()
        else:
            voices = self._voice_manager.filter(query)
        self._render_rows(voices)

    def _select_row(self, row: _VoiceRow) -> None:
        if self._selected_row is row:
            return
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
        self._selected_row = row
        row.set_selected(True)
        if self._on_voice_selected:
            self._on_voice_selected(row.voice.get("ShortName", ""))

    def _preview_voice(self, row: _VoiceRow) -> None:
        if self._busy_row is not None:
            return  # ignore until current preview finishes

        prosody = self._prosody_getter() if self._prosody_getter else {
            "rate": "+0%", "pitch": "+0Hz", "volume": "+0%",
        }

        self._audio_player.stop()
        self._busy_row = row
        row.set_busy(True)

        coro = self._tts_engine.synthesize_preview(
            text=DEFAULT_SAMPLE_TEXT,
            voice=row.voice.get("ShortName", ""),
            rate=prosody.get("rate", "+0%"),
            pitch=prosody.get("pitch", "+0Hz"),
            volume=prosody.get("volume", "+0%"),
        )
        self._async_bridge.run_async(
            coro,
            on_complete=lambda path, r=row: self._on_preview_ready(r, path),
            on_error=lambda exc, r=row: self._on_preview_error(r, exc),
        )

    def _on_preview_ready(self, row: _VoiceRow, path: str) -> None:
        try:
            self._audio_player.cleanup()
            self._audio_player.load(path)
            self._audio_player.play()
        finally:
            row.set_busy(False)
            self._busy_row = None

    def _on_preview_error(self, row: _VoiceRow, exc: BaseException) -> None:
        row.set_busy(False)
        self._busy_row = None
        log.error("Voice preview failed: %r", exc)
        show_error_dialog(self, "Preview failed", friendly_message(exc))
