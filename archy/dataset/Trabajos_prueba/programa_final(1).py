# Lee reglas de firewall estilo iptables y revisa si un paquete pasa
REGLAS = [
    ("ACCEPT", "tcp", 22),
    ("ACCEPT", "tcp", 443),
    ("DROP", "tcp", 23),   # telnet bloqueado
]

def evaluar(protocolo, puerto):
    for accion, proto, p in REGLAS:
        if proto == protocolo and p == puerto:
            return accion
    return "DROP"  # política por defecto: denegar
