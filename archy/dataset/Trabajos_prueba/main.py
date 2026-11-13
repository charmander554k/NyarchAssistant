import spacy

nlp = spacy.load("es_core_news_sm")
doc = nlp("Tlaxcala es un estado de México y la UPTLAX está en Tepeyanco.")
for token in doc:
    print(token.text, token.lemma_, token.pos_)
for entidad in doc.ents:
    print(entidad.text, entidad.label_)
