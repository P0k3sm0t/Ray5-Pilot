from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Any


class ConsoleLog:
    def __init__(self, maxlen: int = 400) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = Lock()

    def add(self, level: str, message: str) -> None:
        with self._lock:
            self._items.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "level": level.upper(), "message": message})

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
