from __future__ import annotations

from threading import RLock

from models import EstadoMundo


class WorldStore:
    """Estado temporal del mundo. Será reemplazable por Redis en AWS."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._state = EstadoMundo()

    def get(self) -> EstadoMundo:
        with self._lock:
            return self._state.model_copy(deep=True)

    def replace(self, state: EstadoMundo) -> EstadoMundo:
        with self._lock:
            self._state = state.model_copy(deep=True)
            return self.get()


store = WorldStore()
