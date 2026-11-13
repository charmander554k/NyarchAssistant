def minimax(tablero, maximizando):
    ganador = evaluar(tablero)
    if ganador is not None:
        return ganador
    valores = []
    for jugada in movimientos(tablero):
        valores.append(minimax(aplicar(tablero, jugada), not maximizando))
    return max(valores) if maximizando else min(valores)
