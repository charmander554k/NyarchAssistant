# Archy — Agente organizador de archivos para estudiantes de TIID

> Contexto del proyecto para Claude Code. **Fase actual: planeación.** Todavía NO se escribe código del agente.
> Por ahora, ayuda a entender, revisar y preparar (leer documentación, resolver dudas, revisar el plan, preparar el entorno) y pregunta antes de crear archivos de código.

## Qué es

Proyecto escolar de **Fundamentos de Inteligencia Artificial**, Ingeniería en Tecnologías de la Información e Innovación Digital (TIID), Universidad Politécnica de Tlaxcala (UPTLAX).

- **Nombre:** Archy
- **Eslogan:** «Tu archivista de confianza, 100 % local.»
- **Equipo (5):** Diego Anuar Ruiz Mendoza, Braulio Arturo Rosete Perez, Damaris Abril Cabrera Pluma, Blanca Azucena Onofre Tlachi, Roberto Calzada De la Rosa.
- **Entrega final:** miércoles 2 de diciembre de 2026.
- **Presupuesto:** $0. Solo herramientas open source y gratuitas.

## Problema

Un estudiante tiene en una sola carpeta `Trabajos` los archivos de tres materias parecidas (**Seguridad Informática**, **Minería de Texto** y **Fundamentos de IA**), revueltos y con nombres poco claros (ej. `vdksahdas.py`). Encontrar el trabajo de cada materia se vuelve difícil.

## Solución

Una **extensión en Python para [NyarchAssistant](https://github.com/NyarchLinux/NyarchAssistant)**, un asistente de escritorio open source para Linux (fork de [Newelle](https://github.com/qwersyk/Newelle), distribuido como Flatpak). En Windows se usa dentro de **WSL2** (ver "Soporte en Windows"). El estudiante escribe en el chat ("organiza mi carpeta Trabajos") y la extensión le da al asistente herramientas propias para:

1. escanear la carpeta,
2. leer el contenido de cada archivo,
3. razonar a qué materia pertenece y qué tipo de archivo es,
4. proponer un plan de movimientos y renombres,
5. pedir confirmación,
6. ejecutar solo lo aprobado,
7. registrar todo y permitir deshacer.

Ciclo del agente: **Percibir → Razonar → Planear → Confirmar → Actuar → Registrar.**

## Decisiones ya tomadas

| Tema | Decisión |
|---|---|
| Base | NyarchAssistant (extensión = clase que hereda de `NewelleExtension` y registra `Tool`s) |
| Modelo | **Qwen 2.5 3B** (`qwen2.5:3b`) vía **Ollama**, local. `qwen2.5:1.5b` para PCs lentas. Solo se usa cuando hace falta. |
| Sistema operativo | **Linux** (Flatpak) y **Windows vía WSL2 + WSLg** (el mismo Flatpak corre dentro de Ubuntu en WSL). No se hace port nativo a Windows. Si una PC no permite WSL (sin virtualización), se usa VM o USB. |
| Nombres de archivo | **PascalCase**, sin acentos ni ñ, sin espacios ni símbolos, máx. 50 caracteres, extensión en minúsculas (ej. `AlgoritmoBolsaDePalabras.py`). Solo se renombra si el nombre actual no es descriptivo. |
| Estructura de carpetas | **Materia → Tipo**. **No** se organiza por parcial. |
| Tipos | Código, Documentos, Datos, Presentaciones, Otros |
| Carpeta de dudas | `_Por revisar` (el doc a veces dice "Por revisar"; falta unificar) |
| Licencia | Probablemente GPL-3.0 para ser compatible con NyarchAssistant (pendiente confirmar en su `COPYING`) |

Estructura resultante:

```
Trabajos/
├── Seguridad Informática/  (Codigo/ Documentos/ Datos/ Presentaciones/ Otros/)
├── Minería de Texto/
├── Fundamentos de IA/
└── _Por revisar/
```

## Cómo razona "qué es qué" (clasificador híbrido en cascada)

1. **Reglas y metadatos:** extensión → tipo; palabras clave en nombre/ruta (ej. `nltk`, `tfidf`, `corpus` → Minería de Texto; `cripto`, `firewall`, `nmap` → Seguridad; `perceptron`, `agente`, `heuristica` → Fundamentos IA).
2. **Contenido:** primeros ~2,000 caracteres. En código: imports, funciones y comentarios. En CSV: nombres de columnas.
3. **Similitud semántica:** embeddings locales con `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers) contra la descripción de cada materia.
4. **Qwen solo si hay duda:** confianza entre 0.45 y 0.70 o empate → Qwen responde en JSON `{materia, tipo, confianza, nombre_sugerido, motivo}`. También sugiere nombres.
5. **Decisión:** ≥ 0.70 se propone mover; 0.45–0.70 se propone con advertencia; < 0.45 → `_Por revisar`. Cada decisión guarda su **motivo**.

Qwen también conversa con el usuario y decide qué herramienta llamar, pero **la clasificación la hace la extensión**, no el modelo.

## Arquitectura planeada (módulos)

| Módulo | Responsabilidad |
|---|---|
| `organizador.py` | La extensión. Registra herramientas: `escanear_carpeta`, `proponer_plan`, `aplicar_plan`, `deshacer`, `historial`. Agrega el prompt del sistema. |
| `nucleo/guardian.py` | Seguridad: toda ruta debe quedar dentro de la carpeta autorizada y fuera de la lista negra. Todo pasa por aquí. |
| `nucleo/escaner.py` | Lista archivos, extensión, tamaño, fechas, hash. |
| `nucleo/extractor.py` | Texto de .py, .ipynb, .txt, .md, .docx, .pdf, .pptx, .csv, .xlsx. |
| `nucleo/clasificador.py` | Materia, tipo, confianza y motivo. |
| `nucleo/nombrador.py` | Genera y valida nombres PascalCase. |
| `nucleo/planificador.py` | Tabla de acciones propuestas; detecta conflictos y duplicados. |
| `nucleo/ejecutor.py` | Mueve y renombra solo lo aprobado (`shutil.move`). |
| `nucleo/bitacora.py` | Log en SQLite y deshacer. |

La lógica vive en `nucleo/` para poder probarla con `pytest` sin NyarchAssistant. Debe ser independiente del sistema operativo: usar `pathlib`, no escribir rutas fijas en el código (todo sale de `config.yaml`) y que las pruebas pasen tanto en Linux como en Windows. Las extensiones se instalan como un solo `.py`; si hace falta, `empaquetar.py` une todo.

Configuración en `config.yaml`: carpeta raíz, modo (`simulacion` por defecto), `permitir_renombrar: preguntar`, `formato_nombres: PascalCase`, `organizar_por_parcial: false`, extensiones permitidas, tamaño máximo 50 MB, modelo, umbrales 0.70/0.45 y las 3 materias con descripción y palabras clave.

## Soporte en Windows (WSL2)

NyarchAssistant no corre nativo en Windows: depende de WebKitGTK 6.0 (se carga al arrancar, `src/main.py`), VTE (terminal), Flatpak y X11/Wayland, que no existen en Windows. Un port nativo (MSYS2) implicaría modificar ~10 archivos del asistente y no cabe en 4 semanas. Por eso en Windows se usa **WSL2 + WSLg**, sin tocar NyarchAssistant:

1. Requisitos: Windows 11, o Windows 10 21H2+ con WSL de la Microsoft Store; virtualización activada en BIOS.
2. `wsl --install` (instala Ubuntu) → instalar Flatpak → instalar el `.flatpak` de NyarchAssistant. La app abre como una ventana normal de Windows.
3. **Modo gráfico por software (obligatorio en WSL).** Dentro de WSL la app no tiene permiso de usar la GPU (`/dev/dri/renderD128: Permission denied`) y aborta al arrancar (código 134: aparece el logo y se cierra). Se arregla una sola vez, dentro de Ubuntu:
   ```bash
   flatpak override --user --env=GSK_RENDERER=cairo --env=WEBKIT_DISABLE_DMABUF_RENDERER=1 --env=WEBKIT_DISABLE_COMPOSITING_MODE=1 --env=LIBGL_ALWAYS_SOFTWARE=1 moe.nyarchlinux.assistant
   ```
   Después se abre normal con `flatpak run moe.nyarchlinux.assistant`. Para un chat el modo software es suficiente.
4. Ollama puede quedarse instalado en Windows o instalarse dentro de WSL. Si está en Windows, Ubuntu no lo ve en `localhost` hasta activar la red "espejo" de WSL (en PowerShell, luego `wsl --shutdown`):
   ```powershell
   "[wsl2]`nnetworkingMode=mirrored" | Out-File -Encoding ascii "$env:USERPROFILE\.wslconfig"
   ```
   En NyarchAssistant: proveedor Ollama, endpoint `http://localhost:11434`, modelo `qwen2.5:3b` (o `qwen2.5:1.5b`), igual que en Linux.
5. Desactivar el avatar animado (Live2D) desde la configuración: en modo software genera errores y consume CPU, y además lo piden las reglas éticas.
6. La carpeta `Trabajos` de Windows se ve como `/mnt/c/Users/<usuario>/Documents/Trabajos`. El permiso Flatpak y el `guardian` apuntan a esa ruta (ver lista negra abajo).
7. Leer archivos en `/mnt/c` es más lento que en Linux, pero para el dataset (60–90 archivos) no afecta.

Consejos: en la ventana de Ubuntu, pegar es con **clic derecho** (Ctrl+V escribe `^V`); en Terminal de Windows es Ctrl+Shift+V. Trabajar desde `~` (carpeta de Linux), no desde `/mnt/c/WINDOWS/system32`.

Estado (6 nov 2026, PC de Roberto, Windows 11): WSL2 + Ubuntu + Flatpak + NyarchAssistant 1.6.0 instalados; la app **abre y se mantiene abierta** con el modo software. Falta probar: conexión con Ollama vía red espejo, permiso `--filesystem` a `/mnt/c/.../Trabajos` y selector de archivos.

## Reglas éticas y de seguridad (obligatorias, no negociables)

Vienen del documento de ética del equipo. Cualquier propuesta debe respetarlas:

- **Nunca borra archivos.** No debe existir una función de borrado.
- **No sobrescribe:** si el destino existe, agrega sufijo `_2`.
- **Acceso mínimo:** solo la carpeta `Trabajos` configurada. Doble barrera: permiso Flatpak solo a esa carpeta (`flatpak override --user --filesystem=~/Documentos/Trabajos moe.nyarchlinux.assistant`, **no** `--filesystem=home`) + el `guardian`. En WSL el permiso apunta a la carpeta de Windows, ej. `--filesystem=/mnt/c/Users/<usuario>/Documents/Trabajos`, **nunca** a `/mnt/c` completo.
- **Lista negra siempre bloqueada:** `/`, `/etc`, `/usr`, `/bin`, `/boot`, `/root`, `/var`, `/proc`, `/sys`, `~/.ssh`, `~/.config`, `~/.var`, carpetas ocultas. En WSL además: `/mnt` y la raíz de cada unidad (`/mnt/c`, `/mnt/d`…) como ruta exacta (igual que `/`, porque `Trabajos` vive debajo), y con todo su contenido `/mnt/c/Windows`, `/mnt/c/Program Files`, `/mnt/c/Program Files (x86)`, `/mnt/c/ProgramData`, `/mnt/c/Users/<usuario>/AppData`. No sigue enlaces simbólicos ni accesos directos (`.lnk`).
- **Control humano:** modo simulación por defecto, el plan se muestra antes de actuar, aprobación por archivo, edición del plan y comando deshacer.
- **Transparencia:** cada decisión muestra confianza y motivo; el agente se presenta como "agente automatizado, no una persona" (el avatar animado de NyarchAssistant se desactiva).
- **Privacidad:** 100 % local. Sin nube, sin búsqueda web, sin telemetría, sin memoria a largo plazo. El log guarda rutas y metadatos, nunca el contenido.
- **NyarchAssistant con perfil "Organizador TIID":** ejecución de comandos de terminal desactivada, solo proveedor Ollama, Smart Prompts desactivado.
- **Imparcialidad:** criterios solo por materia y tipo; nunca modifica el contenido de los archivos.

## Normas ISO de referencia (alineación, no certificación)

ISO/IEC 42001:2023 (gestión de IA), ISO/IEC 23894:2023 (riesgos de IA), ISO/IEC 22989:2022 (terminología de IA), ISO/IEC 27001:2022 (seguridad de la información), ISO/IEC 27701 (privacidad), ISO/IEC 25010:2023 (calidad de software), ISO/IEC/IEEE 29119 (pruebas).

## Cronograma (5 nov – 2 dic 2026)

| Fecha | Actividad |
|---|---|
| Jue 5 nov | Planeación, documentación (plan, normas ISO, cronograma) y diseño de identidad (nombre y eslogan) ✅ |
| Vie 6 nov | Instalar NyarchAssistant + Ollama + qwen2.5:3b en ≥ 2 equipos Linux y probarlo en ≥ 1 equipo Windows con WSL2; leer el wiki de extensiones y hacer una extensión "hola mundo"; crear repo y `config.yaml` |
| 9–13 nov | `guardian` + pruebas de seguridad; permiso Flatpak; `escaner` + `extractor`; dataset de prueba etiquetado (60–90 archivos) |
| Lun 16 nov | Feriado |
| 17–20 nov | Clasificador (reglas + embeddings) y medición; Qwen para dudosos y `nombrador` PascalCase |
| 23–27 nov | Herramientas de la extensión, bitácora, prompt del sistema, perfil. **Vie 27: congelar funciones.** |
| 30 nov – 1 dic | Pruebas completas y con 3–5 compañeros; README, manual, video y presentación |
| Mié 2 dic | Entrega final |

## Metas de evaluación

- ≥ 85 % de exactitud en materia, 100 % de nombres PascalCase válidos, 0 movimientos fuera de la carpeta.
- Pruebas de seguridad: intentar leer `/etc`, `~/.ssh`, `/mnt/c/Windows`, `/mnt/c/Users/<usuario>/AppData`, rutas con `..`, symlinks, accesos directos `.lnk`, nombres repetidos, archivos abiertos, pedirle un comando de terminal. Todo debe bloquearse y quedar en el log.
- Prueba de deshacer: hashes de la carpeta antes y después deben ser idénticos.

## Pendientes abiertos

- Asignar los 5 roles: Integración NyarchAssistant · Seguridad y ética · Percepción y datos · IA · Ejecución y documentación.
- Confirmar licencia de NyarchAssistant (`COPYING`).
- Confirmar quién tiene Linux y quién usará Windows con WSL2 (revisar que su PC tenga virtualización activada); VM o USB solo si WSL no es posible.
- Terminar prueba en WSL2 (la ventana ya abre con modo software): que se conecte a Ollama con la red espejo y que el permiso `--filesystem` a `/mnt/c/.../Trabajos` funcione.
- Averiguar qué descarga NyarchAssistant de HuggingFace al arrancar (probablemente un modelo de embeddings o voz activado por defecto) y desactivarlo en el perfil "Organizador TIID" si choca con la regla de 100 % local.
- Unificar `_Por revisar` vs "Por revisar".
- Logo y paleta de colores de Archy (en proceso).
- Verificar en el wiki de Newelle el formato real de extensiones y herramientas: [Developing extensions](https://github.com/qwersyk/Newelle/wiki/Developing-extensions), [Creating Tools](https://github.com/qwersyk/Newelle/wiki/Creating-Tools).

## Cómo ayudar en esta fase

- Responde en español.
- Antes de proponer código, explica el enfoque y espera aprobación.
- Al revisar ideas, verifica que cumplan las reglas éticas de arriba.
- Prioriza soluciones simples que un equipo estudiantil pueda terminar en 4 semanas.
