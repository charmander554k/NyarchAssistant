from sklearn.feature_extraction.text import CountVectorizer

corpus = ["me gusta la minería de texto", "la bolsa de palabras cuenta frecuencias"]
bolsa = CountVectorizer()
matriz = bolsa.fit_transform(corpus)
print(matriz.toarray())
