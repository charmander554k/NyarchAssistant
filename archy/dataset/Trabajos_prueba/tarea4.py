import heapq

def heuristica(a, b):
    # distancia Manhattan
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def a_estrella(inicio, meta, vecinos):
    abierta = [(0, inicio)]
    costo = {inicio: 0}
    while abierta:
        _, actual = heapq.heappop(abierta)
        if actual == meta:
            return costo[actual]
        for v in vecinos(actual):
            nuevo = costo[actual] + 1
            if nuevo < costo.get(v, float("inf")):
                costo[v] = nuevo
                heapq.heappush(abierta, (nuevo + heuristica(v, meta), v))
