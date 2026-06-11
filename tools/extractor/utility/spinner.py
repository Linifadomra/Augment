#!/usr/bin/env python3
import sys
import time
import threading

_SPINNER_UNICODE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_ASCII   = "-\\|/"
_BAR_FULL_UNICODE  = "█"
_BAR_EMPTY_UNICODE = "░"
_BAR_FULL_ASCII    = "#"
_BAR_EMPTY_ASCII   = "-"
_DONE_UNICODE = "✓"
_DONE_ASCII   = "+"


def _supports_unicode() -> bool:
    try:
        return sys.stdout.encoding.lower().replace("-", "") in ("utf8", "utf16", "utf32")
    except AttributeError:
        return False

_UNICODE = _supports_unicode()


class Progress:
    """
    Minimal thread-safe spinner + progress bar.

    Manual usage:
        p = Progress("walking TUs", total=1827)
        p.start()
        for item in work:
            process(item)
            p.increment()
        p.finish()

    Context manager usage:
        with Progress("walking TUs", total=len(items)) as p:
            for item in items:
                process(item)
                p.increment()
    """

    def __init__(self, label: str, total: int, bar_width: int = 50, interval: float = 0.1):
        self.label      = label
        self.total      = total
        self.bar_width  = bar_width
        self.interval   = interval
        self._counter   = [0]
        self._lock      = threading.Lock()
        self._stop      = threading.Event()
        self._thread    = threading.Thread(target=self._run, daemon=True)

        self._spinner   = _SPINNER_ASCII   if not _UNICODE else _SPINNER_UNICODE
        self._full      = _BAR_FULL_ASCII  if not _UNICODE else _BAR_FULL_UNICODE
        self._empty     = _BAR_EMPTY_ASCII if not _UNICODE else _BAR_EMPTY_UNICODE
        self._done_char = _DONE_ASCII      if not _UNICODE else _DONE_UNICODE

    def start(self) -> "Progress":
        self._start = time.time()
        self._thread.start()
        return self

    def increment(self, n: int = 1) -> None:
        with self._lock:
            self._counter[0] = min(self._counter[0] + n, self.total)

    def finish(self) -> None:
        self._stop.set()
        self._thread.join()
        bar = self._full * self.bar_width
        print(f"\r{self._done_char} [{bar}] 100.0%  {self.total}/{self.total} {self.label}  done{' ' * 20}")

    def __enter__(self) -> "Progress":
        return self.start()

    def __exit__(self, *_) -> None:
        self.finish()

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            with self._lock:
                done = self._counter[0]

            elapsed = time.time() - self._start
            rate    = done / elapsed if elapsed > 0 else 0
            eta     = (self.total - done) / rate if rate > 0 else 0
            pct     = done / self.total * 100 if self.total > 0 else 0

            filled  = int(pct / 100 * self.bar_width)
            bar     = self._full * filled + self._empty * (self.bar_width - filled)
            spin    = self._spinner[i % len(self._spinner)]

            print(
                f"\r{spin} [{bar}] {pct:5.1f}%  {done}/{self.total} {self.label}  "
                f"ETA {int(eta // 60)}m{int(eta % 60):02d}s   ",
                end="", flush=True,
            )
            i += 1
            time.sleep(self.interval)
