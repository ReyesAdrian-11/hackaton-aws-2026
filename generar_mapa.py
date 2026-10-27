"""
generar_mapa.py
Descarga la red vial de Manta, Manabí, Ecuador y la guarda como GraphML.

Uso:
    python generar_mapa.py

Requiere conexión a Internet. El archivo resultante (manta_grafo.graphml)
puede pesar entre 3 y 15 MB dependiendo de la densidad de la red.
"""

import osmnx as ox
import os
import time

# Cambiar el servidor a un espejo alternativo para evadir el colapso (Error 502)
ox.settings.overpass_endpoint = 'https://overpass.kumi.systems/api/interpreter'
# Aumentar el tiempo de espera por si la red está lenta
ox.settings.timeout = 180 

LUGAR = "Manta, Manabi, Ecuador"
ARCHIVO_SALIDA = "manta_grafo.graphml"


def descargar_grafo(lugar: str, archivo: str) -> None:
    print(f"[1/3] Descargando red vial de '{lugar}' usando servidor alternativo...")
    inicio = time.time()

    # network_type='drive' incluye solo calles transitables en vehículo
    G = ox.graph_from_place(lugar, network_type="drive")

    elapsed = time.time() - inicio
    print(f"      Descarga completada en {elapsed:.1f}s")
    print(f"      Nodos: {G.number_of_nodes()} | Aristas: {G.number_of_edges()}")

    print(f"[2/3] Guardando grafo en '{archivo}'...")
    ox.save_graphml(G, filepath=archivo)

    size_mb = os.path.getsize(archivo) / (1024 * 1024)
    print(f"[3/3] Archivo guardado ({size_mb:.2f} MB) — listo para el servidor.")


if __name__ == "__main__":
    descargar_grafo(LUGAR, ARCHIVO_SALIDA)
