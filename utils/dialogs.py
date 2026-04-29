import logging

import customtkinter as ctk

log = logging.getLogger(__name__)


def show_error_dialog(parent, title: str, message: str) -> None:
    """Modal error dialog with an OK button.

    Safe to call from the Tk main thread. Failures here are swallowed so
    the dialog system can never itself crash the app.
    """
    try:
        dlg = ctk.CTkToplevel(parent)
        dlg.title(title)
        dlg.geometry("440x200")
        try:
            dlg.transient(parent)
            dlg.grab_set()
        except Exception:
            pass

        ctk.CTkLabel(
            dlg, text=message, wraplength=400, justify="left",
        ).pack(padx=20, pady=(20, 10), fill="both", expand=True)

        ctk.CTkButton(dlg, text="OK", width=80, command=dlg.destroy).pack(pady=(0, 16))
    except Exception:
        log.exception("Failed to display error dialog: title=%r message=%r", title, message)


def show_info_dialog(parent, title: str, message: str) -> None:
    """Modal info dialog with an OK button (visually identical to error dialog)."""
    show_error_dialog(parent, title, message)
