import hashlib, os

def hash_contrasena(contrasena: str) -> str:
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal, 100_000)
    return sal.hex() + ":" + h.hex()

def verificar(contrasena, guardado):
    sal, h = guardado.split(":")
    nuevo = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), bytes.fromhex(sal), 100_000)
    return nuevo.hex() == h
