from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
GRAPHML_PATH = Path(os.getenv("GRAPHML_PATH", str(BASE_DIR / "manta_grafo.graphml")))
REFUGES_PATH = Path(os.getenv("REFUGES_PATH", str(BASE_DIR / "refugios.json")))
ZONES_PATH = Path(os.getenv("ZONES_PATH", str(BASE_DIR / "zonas_iniciales.json")))
API_KEY = os.getenv("SPOOKYTHON_API_KEY", "dev-secret-key")
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "SPOOKYTHON_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
