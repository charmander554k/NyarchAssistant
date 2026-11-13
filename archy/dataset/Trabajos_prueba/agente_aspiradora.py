# Agente reactivo simple: el mundo de la aspiradora
def agente(percepcion):
    ubicacion, estado = percepcion
    if estado == "sucio":
        return "aspirar"
    return "derecha" if ubicacion == "A" else "izquierda"

for p in [("A", "sucio"), ("A", "limpio"), ("B", "sucio")]:
    print(p, "->", agente(p))
