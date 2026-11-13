from collections import deque

def bfs(grafo, inicio, meta):
    """Búsqueda en anchura: encuentra el camino más corto en pasos."""
    cola = deque([[inicio]])
    visitados = {inicio}
    while cola:
        camino = cola.popleft()
        if camino[-1] == meta:
            return camino
        for vecino in grafo[camino[-1]]:
            if vecino not in visitados:
                visitados.add(vecino)
                cola.append(camino + [vecino])
