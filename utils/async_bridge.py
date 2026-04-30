import asyncio
import logging
import queue
import threading
from typing import Any, Awaitable, Callable, Optional

log = logging.getLogger(__name__)

_POLL_INTERVAL_MS = 50


class AsyncBridge:
    """Bridge between a Tkinter main thread and a dedicated asyncio loop.

    A single background thread owns one event loop for the lifetime of the
    bridge. Coroutines submitted via run_async() execute on that loop, and
    their results are delivered to the Tk main thread via a thread-safe
    queue drained by a periodic Tk timer.

    Why not Tk.after() from the worker thread: tkinter's after() is not
    thread-safe and can fail silently on Windows — completed callbacks
    never fire and there is no exception to log. Queue + polling is the
    canonical workaround.
    """

    def __init__(self, root) -> None:
        self._root = root
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._tk_queue: "queue.Queue[tuple[Callable, tuple]]" = queue.Queue()
        self._poll_active = True
        self._thread = threading.Thread(
            target=self._run_loop, name="AsyncBridge", daemon=True
        )
        self._thread.start()
        self._ready.wait()
        # Kick off the Tk-side polling drain. Always invoked from the main
        # (Tk) thread, so it can call root.after() safely.
        self._root.after(_POLL_INTERVAL_MS, self._drain_queue)

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
                    self._enqueue(on_error, (exc,))
                else:
                    log.error("No on_error handler registered for failing coroutine")
                return
            if on_complete is not None:
                self._enqueue(on_complete, (result,))

        future.add_done_callback(_done)
        return future

    def _enqueue(self, fn: Callable, args: tuple) -> None:
        """Thread-safe: called from the asyncio worker thread."""
        try:
            self._tk_queue.put_nowait((fn, args))
        except Exception:
            log.exception("Failed to enqueue callback for Tk delivery")

    def _drain_queue(self) -> None:
        """Runs on the Tk main thread. Pulls every ready callback off the
        queue and invokes it. Each callback is wrapped so a UI-side error
        is logged rather than silently killing the polling loop."""
        try:
            while True:
                try:
                    fn, args = self._tk_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    fn(*args)
                except Exception:
                    log.exception(
                        "Tk-side callback raised: fn=%r args_len=%d",
                        getattr(fn, "__name__", fn), len(args),
                    )
        finally:
            if self._poll_active:
                try:
                    self._root.after(_POLL_INTERVAL_MS, self._drain_queue)
                except Exception:
                    log.exception("Failed to reschedule Tk drain timer")

    def shutdown(self) -> None:
        self._poll_active = False
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
