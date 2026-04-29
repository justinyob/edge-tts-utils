from typing import Callable, Optional

import customtkinter as ctk


class ProgressBar(ctk.CTkFrame):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._cancel_callback: Optional[Callable] = None

        self.grid_columnconfigure(0, weight=1)

        self.bar = ctk.CTkProgressBar(self)
        self.bar.set(0)
        self.bar.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=(8, 4))

        self.cancel_btn = ctk.CTkButton(
            self, text="✕ Cancel", width=90, command=self._on_cancel,
        )
        self.cancel_btn.grid(row=0, column=1, padx=(0, 8), pady=(8, 4))

        self.status_lbl = ctk.CTkLabel(self, text="Ready", anchor="w")
        self.status_lbl.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))

        self._visible = False
        self.hide()

    def set_progress(self, current: int, total: int) -> None:
        if total <= 0:
            self.bar.set(0)
            return
        self.bar.set(min(1.0, max(0.0, current / total)))
        self.set_status(f"Chunk {current} of {total}")

    def set_status(self, message: str) -> None:
        self.status_lbl.configure(text=message)

    def set_cancel_callback(self, fn: Optional[Callable]) -> None:
        self._cancel_callback = fn

    def _on_cancel(self) -> None:
        if self._cancel_callback is not None:
            self.cancel_btn.configure(state="disabled", text="Cancelling...")
            self._cancel_callback()

    def show(self) -> None:
        if not self._visible:
            self.cancel_btn.configure(state="normal", text="✕ Cancel")
            self.pack(fill="x", padx=8, pady=(4, 8))
            self._visible = True

    def hide(self) -> None:
        if self._visible:
            self.pack_forget()
        self._visible = False

    def reset(self) -> None:
        self.bar.set(0)
        self.set_status("Ready")
        self.cancel_btn.configure(state="normal", text="✕ Cancel")
        self.hide()
