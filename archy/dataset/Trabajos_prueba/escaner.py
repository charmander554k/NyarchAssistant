import socket

def escanear_puertos(host, puertos):
    abiertos = []
    for puerto in puertos:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        if s.connect_ex((host, puerto)) == 0:
            abiertos.append(puerto)
        s.close()
    return abiertos

print(escanear_puertos("127.0.0.1", [21, 22, 80, 443, 3306]))
