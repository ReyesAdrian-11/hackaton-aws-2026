from __future__ import annotations

from threading import RLock

from models import EstadoMundo


class WorldStore:
    """Estado temporal del mundo. Será reemplazable por Redis en AWS."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._state = EstadoMundo()
        # Número de turno cacheado para respuesta rápida sin deep-copy.
        self._turno: int = 0

    def get(self) -> EstadoMundo:
        with self._lock:
            return self._state.model_copy(deep=True)

    def get_turno(self) -> int:
        """Retorna el turno actual sin deep-copy. O(1) para validación rápida."""
        return self._turno

    def replace(self, state: EstadoMundo) -> EstadoMundo:
        with self._lock:
            self._state = state.model_copy(deep=True)
            self._turno = self._state.turno
            return self._state.model_copy(deep=True)


store = WorldStore()
