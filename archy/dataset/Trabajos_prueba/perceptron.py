import numpy as np

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
