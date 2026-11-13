import re
from nltk.corpus import stopwords

STOP = set(stopwords.words("spanish"))

def limpiar(texto):
    texto = re.sub(r"http\S+|@\w+|#", "", texto.lower())
    tokens = re.findall(r"[a-záéíóúñ]+", texto)
    return [t for t in tokens if t not in STOP]
