"""Manual test harness for ProsodyPanel.

Run from project root:
    ./venv/bin/python test_prosody_panel.py

Verify visually:
- Three labeled sliders (Rate, Volume, Pitch) with live value labels
- Values always show a sign: "+0%", "-25%", "+5Hz"
- "Reset to defaults" button returns all sliders to 0
- Each slider movement prints the current get_prosody() dict to stdout
"""
import customtkinter as ctk

from ui.prosody_panel import ProsodyPanel


def main() -> None:
    root = ctk.CTk()
    root.title("Prosody Panel — manual test")
    root.geometry("520x220")

    def on_change():
        print(panel.get_prosody())

    panel = ProsodyPanel(root, on_change=on_change)
    panel.pack(fill="both", expand=True, padx=12, pady=12)

    print("initial:", panel.get_prosody())
    root.mainloop()


if __name__ == "__main__":
    main()
