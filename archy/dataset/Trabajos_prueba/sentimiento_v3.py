from textblob import TextBlob

reseñas = ["Excelente servicio", "La comida llegó fría", "Normal"]
for r in reseñas:
    polaridad = TextBlob(r).sentiment.polarity
    print(r, "->", "positivo" if polaridad > 0 else "negativo" if polaridad < 0 else "neutro")
