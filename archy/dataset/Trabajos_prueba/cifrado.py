# Cifrado César: desplaza cada letra k posiciones
ABC = "abcdefghijklmnopqrstuvwxyz"

def cifrar(texto, k):
    return "".join(ABC[(ABC.index(c) + k) % 26] if c in ABC else c for c in texto.lower())

def descifrar(texto, k):
    return cifrar(texto, -k)

print(cifrar("ataque al amanecer", 3))
