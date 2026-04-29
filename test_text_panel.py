"""Manual test harness for TextPanel + VoiceBrowserPanel + ProsodyPanel.

Run from project root:
    ./venv/bin/python test_text_panel.py

Verify visually:
- "📂 Import file" loads a .txt or .docx; filename appears above the textbox
- Word count updates ~300ms after you stop typing
- "▶ Preview" plays first 100 words via the selected voice and prosody
- "🎵 Export audio..." opens a save dialog, then a small CTkToplevel with
  an SRT checkbox and Export button
- Progress bar appears, updates per chunk, Cancel works
- On finish, a success dialog reports duration + size
"""
import customtkinter as ctk

from core.audio_player import AudioPlayer
from core.tts_engine import TTSEngine
from core.voice_manager import VoiceManager
from ui.prosody_panel import ProsodyPanel
from ui.text_panel import TextPanel
from ui.voice_browser import VoiceBrowserPanel
from utils.async_bridge import AsyncBridge


def main() -> None:
    root = ctk.CTk()
    root.title("Voice Studio — TextPanel manual test")
    root.geometry("1100x700")
    root.minsize(900, 600)

    bridge = AsyncBridge(root)
    vm = VoiceManager()
    player = AudioPlayer()
    engine = TTSEngine()

    root.grid_columnconfigure(0, weight=0, minsize=320)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(0, weight=1)

    voice_panel = VoiceBrowserPanel(
        root, voice_manager=vm, audio_player=player,
        async_bridge=bridge, tts_engine=engine,
        on_voice_selected=lambda n: print(f"voice: {n}"),
    )
    voice_panel.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(8, 4), pady=8)

    text_panel = TextPanel(
        root, tts_engine=engine, audio_player=player, async_bridge=bridge,
        get_voice=voice_panel.get_selected_voice,
        get_prosody=lambda: prosody.get_prosody(),
    )
    text_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=(8, 4))

    prosody = ProsodyPanel(root)
    prosody.grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(4, 8))

    voice_panel.set_prosody_getter(prosody.get_prosody)

    def on_close():
        try:
            player.cleanup()
        finally:
            bridge.shutdown()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
