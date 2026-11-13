import random
from math import gcd

def generar_claves(p, q):
    """Genera el par de claves RSA a partir de dos primos."""
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    while gcd(e, phi) != 1:
        e = random.randrange(3, phi, 2)
    d = pow(e, -1, phi)
    return (e, n), (d, n)

publica, privada = generar_claves(61, 53)
mensaje_cifrado = pow(42, publica[0], publica[1])
