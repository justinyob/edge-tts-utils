"""Custom exceptions for Voice Studio.

Each exception's message is intended to be safe to show directly to the user.
"""


class VoiceFetchError(Exception):
    """Raised when the voice list cannot be fetched from the TTS service."""


class NetworkError(Exception):
    """Raised when a network call to the TTS service fails."""


class SynthesisError(Exception):
    """Raised when TTS synthesis fails mid-flight."""


class DiskWriteError(Exception):
    """Raised when writing the output file fails."""


class FileReadError(Exception):
    """Raised when an input file cannot be read or decoded."""


class CancellationError(Exception):
    """Raised when synthesis is cancelled mid-flight."""


# User-facing message constants
MSG_VOICE_FETCH_FAILED = (
    "Could not load voice list. Check your connection and restart the app."
)
MSG_NETWORK_FAILED = (
    "Could not connect to the text-to-speech service. "
    "Please check your internet connection and try again."
)
MSG_SYNTHESIS_FAILED = (
    "Audio generation failed. The service may be temporarily unavailable. "
    "Try again in a moment."
)
MSG_DISK_WRITE_FAILED = (
    "Could not save the file. "
    "Check that you have write permission for the selected folder."
)
MSG_FILE_READ_FAILED = (
    "Could not read this file. Supported formats: .txt, .docx"
)


def friendly_message(exc: BaseException) -> str:
    """Map an exception to a user-facing message."""
    if isinstance(exc, VoiceFetchError):
        return str(exc) or MSG_VOICE_FETCH_FAILED
    if isinstance(exc, NetworkError):
        return str(exc) or MSG_NETWORK_FAILED
    if isinstance(exc, SynthesisError):
        return str(exc) or MSG_SYNTHESIS_FAILED
    if isinstance(exc, DiskWriteError):
        return str(exc) or MSG_DISK_WRITE_FAILED
    if isinstance(exc, FileReadError):
        return MSG_FILE_READ_FAILED
    if isinstance(exc, CancellationError):
        return "Operation cancelled."
    return f"An unexpected error occurred: {exc}"
