import logging

import edge_tts

from config import ENGLISH_LOCALE_PREFIX
from core.exceptions import MSG_VOICE_FETCH_FAILED, VoiceFetchError

log = logging.getLogger(__name__)


class VoiceManager:
    def __init__(self) -> None:
        self._voices: list[dict] | None = None

    async def fetch_voices(self) -> list[dict]:
        if self._voices is not None:
            return self._voices
        try:
            all_voices = await edge_tts.list_voices()
        except Exception as e:
            log.exception("edge_tts.list_voices() failed")
            raise VoiceFetchError(MSG_VOICE_FETCH_FAILED) from e

        filtered = []
        for v in all_voices:
            if not v.get("Locale", "").startswith(ENGLISH_LOCALE_PREFIX):
                continue
            v = dict(v)
            v["VoicePersonalities"] = v.get("VoiceTag", {}).get("VoicePersonalities", [])
            filtered.append(v)
        self._voices = filtered
        return self._voices

    def get_voices(self) -> list[dict]:
        if self._voices is None:
            raise RuntimeError(
                "Voices not loaded. Call fetch_voices() before get_voices()."
            )
        return self._voices

    def filter(self, query: str) -> list[dict]:
        voices = self.get_voices()
        if not query:
            return list(voices)
        q = query.lower()
        return [
            v for v in voices
            if q in v.get("ShortName", "").lower()
            or q in v.get("Locale", "").lower()
        ]


if __name__ == "__main__":
    import asyncio

    vm = VoiceManager()
    voices = asyncio.run(vm.fetch_voices())
    assert len(voices) > 0
    print(f"VoiceManager: OK ({len(voices)} English voices)")
