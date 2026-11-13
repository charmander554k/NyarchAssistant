import nltk
from sklearn.feature_extraction.text import TfidfVectorizer

documentos = ["el gato duerme", "el perro ladra", "el gato y el perro"]
vectorizador = TfidfVectorizer()
X = vectorizador.fit_transform(documentos)
print(vectorizador.get_feature_names_out())
