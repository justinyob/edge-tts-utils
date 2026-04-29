import customtkinter as ctk

from config import (
    PITCH_MAX,
    PITCH_MIN,
    RATE_MAX,
    RATE_MIN,
    VOLUME_MAX,
    VOLUME_MIN,
)


def _fmt(value: int, suffix: str) -> str:
    return f"{value:+d}{suffix}"


class _SliderRow:
    def __init__(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        minimum: int,
        maximum: int,
        suffix: str,
        on_change,
    ) -> None:
        self.suffix = suffix
        self.minimum = minimum
        self.maximum = maximum
        self._on_change = on_change

        self.label = ctk.CTkLabel(parent, text=label, width=80, anchor="w")
        self.label.grid(row=row, column=0, padx=(10, 6), pady=6, sticky="w")

        steps = maximum - minimum
        self.slider = ctk.CTkSlider(
            parent,
            from_=minimum,
            to=maximum,
            number_of_steps=steps,
            command=self._handle,
        )
        self.slider.set(0)
        self.slider.grid(row=row, column=1, padx=6, pady=6, sticky="ew")

        self.value_lbl = ctk.CTkLabel(parent, text=_fmt(0, suffix), width=60, anchor="e")
        self.value_lbl.grid(row=row, column=2, padx=(6, 10), pady=6, sticky="e")

    def _handle(self, raw_value: float) -> None:
        v = int(round(raw_value))
        self.value_lbl.configure(text=_fmt(v, self.suffix))
        if self._on_change:
            self._on_change()

    def get_value(self) -> int:
        return int(round(self.slider.get()))

    def reset(self) -> None:
        self.slider.set(0)
        self.value_lbl.configure(text=_fmt(0, self.suffix))


class ProsodyPanel(ctk.CTkFrame):
    def __init__(self, parent, on_change=None) -> None:
        super().__init__(parent)
        self._on_change = on_change

        self.grid_columnconfigure(1, weight=1)

        self.rate = _SliderRow(
            self, row=0, label="Rate",
            minimum=RATE_MIN, maximum=RATE_MAX, suffix="%",
            on_change=self._fire_change,
        )
        self.volume = _SliderRow(
            self, row=1, label="Volume",
            minimum=VOLUME_MIN, maximum=VOLUME_MAX, suffix="%",
            on_change=self._fire_change,
        )
        self.pitch = _SliderRow(
            self, row=2, label="Pitch",
            minimum=PITCH_MIN, maximum=PITCH_MAX, suffix="Hz",
            on_change=self._fire_change,
        )

        self.reset_btn = ctk.CTkButton(
            self, text="Reset to defaults", command=self.reset, width=140,
        )
        self.reset_btn.grid(row=3, column=0, columnspan=3, padx=10, pady=(8, 10), sticky="e")

    def _fire_change(self) -> None:
        if self._on_change:
            self._on_change()

    def get_prosody(self) -> dict:
        return {
            "rate": _fmt(self.rate.get_value(), "%"),
            "volume": _fmt(self.volume.get_value(), "%"),
            "pitch": _fmt(self.pitch.get_value(), "Hz"),
        }

    def reset(self) -> None:
        self.rate.reset()
        self.volume.reset()
        self.pitch.reset()
        self._fire_change()

    def set_prosody(self, rate: str, volume: str, pitch: str) -> None:
        for row, val in ((self.rate, rate), (self.volume, volume), (self.pitch, pitch)):
            try:
                stripped = val.rstrip("HzhZ%").strip()
                if stripped.startswith("+"):
                    stripped = stripped[1:]
                n = int(stripped)
            except (ValueError, AttributeError):
                n = 0
            n = max(row.minimum, min(row.maximum, n))
            row.slider.set(n)
            row.value_lbl.configure(text=_fmt(n, row.suffix))
        self._fire_change()
