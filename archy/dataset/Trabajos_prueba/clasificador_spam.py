from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

# Filtro de spam: clasificación de textos de correos
correos = ["gana dinero rápido", "reunión mañana a las 10"]
etiquetas = [1, 0]
X = CountVectorizer().fit_transform(correos)
MultinomialNB().fit(X, etiquetas)
