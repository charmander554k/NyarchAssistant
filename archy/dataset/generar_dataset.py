"""Genera el dataset de prueba etiquetado de Archy.

Crea la carpeta `Trabajos_prueba/` con 75 archivos sintéticos (sin datos
personales) revueltos como los tendría un estudiante, y `etiquetas.csv` con la
respuesta correcta de cada uno: materia, tipo, si el nombre es descriptivo,
dificultad y tipo de caso.

Uso (desde archy/):
    python dataset/generar_dataset.py              # crea el dataset
    python dataset/generar_dataset.py --reemplazar # lo vuelve a crear desde cero

Solo para generarlo hace falta (no las usa Archy):
    pip install python-docx python-pptx openpyxl fpdf2 pillow
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
CARPETA = AQUI / "Trabajos_prueba"
ETIQUETAS = AQUI / "etiquetas.csv"

SEG = "Seguridad Informática"
MIN = "Minería de Texto"
IA = "Fundamentos de IA"
DUDA = "_Por revisar"


@dataclass(frozen=True)
class Muestra:
    archivo: str
    materia: str          # respuesta correcta (o _Por revisar si no hay forma de saberlo)
    contenido: Any        # depende del formato (ver escritores abajo)
    descriptivo: bool     # ¿el nombre ya dice de qué trata?
    dificultad: str       # facil | media | dificil
    caso: str             # normal | pista_en_nombre | ambiguo | ajeno | sin_informacion | duplicado | codificacion | extension_mayusculas
    nota: str = ""


# ---------------------------------------------------------------------------
# Contenido. Formatos:
#   .py .txt .md .csv .json -> str
#   .ipynb -> [(tipo_celda, texto)]
#   .docx  -> [párrafos]  (el primero es el título)
#   .pptx  -> [(título, [viñetas])]
#   .xlsx  -> (nombre_hoja, [filas])
#   .pdf   -> [líneas]    (solo caracteres Latin-1)
#   .png   -> (color, texto dibujado)  — Archy no lee imágenes
# ---------------------------------------------------------------------------

SEGURIDAD = [
    # Código
    Muestra("cifrado.py", SEG, '''# Cifrado César: desplaza cada letra k posiciones
ABC = "abcdefghijklmnopqrstuvwxyz"

def cifrar(texto, k):
    return "".join(ABC[(ABC.index(c) + k) % 26] if c in ABC else c for c in texto.lower())

def descifrar(texto, k):
    return cifrar(texto, -k)

print(cifrar("ataque al amanecer", 3))
''', True, "facil", "normal"),
    Muestra("a1.py", SEG, '''import random
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
''', False, "media", "normal"),
    Muestra("escaner.py", SEG, '''import socket

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
''', False, "media", "normal", "Escáner de puertos tipo nmap"),
    Muestra("hashes_contrasenas.py", SEG, '''import hashlib, os

def hash_contrasena(contrasena: str) -> str:
    sal = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal, 100_000)
    return sal.hex() + ":" + h.hex()

def verificar(contrasena, guardado):
    sal, h = guardado.split(":")
    nuevo = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), bytes.fromhex(sal), 100_000)
    return nuevo.hex() == h
''', True, "facil", "normal"),
    Muestra("programa_final(1).py", SEG, '''# Lee reglas de firewall estilo iptables y revisa si un paquete pasa
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
''', False, "media", "normal"),
    Muestra("sniff.ipynb", SEG, [
        ("markdown", "# Análisis de tráfico de red\nCaptura de paquetes con scapy para detectar escaneos."),
        ("code", "from scapy.all import sniff, TCP\n\npaquetes = sniff(count=50, filter='tcp')\nsyn = [p for p in paquetes if p[TCP].flags == 'S']\nprint(len(syn), 'paquetes SYN')"),
    ], False, "media", "normal"),
    Muestra("Untitled.ipynb", SEG, [
        ("markdown", "Práctica: cifrado simétrico con AES"),
        ("code", "from cryptography.fernet import Fernet\n\nclave = Fernet.generate_key()\nf = Fernet(clave)\ntoken = f.encrypt(b'mensaje secreto')\nprint(f.decrypt(token))"),
    ], False, "media", "normal"),
    # Documentos
    Muestra("practica3 v2.docx", SEG, [
        "Práctica 3: Cifrado RSA",
        "Objetivo: generar un par de claves pública y privada y cifrar un mensaje.",
        "Se eligieron los primos p = 61 y q = 53 y el exponente público e = 65537.",
        "Conclusión: la seguridad de RSA depende de lo difícil que es factorizar n.",
    ], False, "facil", "normal"),
    Muestra("Doc1.docx", SEG, [
        "Informe de vulnerabilidades",
        "Se revisó la aplicación web con base en el OWASP Top 10.",
        "Se encontró inyección SQL en el formulario de inicio de sesión y XSS en los comentarios.",
        "Recomendación: usar consultas parametrizadas y validar todas las entradas.",
    ], False, "media", "normal"),
    Muestra("tarea final FINAL.pdf", SEG, [
        "Politicas de contrasenas y autenticacion",
        "Una contrasena segura tiene al menos 12 caracteres y no se reutiliza.",
        "La autenticacion de dos factores (MFA) reduce el riesgo de robo de cuentas.",
        "Los ataques de fuerza bruta se mitigan bloqueando intentos fallidos.",
    ], False, "media", "normal"),
    Muestra("apuntes.txt", SEG, """Apuntes clase 4
Un firewall filtra el tráfico según reglas.
La DMZ separa los servidores públicos de la red interna.
Una VPN cifra la conexión entre dos puntos.
""", False, "media", "codificacion", "Guardado en cp1252 (acentos de Windows)"),
    Muestra("resumen_clase5.md", SEG, """# Ingeniería social y phishing

- El phishing engaña al usuario para que entregue sus credenciales.
- Señales: urgencia, remitente falso, enlaces acortados.
- Defensa: capacitación, filtros de correo y MFA.
""", False, "media", "normal"),
    Muestra("nuevo 3.txt", SEG, """nmap -sV 192.168.1.10
PORT     STATE SERVICE VERSION
22/tcp   open  ssh     OpenSSH 8.9
80/tcp   open  http    Apache 2.4.52
3306/tcp open  mysql   MySQL 8.0
Hallazgo: el puerto de la base de datos no debería estar expuesto.
""", False, "media", "normal", "Bitácora de pentest"),
    # Datos
    Muestra("datos.csv", SEG, "ip,puerto,servicio,estado\n192.168.1.10,22,ssh,abierto\n192.168.1.10,23,telnet,filtrado\n192.168.1.10,443,https,abierto\n", False, "media", "normal"),
    Muestra("log1.csv", SEG, "fecha,usuario,ip,resultado\n2026-10-01 08:00,admin,10.0.0.5,fallido\n2026-10-01 08:01,admin,10.0.0.5,fallido\n2026-10-01 08:02,admin,10.0.0.5,bloqueado\n", False, "media", "normal", "Intentos de inicio de sesión (fuerza bruta)"),
    Muestra("Libro1.xlsx", SEG, ("Riesgos", [
        ["activo", "amenaza", "vulnerabilidad", "probabilidad", "impacto"],
        ["servidor web", "inyección SQL", "entradas sin validar", "alta", "alto"],
        ["laptops", "malware", "antivirus desactualizado", "media", "medio"],
    ]), False, "media", "normal", "Matriz de riesgos"),
    Muestra("resultados.json", SEG, json.dumps({"escaneo": "vulnerabilidades", "hallazgos": [
        {"cve": "CVE-2021-44228", "nombre": "Log4Shell", "severidad": "crítica"},
        {"cve": "CVE-2014-0160", "nombre": "Heartbleed", "severidad": "alta"},
    ]}, ensure_ascii=False, indent=2), False, "media", "normal"),
    # Presentaciones
    Muestra("expo.pptx", SEG, [
        ("Criptografía simétrica y asimétrica", ["Equipo 3"]),
        ("Simétrica", ["Una sola clave", "AES, DES", "Rápida"]),
        ("Asimétrica", ["Clave pública y privada", "RSA", "Firma digital"]),
    ], False, "facil", "normal"),
    Muestra("Presentación1.pptx", SEG, [
        ("Ataques de phishing", ["Cómo reconocerlos"]),
        ("Tipos", ["Spear phishing", "Smishing", "Vishing"]),
        ("Prevención", ["Verificar el remitente", "No abrir enlaces sospechosos"]),
    ], False, "media", "normal"),
    Muestra("equipo4_final.pptx", SEG, [
        ("Seguridad en redes inalámbricas", ["WEP, WPA2 y WPA3"]),
        ("Riesgos", ["Contraseñas débiles", "Ataques de desautenticación"]),
    ], False, "media", "normal"),
    # Otros
    Muestra("captura_wireshark.png", SEG, ("#1D6289", "captura"), True, "dificil", "pista_en_nombre",
            "Archy no lee imágenes: solo el nombre da la pista"),
    Muestra("IMG_20261005.png", DUDA, ("#239CAC", "foto"), False, "dificil", "sin_informacion",
            "Imagen sin pistas: lo correcto es mandarla a revisar"),
]

MINERIA = [
    # Código
    Muestra("vdksahdas.py", MIN, '''import nltk
from sklearn.feature_extraction.text import TfidfVectorizer

documentos = ["el gato duerme", "el perro ladra", "el gato y el perro"]
vectorizador = TfidfVectorizer()
X = vectorizador.fit_transform(documentos)
print(vectorizador.get_feature_names_out())
''', False, "facil", "normal"),
    Muestra("limpieza.py", MIN, '''import re
from nltk.corpus import stopwords

STOP = set(stopwords.words("spanish"))

def limpiar(texto):
    texto = re.sub(r"http\\S+|@\\w+|#", "", texto.lower())
    tokens = re.findall(r"[a-záéíóúñ]+", texto)
    return [t for t in tokens if t not in STOP]
''', False, "facil", "normal"),
    Muestra("x.py", MIN, '''from sklearn.feature_extraction.text import CountVectorizer

corpus = ["me gusta la minería de texto", "la bolsa de palabras cuenta frecuencias"]
bolsa = CountVectorizer()
matriz = bolsa.fit_transform(corpus)
print(matriz.toarray())
''', False, "media", "normal", "Bolsa de palabras"),
    Muestra("sentimiento_v3.py", MIN, '''from textblob import TextBlob

reseñas = ["Excelente servicio", "La comida llegó fría", "Normal"]
for r in reseñas:
    polaridad = TextBlob(r).sentiment.polarity
    print(r, "->", "positivo" if polaridad > 0 else "negativo" if polaridad < 0 else "neutro")
''', True, "facil", "normal"),
    Muestra("main.py", MIN, '''import spacy

nlp = spacy.load("es_core_news_sm")
doc = nlp("Tlaxcala es un estado de México y la UPTLAX está en Tepeyanco.")
for token in doc:
    print(token.text, token.lemma_, token.pos_)
for entidad in doc.ents:
    print(entidad.text, entidad.label_)
''', False, "media", "normal", "Lematización y entidades con spaCy"),
    Muestra("practica_nube.ipynb", MIN, [
        ("markdown", "# Nube de palabras de tweets"),
        ("code", "from wordcloud import WordCloud\nimport pandas as pd\n\ntweets = pd.read_csv('tweets_limpios.csv')\ntexto = ' '.join(tweets['tweet'])\nWordCloud().generate(texto).to_file('nube.png')"),
    ], True, "facil", "normal"),
    Muestra("Untitled1.ipynb", MIN, [
        ("markdown", "Clasificación de noticias"),
        ("code", "from sklearn.feature_extraction.text import TfidfVectorizer\nfrom sklearn.naive_bayes import MultinomialNB\n\nX = TfidfVectorizer().fit_transform(noticias)\nmodelo = MultinomialNB().fit(X, categorias)"),
    ], False, "media", "normal"),
    # Documentos
    Muestra("reporte.docx", MIN, [
        "Reporte: preprocesamiento de un corpus de reseñas",
        "Se tokenizó el corpus, se eliminaron stopwords y se aplicó lematización.",
        "Después se construyó la matriz TF-IDF para comparar documentos.",
    ], False, "facil", "normal"),
    Muestra("Documento sin título.docx", MIN, [
        "La ley de Zipf",
        "En un corpus, la frecuencia de una palabra es inversamente proporcional a su rango.",
        "Por eso unas pocas palabras (stopwords) aparecen muchísimo.",
    ], False, "media", "normal"),
    Muestra("tarea2.pdf", MIN, [
        "Modelos de n-gramas",
        "Un bigrama es una secuencia de dos tokens consecutivos del texto.",
        "Se usan para predecir la siguiente palabra y para el suavizado de Laplace.",
    ], False, "media", "normal"),
    Muestra("notas.txt", MIN, """Stemming vs lematización
El stemming corta la palabra a su raíz (corriendo -> corr).
La lematización usa el diccionario (corriendo -> correr).
Ambos reducen el vocabulario del corpus.
""", False, "media", "normal"),
    Muestra("README.md", MIN, """# Análisis de tweets

Proyecto final: limpiar tweets, calcular TF-IDF y clasificar su sentimiento.

## Pasos
1. Tokenización
2. Eliminación de stopwords
3. Vectorización
""", False, "facil", "normal"),
    Muestra("copia de tarea.txt", MIN, """Similitud coseno entre documentos
Cada documento se representa como un vector de frecuencias de términos.
La similitud coseno mide el ángulo entre los vectores: 1 = iguales, 0 = sin palabras en común.
""", False, "media", "normal"),
    # Datos
    Muestra("corpus.csv", MIN, "texto,sentimiento\nme encantó la película,positivo\nno la recomiendo,negativo\nestuvo bien,neutro\n", True, "facil", "normal"),
    Muestra("tweets_limpios.csv", MIN, "id,tweet,fecha\n1,hoy aprendí tfidf,2026-10-02\n2,la minería de texto es genial,2026-10-03\n", True, "facil", "normal"),
    Muestra("Libro2.xlsx", MIN, ("Frecuencias", [
        ["término", "doc1", "doc2", "doc3"],
        ["gato", 2, 0, 1],
        ["perro", 0, 3, 1],
        ["tfidf", 1, 1, 0],
    ]), False, "media", "normal", "Matriz término-documento"),
    Muestra("stopwords.json", MIN, json.dumps({"idioma": "español", "stopwords": ["el", "la", "de", "que", "y", "en", "los"]}, ensure_ascii=False), True, "media", "normal"),
    # Presentaciones
    Muestra("expo_final.pptx", MIN, [
        ("TF-IDF explicado", ["Frecuencia de término por frecuencia inversa de documento"]),
        ("Fórmula", ["tf(t, d) · log(N / df(t))"]),
    ], False, "facil", "normal"),
    Muestra("Presentación2.pptx", MIN, [
        ("Análisis de sentimiento", ["Opiniones en redes sociales"]),
        ("Enfoques", ["Léxicos", "Aprendizaje automático"]),
    ], False, "media", "normal"),
    Muestra("equipo2.pptx", MIN, [
        ("Modelado de temas con LDA", ["Equipo 2"]),
        ("Idea", ["Cada documento es una mezcla de temas", "Cada tema es una distribución de palabras"]),
    ], False, "media", "normal"),
    # Otros
    Muestra("nube_palabras.png", MIN, ("#D9C97C", "nube"), True, "dificil", "pista_en_nombre",
            "Archy no lee imágenes: solo el nombre da la pista"),
    Muestra("grafica.png", DUDA, ("#D0DB93", "grafica"), False, "dificil", "sin_informacion",
            "Imagen sin pistas: lo correcto es mandarla a revisar"),
]

FUNDAMENTOS = [
    # Código
    Muestra("perceptron.py", IA, '''import numpy as np

class Perceptron:
    def __init__(self, n, tasa=0.1):
        self.pesos = np.zeros(n)
        self.sesgo = 0.0
        self.tasa = tasa

    def predecir(self, x):
        return 1 if np.dot(self.pesos, x) + self.sesgo > 0 else 0

    def entrenar(self, X, y, epocas=10):
        for _ in range(epocas):
            for xi, yi in zip(X, y):
                error = yi - self.predecir(xi)
                self.pesos += self.tasa * error * xi
                self.sesgo += self.tasa * error
''', True, "facil", "normal"),
    Muestra("a.py", IA, '''from collections import deque

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
''', False, "media", "normal"),
    Muestra("tarea4.py", IA, '''import heapq

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
''', False, "media", "normal", "A* con heurística"),
    Muestra("juego.py", IA, '''def minimax(tablero, maximizando):
    ganador = evaluar(tablero)
    if ganador is not None:
        return ganador
    valores = []
    for jugada in movimientos(tablero):
        valores.append(minimax(aplicar(tablero, jugada), not maximizando))
    return max(valores) if maximizando else min(valores)
''', False, "media", "normal", "Minimax para gato (tic-tac-toe)"),
    Muestra("agente_aspiradora.py", IA, '''# Agente reactivo simple: el mundo de la aspiradora
def agente(percepcion):
    ubicacion, estado = percepcion
    if estado == "sucio":
        return "aspirar"
    return "derecha" if ubicacion == "A" else "izquierda"

for p in [("A", "sucio"), ("A", "limpio"), ("B", "sucio")]:
    print(p, "->", agente(p))
''', True, "facil", "normal"),
    Muestra("Untitled2.ipynb", IA, [
        ("markdown", "Red neuronal para XOR"),
        ("code", "from sklearn.neural_network import MLPClassifier\n\nX = [[0,0],[0,1],[1,0],[1,1]]\ny = [0,1,1,0]\nred = MLPClassifier(hidden_layer_sizes=(4,), max_iter=2000).fit(X, y)\nprint(red.predict(X))"),
    ], False, "media", "normal"),
    Muestra("knn_practica.ipynb", IA, [
        ("markdown", "# K vecinos más cercanos con el dataset iris"),
        ("code", "from sklearn.neighbors import KNeighborsClassifier\nfrom sklearn.datasets import load_iris\n\nX, y = load_iris(return_X_y=True)\nknn = KNeighborsClassifier(n_neighbors=3).fit(X, y)"),
    ], True, "facil", "normal"),
    # Documentos
    Muestra("Doc2.docx", IA, [
        "Tipos de agentes inteligentes",
        "Un agente percibe su entorno mediante sensores y actúa mediante actuadores.",
        "Se describe con PEAS: medida de desempeño, entorno, actuadores y sensores.",
        "Tipos: reactivo simple, basado en modelos, basado en objetivos y basado en utilidad.",
    ], False, "facil", "normal"),
    Muestra("ensayo_final.docx", IA, [
        "Breve historia de la inteligencia artificial",
        "En 1950 Alan Turing propuso el test de Turing.",
        "En 1956 se acuñó el término inteligencia artificial en Dartmouth.",
    ], False, "media", "normal"),
    Muestra("practica5.pdf", IA, [
        "Logica difusa",
        "En la logica difusa un valor puede ser parcialmente verdadero, entre 0 y 1.",
        "Se usan funciones de pertenencia y reglas SI-ENTONCES para controlar sistemas.",
    ], False, "media", "normal"),
    Muestra("apuntes ia.txt", IA, """Búsqueda no informada vs informada
No informada: BFS, DFS, costo uniforme. No sabe qué tan lejos está la meta.
Informada: voraz y A*. Usa una heurística para estimar la distancia a la meta.
""", True, "facil", "normal"),
    Muestra("resumen.md", IA, """# Árboles de decisión

- Cada nodo pregunta por un atributo.
- Se elige el atributo con mayor ganancia de información (menor entropía).
- Riesgo: sobreajuste; se controla podando el árbol.
""", False, "media", "normal"),
    Muestra("tarea (2).txt", IA, """Problema de las 8 reinas
Se resolvió con búsqueda local (hill climbing) y reinicios aleatorios.
La función de evaluación cuenta los pares de reinas que se atacan.
""", False, "media", "normal"),
    # Datos
    Muestra("iris.csv", IA, "sepal_length,sepal_width,petal_length,petal_width,species\n5.1,3.5,1.4,0.2,setosa\n7.0,3.2,4.7,1.4,versicolor\n", True, "dificil", "normal",
            "Dataset clásico de IA, pero sus columnas no tienen palabras clave"),
    Muestra("datos_entrenamiento.csv", DUDA, "x1,x2,clase\n0,0,0\n0,1,1\n1,0,1\n1,1,0\n", False, "dificil", "sin_informacion",
            "Tabla XOR: solo números y un nombre genérico; lo correcto es mandarla a revisar"),
    Muestra("Libro3.xlsx", IA, ("Compuertas", [
        ["A", "B", "AND", "OR", "XOR"],
        [0, 0, 0, 0, 0],
        [0, 1, 0, 1, 1],
        [1, 0, 0, 1, 1],
        [1, 1, 1, 1, 0],
    ]), False, "dificil", "normal", "Tabla de verdad para el perceptrón"),
    Muestra("laberinto.json", IA, json.dumps({"descripcion": "laberinto para búsqueda A*", "inicio": [0, 0], "meta": [3, 3],
                                               "mapa": ["0010", "0110", "0000", "1100"]}, ensure_ascii=False), True, "media", "normal"),
    # Presentaciones
    Muestra("expo_ia.pptx", IA, [
        ("Redes neuronales artificiales", ["Equipo 1"]),
        ("Neurona", ["Entradas, pesos, sesgo", "Función de activación"]),
        ("Entrenamiento", ["Retropropagación", "Descenso de gradiente"]),
    ], False, "facil", "normal"),
    Muestra("Presentación3.pptx", IA, [
        ("Algoritmos de búsqueda", ["BFS, DFS y A*"]),
        ("Heurísticas", ["Admisibles", "Consistentes"]),
    ], False, "media", "normal"),
    Muestra("equipo1_final.pptx", IA, [
        ("Ética en la inteligencia artificial", ["Sesgos y transparencia"]),
        ("Principios", ["Supervisión humana", "Privacidad", "Rendición de cuentas"]),
    ], False, "media", "normal"),
    # Otros
    Muestra("grafo_busqueda.png", IA, ("#152F67", "grafo"), True, "dificil", "pista_en_nombre",
            "Archy no lee imágenes: solo el nombre da la pista"),
    Muestra("captura.png", DUDA, ("#5B6B7F", "captura"), False, "dificil", "sin_informacion",
            "Imagen sin pistas: lo correcto es mandarla a revisar"),
]

DIFICILES = [
    Muestra("proyecto_integrador.docx", SEG, [
        "Proyecto integrador: detección de correos de phishing",
        "Se entrenó un clasificador con TF-IDF sobre el texto de los correos.",
        "El objetivo es proteger a los usuarios de ataques de ingeniería social y robo de credenciales.",
    ], False, "dificil", "ambiguo", "Mezcla Minería de Texto (TF-IDF) con Seguridad (phishing); el objetivo es de seguridad"),
    Muestra("clasificador_spam.py", MIN, '''from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

# Filtro de spam: clasificación de textos de correos
correos = ["gana dinero rápido", "reunión mañana a las 10"]
etiquetas = [1, 0]
X = CountVectorizer().fit_transform(correos)
MultinomialNB().fit(X, etiquetas)
''', True, "dificil", "ambiguo", "Puede parecer de IA (Naive Bayes), pero es clasificación de texto"),
    Muestra("agente_ids.py", SEG, '''# Agente que detecta intrusos: si ve muchos intentos fallidos, bloquea la IP
UMBRAL = 5

def agente(percepcion, historial):
    ip, resultado = percepcion
    if resultado == "fallido":
        historial[ip] = historial.get(ip, 0) + 1
    return "bloquear" if historial.get(ip, 0) >= UMBRAL else "permitir"
''', False, "dificil", "ambiguo", "Usa la idea de agente (IA), pero es un sistema de detección de intrusos (Seguridad)"),
    Muestra("receta_pastel.txt", DUDA, """Pastel de chocolate
Ingredientes: 2 tazas de harina, 1 taza de azúcar, 3 huevos, cacao.
Hornear 40 minutos a 180 grados.
""", True, "facil", "ajeno", "No es de ninguna materia"),
    Muestra("horario_semestre.pdf", DUDA, [
        "Horario del semestre",
        "Lunes: Seguridad Informatica 8:00",
        "Martes: Mineria de Texto 10:00",
        "Miercoles: Fundamentos de IA 12:00",
    ], True, "dificil", "ajeno", "Menciona las tres materias por igual: no pertenece a ninguna"),
    Muestra("lista_compras.xlsx", DUDA, ("Compras", [
        ["producto", "cantidad"],
        ["cuadernos", 3],
        ["plumas", 5],
    ]), True, "facil", "ajeno", "No es de ninguna materia"),
    Muestra("perceptron (copia).py", IA, None, False, "media", "duplicado",
            "Mismo contenido que perceptron.py (mismo hash): el planificador debe detectarlo"),
    Muestra("PRACTICA_RSA.PDF", SEG, [
        "Practica: firma digital con RSA",
        "Se firma el hash del mensaje con la clave privada y se verifica con la publica.",
    ], True, "media", "extension_mayusculas", "Extensión en mayúsculas: el nombre final debe quedar en .pdf"),
    Muestra("notas_vacias.txt", DUDA, "", False, "dificil", "sin_informacion", "Archivo vacío"),
]

MUESTRAS = SEGURIDAD + MINERIA + FUNDAMENTOS + DIFICILES
ORIGEN_DUPLICADOS = {"perceptron (copia).py": "perceptron.py"}
CODIFICACION = {"apuntes.txt": "cp1252"}


# ---------------------------------------------------------------------------
# Escritores por formato
# ---------------------------------------------------------------------------

def escribir_docx(ruta: Path, parrafos: list[str]) -> None:
    from docx import Document
    doc = Document()
    doc.add_heading(parrafos[0], level=1)
    for p in parrafos[1:]:
        doc.add_paragraph(p)
    doc.save(ruta)


def escribir_pptx(ruta: Path, diapositivas: list) -> None:
    from pptx import Presentation
    pres = Presentation()
    for i, (titulo, vinetas) in enumerate(diapositivas):
        diseno = pres.slide_layouts[0 if i == 0 else 1]
        diapositiva = pres.slides.add_slide(diseno)
        diapositiva.shapes.title.text = titulo
        cuerpo = diapositiva.placeholders[1].text_frame
        cuerpo.text = vinetas[0] if vinetas else ""
        for v in vinetas[1:]:
            cuerpo.add_paragraph().text = v
    pres.save(ruta)


def escribir_xlsx(ruta: Path, datos) -> None:
    from openpyxl import Workbook
    hoja_nombre, filas = datos
    libro = Workbook()
    hoja = libro.active
    hoja.title = hoja_nombre
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)


def escribir_pdf(ruta: Path, lineas: list[str]) -> None:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, lineas[0], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=12)
    for linea in lineas[1:]:
        pdf.multi_cell(0, 8, linea, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(ruta))


def escribir_png(ruta: Path, datos) -> None:
    from PIL import Image, ImageDraw
    color, texto = datos
    img = Image.new("RGB", (320, 200), color)
    ImageDraw.Draw(img).text((20, 90), texto, fill="white")
    img.save(ruta)


def escribir_ipynb(ruta: Path, celdas: list) -> None:
    cuaderno = {
        "cells": [
            {"cell_type": tipo, "metadata": {}, "source": texto.splitlines(keepends=True),
             **({"outputs": [], "execution_count": None} if tipo == "code" else {})}
            for tipo, texto in celdas
        ],
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    ruta.write_text(json.dumps(cuaderno, ensure_ascii=False, indent=1), encoding="utf-8")


def escribir(muestra: Muestra, carpeta: Path) -> None:
    ruta = carpeta / muestra.archivo
    extension = ruta.suffix.lower()
    if muestra.archivo in ORIGEN_DUPLICADOS:
        shutil.copyfile(carpeta / ORIGEN_DUPLICADOS[muestra.archivo], ruta)
    elif extension == ".docx":
        escribir_docx(ruta, muestra.contenido)
    elif extension == ".pptx":
        escribir_pptx(ruta, muestra.contenido)
    elif extension == ".xlsx":
        escribir_xlsx(ruta, muestra.contenido)
    elif extension == ".pdf":
        escribir_pdf(ruta, muestra.contenido)
    elif extension == ".png":
        escribir_png(ruta, muestra.contenido)
    elif extension == ".ipynb":
        escribir_ipynb(ruta, muestra.contenido)
    else:
        ruta.write_text(muestra.contenido, encoding=CODIFICACION.get(muestra.archivo, "utf-8"), newline="\n")


def tipo_de(extension: str) -> str:
    """Igual que config.yaml: así la etiqueta 'tipo' coincide con lo que espera Archy."""
    sys.path.insert(0, str(AQUI.parent))
    from nucleo.configuracion import cargar_config
    return cargar_config(AQUI.parent / "config.yaml").tipo_de(extension)


def main() -> int:
    analizador = argparse.ArgumentParser(description="Genera el dataset de prueba de Archy.")
    analizador.add_argument("--reemplazar", action="store_true", help="borrar y volver a crear Trabajos_prueba/")
    args = analizador.parse_args()

    nombres = [m.archivo for m in MUESTRAS]
    repetidos = {n for n in nombres if nombres.count(n) > 1}
    if repetidos:
        print(f"ERROR: nombres repetidos en el dataset: {sorted(repetidos)}")
        return 1

    if CARPETA.exists():
        if not args.reemplazar:
            print(f"Ya existe {CARPETA}. Usa --reemplazar para volver a crearlo.")
            return 1
        shutil.rmtree(CARPETA)  # solo la carpeta generada por este script
    CARPETA.mkdir(parents=True)

    for muestra in sorted(MUESTRAS, key=lambda m: m.archivo in ORIGEN_DUPLICADOS):
        escribir(muestra, CARPETA)

    with open(ETIQUETAS, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["archivo", "materia", "tipo", "nombre_descriptivo", "dificultad", "caso", "nota"])
        for m in MUESTRAS:
            escritor.writerow([m.archivo, m.materia, tipo_de(Path(m.archivo).suffix), "si" if m.descriptivo else "no",
                               m.dificultad, m.caso, m.nota])

    print(f"Dataset creado: {len(MUESTRAS)} archivos en {CARPETA}")
    print(f"Etiquetas: {ETIQUETAS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
