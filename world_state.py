from __future__ import annotations

from threading import RLock
from models import EstadoMundo


class WorldStore:
    """Estado temporal del mundo durante la sesión de EC2."""

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

    def get_blocked_edges(self) -> set[frozenset[str]]:
        """Retorna solo los cierres, evitando copiar actores para /paso."""
        with self._lock:
            return {frozenset(edge) for edge in self._state.aristasBloqueadas}

    def replace(self, state: EstadoMundo) -> EstadoMundo:
        with self._lock:
            self._state = state.model_copy(deep=True)
            self._turno = self._state.turno
            return self._state.model_copy(deep=True)

    def bootstrap(self, initial: EstadoMundo) -> EstadoMundo:
        """Initialize the in-memory session at process startup."""
        return self.replace(initial)


store = WorldStore()
