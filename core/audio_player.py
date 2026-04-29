import os
import tempfile

import pygame


class AudioPlayer:
    def __init__(self) -> None:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        self._path: str | None = None
        self._paused: bool = False

    def load(self, path: str) -> None:
        self.stop()
        pygame.mixer.music.load(path)
        self._path = path
        self._paused = False

    def play(self) -> None:
        pygame.mixer.music.play()
        self._paused = False

    def pause(self) -> None:
        if self._paused:
            pygame.mixer.music.unpause()
            self._paused = False
        else:
            pygame.mixer.music.pause()
            self._paused = True

    def stop(self) -> None:
        pygame.mixer.music.stop()
        self._paused = False

    def is_playing(self) -> bool:
        return bool(pygame.mixer.music.get_busy()) and not self._paused

    def cleanup(self) -> None:
        self.stop()
        try:
            pygame.mixer.music.unload()
        except (AttributeError, pygame.error):
            pass

        path = self._path
        self._path = None
        if path and os.path.exists(path):
            try:
                tmp_root = os.path.realpath(tempfile.gettempdir())
                if os.path.realpath(path).startswith(tmp_root + os.sep):
                    os.remove(path)
            except OSError:
                pass


if __name__ == "__main__":
    import asyncio
    import time

    import edge_tts

    # Use dummy audio driver if no real one available (CI / headless)
    if not os.environ.get("SDL_AUDIODRIVER") and not os.environ.get("DISPLAY"):
        os.environ["SDL_AUDIODRIVER"] = "dummy"

    async def make_clip(path: str):
        comm = edge_tts.Communicate(
            "Audio player smoke test. This is a short phrase that plays for a few seconds.",
            "en-US-JennyNeural",
        )
        await comm.save(path)

    fd, mp3 = tempfile.mkstemp(prefix="audio_player_test_", suffix=".mp3")
    os.close(fd)
    asyncio.run(make_clip(mp3))
    assert os.path.getsize(mp3) > 0

    player = AudioPlayer()
    player.load(mp3)
    player.play()
    time.sleep(1.0)
    assert player.is_playing(), "expected is_playing() True after 1s"
    print("  playing — OK")

    player.pause()
    time.sleep(0.2)
    assert not player.is_playing(), "expected is_playing() False while paused"
    print("  paused — OK")

    player.pause()  # unpause
    time.sleep(0.5)
    assert player.is_playing(), "expected is_playing() True after unpause"
    print("  unpaused — OK")

    player.stop()
    # Briefly let the mixer settle
    time.sleep(0.1)
    assert not player.is_playing(), "expected is_playing() False after stop"
    print("  stopped — OK")

    player.cleanup()
    assert not os.path.exists(mp3), f"temp file should be deleted: {mp3}"
    print("  cleanup deleted temp file — OK")

    print("AudioPlayer: OK")
