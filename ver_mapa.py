import osmnx as ox

print("Cargando el grafo...")
# Leer el archivo que acabas de generar
grafo = ox.load_graphml("manta_grafo.graphml")

print("Dibujando... (se abrirá una ventana emergente)")
# Renderizar visualmente los nodos y aristas
fig, ax = ox.plot_graph(grafo, node_color='red', node_size=15, edge_color='white', bgcolor='black')