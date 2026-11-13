# Dataset de prueba de Archy

75 archivos sintéticos (sin datos personales) que simulan la carpeta `Trabajos` de un estudiante de TIID: archivos de **Seguridad Informática**, **Minería de Texto** y **Fundamentos de IA** revueltos y con nombres poco claros (`Doc1.docx`, `Untitled.ipynb`, `tarea final FINAL.pdf`, `vdksahdas.py`…). Sirve para **medir** el clasificador de Archy (meta: ≥ 85 % de exactitud en materia).

- `Trabajos_prueba/`: los archivos.
- `etiquetas.csv`: la respuesta correcta de cada archivo.
- `generar_dataset.py`: crea los dos anteriores (reproducible).
- `verificar_dataset.py`: revisa el dataset y mide una línea base.

## Composición

| Materia | Código | Documentos | Datos | Presentaciones | Otros | Total |
|---|---|---|---|---|---|---|
| Seguridad Informática | 8 | 8 | 4 | 3 | 1 | 24 |
| Minería de Texto | 8 | 6 | 4 | 3 | 1 | 22 |
| Fundamentos de IA | 8 | 6 | 3 | 3 | 1 | 21 |
| `_Por revisar` | 0 | 3 | 2 | 0 | 3 | 8 |
| **Total** | 24 | 23 | 13 | 9 | 6 | **75** |

Formatos: `.py`, `.ipynb`, `.txt`, `.md`, `.json`, `.csv`, `.xlsx`, `.docx`, `.pptx`, `.pdf` y `.png`. Los de Office y PDF son archivos reales: se abren en Word, PowerPoint, Excel o cualquier lector de PDF.

**Casos difíciles a propósito (17):**
- **Ambiguos (3):** por ejemplo, un detector de phishing con TF-IDF, que mezcla Seguridad y Minería.
- **Ajenos a las materias (3):** una receta, una lista de compras y un horario que menciona las tres materias.
- **Sin información (5):** imágenes sin pistas, una tabla XOR con nombre genérico y un archivo vacío.
- **Pista solo en el nombre (3):** imágenes como `captura_wireshark.png`.
- **Duplicado (1):** `perceptron (copia).py`, con el mismo hash que `perceptron.py`.
- **Acentos en cp1252 (1):** `apuntes.txt`.
- **Extensión en mayúsculas (1):** `PRACTICA_RSA.PDF`.

54 de los 75 nombres **no son descriptivos**: ese es justo el problema que Archy resuelve.

## Regla para etiquetar

La etiqueta `materia` es **lo que haría un agente correcto**. Si un archivo no tiene ninguna pista (una imagen `IMG_20261005.png`, un archivo vacío, una tabla solo de números) o no pertenece a ninguna materia, la respuesta correcta es `_Por revisar`, no adivinar.

Columnas de `etiquetas.csv`: `archivo`, `materia`, `tipo` (sale de la extensión, igual que en `config.yaml`), `nombre_descriptivo` (si/no), `dificultad` (facil/media/dificil), `caso` y `nota`.

## Cómo usarlo

Desde `archy/` (en Windows usa `.venv\Scripts\python`):

```bash
python dataset/verificar_dataset.py            # integridad, composición, lectura, duplicados y línea base
python dataset/verificar_dataset.py --detalle  # además, cada error de la línea base
python demo_extractor.py dataset/Trabajos_prueba   # qué lee Archy de cada archivo
python -m pytest tests/test_dataset.py         # pruebas de consistencia
```

Para probarlo en NyarchAssistant, copia el dataset a tu carpeta `Trabajos`. Nunca sobrescribe: si un archivo ya existe, lo deja como está.

```bash
python dataset/verificar_dataset.py --copiar-a "C:\Users\<usuario>\Documents\Trabajos"
```

Para volver a generarlo (por ejemplo, después de agregar muestras en `generar_dataset.py`):

```bash
pip install python-docx python-pptx openpyxl fpdf2 pillow   # solo para generar; Archy no las usa
python dataset/generar_dataset.py --reemplazar
```

## Línea base (13 nov 2026)

Un clasificador que **solo cuenta las palabras clave** de `config.yaml` en el nombre y el texto acierta **59 de 75 (79 %)**:

| Grupo | Exactitud |
|---|---|
| Fáciles | 90 % |
| Medios | 80 % |
| Difíciles | 57 % |

Falla, por ejemplo:
- en `cifrado.py`, porque contiene la palabra "texto";
- en hojas de cálculo y presentaciones sin palabras clave;
- en el horario que menciona las tres materias.

Por eso el clasificador real agrega contenido, embeddings y Qwen para los casos dudosos. Esta cifra es la referencia para medir si cada mejora ayuda.

## Pendiente

Agregar 10 a 15 trabajos **reales** del equipo, sin datos personales, para medir también con archivos que no fueron escritos pensando en Archy.
