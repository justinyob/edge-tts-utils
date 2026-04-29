"""Manual test harness for VoiceBrowserPanel.

Run from project root:
    ./venv/bin/python test_voice_browser.py

Verify visually:
- "Loading voices..." appears, then list populates
- Search box filters in real time
- Clicking a row highlights it (selection persists)
- ▶ button generates a preview and plays it
- Selecting a different voice while one is selected updates the highlight
"""
import customtkinter as ctk

from core.audio_player import AudioPlayer
from core.tts_engine import TTSEngine
from core.voice_manager import VoiceManager
from ui.voice_browser import VoiceBrowserPanel
from utils.async_bridge import AsyncBridge


def main() -> None:
    root = ctk.CTk()
    root.title("Voice Browser — manual test")
    root.geometry("420x600")

    bridge = AsyncBridge(root)
    vm = VoiceManager()
    player = AudioPlayer()
    engine = TTSEngine()

    def on_selected(name: str) -> None:
        print(f"selected: {name}")

    panel = VoiceBrowserPanel(
        root,
        voice_manager=vm,
        audio_player=player,
        async_bridge=bridge,
        tts_engine=engine,
        on_voice_selected=on_selected,
    )
    panel.set_prosody_getter(lambda: {"rate": "+0%", "pitch": "+0Hz", "volume": "+0%"})
    panel.pack(fill="both", expand=True)

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
