from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Zombie(BaseModel):
    id: str
    tipo: str = Field(pattern="^(caminante|corredor|horda|dormido)$")
    nodo: str
    nodoAnterior: str | None = None
    trayecto: list[str] = Field(default_factory=list)
    visible: bool = True


class Sobreviviente(BaseModel):
    id: str
    nodo: str
    nodoAnterior: str | None = None
    trayecto: list[str] = Field(default_factory=list)
    refugio: str | None = None
    activo: bool = True
    siguienteNodo: str | None = None
    ruta: list[str] = Field(default_factory=list)
    resultado: Literal["rescatado", "mordido"] | None = None


class EventoSimulacion(BaseModel):
    id: str
    turno: int = Field(ge=0)
    tipo: Literal["bloqueo", "desvio", "despertar", "mordida", "rescate"]
    mensaje: str
    actores: list[str] = Field(default_factory=list)
    nodo: str | None = None
    arista: list[str] | None = None


class Refugio(BaseModel):
    id: str
    nodo: str
    nombre: str | None = None
    capacidad: int = Field(default=60, ge=1)
    ocupados: int = Field(default=0, ge=0)


class EstadoMundo(BaseModel):
    turno: int = Field(default=0, ge=0)
    ronda: int = Field(default=0, ge=0)
    simulacion: Literal["detenida", "iniciando", "en_curso", "completada", "error"] = "detenida"
    zombies: list[Zombie] = Field(default_factory=list)
    sobrevivientes: list[Sobreviviente] = Field(default_factory=list)
    aristasBloqueadas: list[list[str]] = Field(default_factory=list)
    refugios: list[Refugio] = Field(default_factory=list)
    eventos: list[EventoSimulacion] = Field(default_factory=list)


class PasoRequest(BaseModel):
    sobrevivienteId: str
    nodoActual: str
    turno: int = Field(ge=0)


class PasoResponse(BaseModel):
    siguienteNodo: str


class RondaInicioResponse(BaseModel):
    ronda: int
    turno: int
    estado: Literal["iniciando", "en_curso", "completada", "error"]
    mensaje: str


class EstadoCargaRequest(EstadoMundo):
    """Modelo usado solo para pruebas locales del motor."""
