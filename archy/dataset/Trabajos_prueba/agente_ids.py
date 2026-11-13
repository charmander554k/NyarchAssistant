# Agente que detecta intrusos: si ve muchos intentos fallidos, bloquea la IP
UMBRAL = 5

def agente(percepcion, historial):
    ip, resultado = percepcion
    if resultado == "fallido":
        historial[ip] = historial.get(ip, 0) + 1
    return "bloquear" if historial.get(ip, 0) >= UMBRAL else "permitir"
