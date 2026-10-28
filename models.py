from __future__ import annotations

from pydantic import BaseModel, Field


class Zombie(BaseModel):
    id: str
    tipo: str = Field(pattern="^(caminante|corredor|horda|dormido)$")
    nodo: str
    visible: bool = True


class Sobreviviente(BaseModel):
    id: str
    nodo: str
    refugio: str | None = None
    activo: bool = True


class Refugio(BaseModel):
    id: str
    nodo: str
    nombre: str | None = None
    capacidad: int = Field(default=60, ge=1)
    ocupados: int = Field(default=0, ge=0)


class EstadoMundo(BaseModel):
    turno: int = Field(default=0, ge=0)
    zombies: list[Zombie] = Field(default_factory=list)
    sobrevivientes: list[Sobreviviente] = Field(default_factory=list)
    aristasBloqueadas: list[list[str]] = Field(default_factory=list)
    refugios: list[Refugio] = Field(default_factory=list)


class PasoRequest(BaseModel):
    sobrevivienteId: str
    nodoActual: str
    turno: int = Field(ge=0)


class PasoResponse(BaseModel):
    siguienteNodo: str


class EstadoCargaRequest(EstadoMundo):
    """Modelo usado solo para pruebas locales del motor."""
