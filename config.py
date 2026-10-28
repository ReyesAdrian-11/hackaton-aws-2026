from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
GRAPHML_PATH = Path(os.getenv("GRAPHML_PATH", str(BASE_DIR / "manta_grafo.graphml")))
REFUGES_PATH = Path(os.getenv("REFUGES_PATH", str(BASE_DIR / "refugios.json")))
API_KEY = os.getenv("SPOOKYTHON_API_KEY", "dev-secret-key")
