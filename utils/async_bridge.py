import asyncio
import logging
import threading
from typing import Any, Awaitable, Callable, Optional

log = logging.getLogger(__name__)


class AsyncBridge:
    """Bridge between a Tkinter main thread and a dedicated asyncio loop.

    A single background thread owns one event loop for the lifetime of the
    bridge. Coroutines submitted via run_async() execute on that loop, and
    their results are delivered back to the Tk main thread via root.after().
    """

    def __init__(self, root) -> None:
        self._root = root
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, name="AsyncBridge", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        try:
            self._loop.run_forever()
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            finally:
                self._loop.close()

    def run_async(
        self,
        coro: Awaitable[Any],
        on_complete: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[BaseException], None]] = None,
    ):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _done(fut):
            try:
                result = fut.result()
            except asyncio.CancelledError:
                return  # bridge is shutting down — drop silently
            except BaseException as exc:
                log.exception("Async coroutine failed: %r", exc)
                if on_error is not None:
                    self._safe_after(on_error, exc)
                else:
                    log.error("No on_error handler registered for failing coroutine")
                return
            if on_complete is not None:
                self._safe_after(on_complete, result)

        future.add_done_callback(_done)
        return future

    def _safe_after(self, fn, *args) -> None:
        try:
            self._root.after(0, fn, *args)
        except (RuntimeError, Exception):
            # Tk root has been destroyed; nothing to deliver to.
            pass

    def shutdown(self) -> None:
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


if __name__ == "__main__":
    import asyncio as _asyncio
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    bridge = AsyncBridge(root)

    state = {"result": None, "error": None, "done": False}

    async def sample():
        await _asyncio.sleep(0.1)
        return "ok"

    def on_complete(result):
        state["result"] = result
        state["done"] = True

    def on_error(exc):
        state["error"] = exc
        state["done"] = True

    bridge.run_async(sample(), on_complete=on_complete, on_error=on_error)

    def poll():
        if state["done"]:
            root.quit()
        else:
            root.after(20, poll)

    root.after(20, poll)
    root.after(3000, root.quit)  # safety timeout
    root.mainloop()

    assert state["error"] is None, f"unexpected error: {state['error']}"
    assert state["result"] == "ok", f"expected 'ok', got {state['result']!r}"

    bridge.shutdown()
    root.destroy()
    print("AsyncBridge: OK")
