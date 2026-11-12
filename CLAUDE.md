# Archy — Agente organizador de archivos para estudiantes de TIID

> Contexto del proyecto para Claude Code. **Fase actual: desarrollo** (desde el 10 nov). Planeación y entorno listos; ahora se construye `archy/nucleo/` módulo por módulo, cada uno con sus pruebas `pytest`.
> Antes de escribir un módulo nuevo, explica el enfoque y espera aprobación. Todo cambio debe respetar las reglas éticas.

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
| Carpeta de dudas | `_Por revisar` (unificado el 10 nov; así está en `config.yaml` → `carpeta_dudas`) |
| Licencia | **GPL-3.0**, compatible con NyarchAssistant (confirmado el 10 nov: su `COPYING` es GPL v3 y su appdata dice `GPL-3.0-or-later`) |

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
| `organizador.py` | La extensión. Ya tiene el panel explorador y el tema (11 nov). Falta registrar las herramientas: `escanear_carpeta`, `proponer_plan`, `aplicar_plan`, `deshacer`, `historial`, y agregar el prompt del sistema. |
| `nucleo/guardian.py` | Seguridad: toda ruta debe quedar dentro de la carpeta autorizada y fuera de la lista negra. Todo pasa por aquí. |
| `nucleo/escaner.py` | Lista archivos, extensión, tamaño, fechas, hash. |
| `nucleo/extractor.py` | Texto de .py, .ipynb, .txt, .md, .docx, .pdf, .pptx, .csv, .xlsx. |
| `nucleo/clasificador.py` | Materia, tipo, confianza y motivo. |
| `nucleo/nombrador.py` | Genera y valida nombres PascalCase. |
| `nucleo/planificador.py` | Tabla de acciones propuestas; detecta conflictos y duplicados. |
| `nucleo/ejecutor.py` | Mueve y renombra solo lo aprobado (`shutil.move`). |
| `nucleo/bitacora.py` | Log en SQLite y deshacer. |

La lógica vive en `nucleo/` para poder probarla con `pytest` sin NyarchAssistant. Debe ser independiente del sistema operativo: usar `pathlib`, no escribir rutas fijas en el código (todo sale de `config.yaml`) y que las pruebas pasen tanto en Linux como en Windows. Las extensiones se instalan como un solo `.py`; si hace falta, `empaquetar.py` une todo.

**Estado de los módulos (12 nov):** `config.yaml` ✅ · `nucleo/guardian.py` ✅ · `nucleo/configuracion.py` ✅ · `nucleo/escaner.py` ✅ · `nucleo/extractor.py` ✅ — en total 146 pruebas pasan en WSL y 145 en Windows (las que se saltan son exclusivas del otro sistema; en Windows las de symlinks se saltan si no hay permisos de administrador o modo desarrollador). Escáner y extractor también se probaron dentro del sandbox de NyarchAssistant (Python 3.13, pypdf 5.9) sobre una carpeta `Trabajos` real. Pendientes: `clasificador`, `nombrador`, `planificador`, `ejecutor`, `bitacora`.

**Extractor (`nucleo/extractor.py`):** `extraer(guardian, config, ruta)` devuelve una `Extraccion` con `texto` (como máximo `caracteres_a_leer`, 2,000), `metodo`, `truncado` y `aviso`. **Nunca lanza errores**: un archivo dañado da texto vacío y un aviso. Formatos: texto plano (UTF-8 y, si falla, cp1252/Latin-1 para acentos de Windows); código (pone **primero** imports, definiciones y comentarios); `.ipynb` (celdas Markdown + código); `.csv`/`.tsv` (`Columnas: …` y hasta 5 filas, detecta `,` `;` tab `|`); `.docx`, `.pptx`, `.xlsx` y OpenDocument leídos como ZIP con XML **sin librerías extra**; `.pdf` con `pypdf` (ya viene en el Flatpak; máximo 5 páginas). Otras extensiones → `no_soportado`. Seguridad: toda ruta pasa por el guardián, solo lectura, máximo 256 KB de texto y 4 MB descomprimidos por parte de un ZIP (protege contra bombas ZIP), detecta binarios disfrazados. El texto nunca se guarda en la bitácora.

**Configuración (`nucleo/configuracion.py`):** `cargar_config(ruta)` devuelve un `Config` validado; si hay errores lanza `ConfigInvalida` con **todos** los problemas juntos (claves desconocidas o faltantes, umbrales fuera de `0 < bajo < alto <= 1`, extensiones repetidas o sin punto, materias repetidas, etc.). `config.tipo_de(".py")` → `"Codigo"`; extensiones no listadas → `"Otros"`. PyYAML ya viene en el Flatpak.

**Escáner (`nucleo/escaner.py`):** `escanear(guardian, config)` devuelve `archivos` (ruta relativa, extensión, tipo, tamaño, fecha, **SHA-256**, y `ubicacion`: `suelto` / `organizado` (ya en `Materia/Tipo/`) / `por_revisar`) y `omitidos` con motivo (ocultos, enlaces, `.lnk`, temporales de Office `~$`, más de 50 MB, archivos que no se pueden leer). Solo lee bytes para el hash, nunca el texto. Toda ruta pasa por `guardian.revisar()`. No sigue enlaces ni entra a carpetas ocultas. Máximo 2,000 archivos por escaneo. Orden alfabético estable. Extensiones no listadas se incluyen como `Otros` (se mueven, pero el extractor no las lee).

**Cómo correr las pruebas:**
- Windows (una sola vez: `python -m venv archy\.venv` y `archy\.venv\Scripts\python -m pip install pytest pyyaml pypdf`): desde `archy/`, `.venv\Scripts\python -m pytest`.
- Linux/WSL: desde `archy/`, `python3 -m pytest` (en Ubuntu sin pytest se puede usar el del entorno de Windows: `PYTHONPATH=.venv/Lib/site-packages python3 -m pytest -p no:cacheprovider`).
- En Windows las pruebas usan `archy/tests/_tmp_pruebas/` porque la carpeta temporal normal está dentro de AppData, que el guardián bloquea a propósito.

**Guardián (`nucleo/guardian.py`):** `Guardian(carpeta_raiz, lista_negra_extra, home)`. `validar(ruta)` devuelve la ruta segura o lanza `AccesoDenegado` (con `motivo` en español para la bitácora); `revisar(ruta)` hace lo mismo pero devuelve una `Decision` y nunca lanza (usar esta en las herramientas, porque `create_io_tool` no atrapa errores). Al crearse rechaza una carpeta raíz que no exista, que sea enlace, de sistema o la carpeta personal completa. La lista negra base está en el código; `config.yaml` solo puede agregar rutas. Además de la lista de las reglas éticas bloquea `/sbin`, `/dev`, `/lib`, `/lib64`, `/run`, `/home` exacto, `~/.gnupg`, `~/.local`, rutas de red de Windows y rutas `C:\...` escritas dentro de WSL.

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
   En NyarchAssistant (Configuración → Language Model), igual que en Linux:
   - **Ojo:** por defecto viene seleccionado **"Nyarch Demo API"**, una API en la nube (`llm.nyarchlinux.moe`) limitada a ~10 peticiones por día. Si no se cambia, los mensajes salen a internet (rompe la regla de 100 % local) y al rato aparece `Error code: 429 rate_limit_exceeded`.
   - Elegir **"Ollama Instance"** (no "Ollama Cloud" ni "Local Model"). Si sale en gris, primero clic en la flecha azul ↓ para instalar la librería `ollama`.
   - En sus opciones (⌄): endpoint `http://localhost:11434`; **Ollama Model**: botón ↻ y elegir `qwen2.5:3b` (o `qwen2.5:1.5b`), porque por defecto trae `qwen3.5:9b`, que no está descargado; **Enable Thinking** desactivado (Qwen 2.5 no lo soporta); **Native Tool Calling** activado; **Automatically Serve** apagado.
   - Comprobar: el encabezado del chat dice "Ollama Instance - qwen2.5:3b" y, mientras responde, `ollama ps` (en PowerShell) muestra `qwen2.5:3b`.
5. No usar el avatar animado (Live2D): en modo software genera errores y consume CPU, y además lo piden las reglas éticas. `archy/instalar.sh` crea el perfil "Archy", que usa el panel explorador en su lugar (ver "Interfaz de Archy").
6. La carpeta `Trabajos` de Windows se ve como `/mnt/c/Users/<usuario>/Documents/Trabajos`. El permiso Flatpak y el `guardian` apuntan a esa ruta (ver lista negra abajo).
7. Leer archivos en `/mnt/c` es más lento que en Linux, pero para el dataset (60–90 archivos) no afecta.

Consejos: en la ventana de Ubuntu, pegar es con **clic derecho** (Ctrl+V escribe `^V`); en Terminal de Windows es Ctrl+Shift+V. Trabajar desde `~` (carpeta de Linux), no desde `/mnt/c/WINDOWS/system32`.

Estado (6 nov 2026, PC de Roberto, Windows 11): WSL2 + Ubuntu + Flatpak + NyarchAssistant 1.6.0 **funcionando**: la app abre con modo software, se conecta al Ollama de Windows por la red espejo y `qwen2.5:3b` local llama correctamente a la herramienta `saludar` de la extensión "hola mundo" (confirmado con `ollama ps`). Nota: la primera prueba de la extensión corrió por error en "Nyarch Demo API" (nube), porque no se había cambiado el proveedor; la prueba válida con Qwen local es la segunda. Qwen corre en CPU (lento, pero funciona) y su texto final a veces sale confuso (mezcla "eres"/"soy", agrega una "Task List" innecesaria), lo que confirma que la clasificación debe hacerla la extensión y no el modelo. El 11 nov se aplicó y verificó el permiso restringido a `/mnt/c/Users/rober/Documents/Trabajos` (ver "Acceso mínimo"). Falta probar el selector de archivos.

## Servidor Ollama remoto (opcional, solo para desarrollo)

Si una laptop es lenta (CPU), puede usar el Ollama de otra PC del equipo que tenga GPU, aunque estén en redes distintas (ej. laptop en la universidad y PC en casa), usando **Tailscale** (VPN personal gratuita, cifrada).

Medido el 6 nov con `qwen2.5:3b`: PC con GPU vía Tailscale ≈ **110 tokens/s** (respuesta de ~100 palabras en ~1.3 s) contra ≈ 9 tokens/s en la CPU de la laptop (~12–16 s). Unas 12 veces más rápido.

**En la PC con GPU (Windows):**
1. Instalar Tailscale e iniciar sesión; Ollama con `qwen2.5:3b` descargado.
2. `setx OLLAMA_HOST 0.0.0.0:11434` y reiniciar Ollama (Quit en el icono junto al reloj y abrirlo de nuevo). Comprobar con `Get-NetTCPConnection -LocalPort 11434 -State Listen`: debe decir `0.0.0.0` o `::`, no `127.0.0.1`.
3. Firewall (PowerShell como administrador), solo para direcciones de Tailscale:
   ```powershell
   New-NetFirewallRule -DisplayName "Ollama Tailscale" -Direction Inbound -Protocol TCP -LocalPort 11434 -RemoteAddress 100.64.0.0/10 -Action Allow
   ```
4. **Obligatorio:** `setx OLLAMA_CONTEXT_LENGTH 16384` y reiniciar Ollama. Con los 4096 por defecto, el prompt de NyarchAssistant no cabe y el modelo responde vacío (ver pendiente "Contexto de Ollama").
5. Opcional: `setx OLLAMA_KEEP_ALIVE 30m` para que el modelo no se descargue de la GPU a los 5 minutos (la primera respuesta tras descargarse tarda ~1 minuto).
6. Debe quedarse encendida, sin suspenderse y con Ollama abierto.

**En la laptop:**
1. Tailscale con la **misma cuenta**. `"C:\Program Files\Tailscale\tailscale.exe" status` muestra la IP `100.x` de la PC con GPU.
2. Probar desde Ubuntu: `curl http://<IP-100.x>:11434/api/tags` (debe listar los modelos).
3. Con NyarchAssistant **cerrado**: `bash archy/usar_ollama.sh http://<IP-100.x>:11434` (para volver a esta PC: `bash archy/usar_ollama.sh local`). Prueba la conexión y guarda endpoint y modelo en los ajustes activos **y** en los perfiles. No basta con cambiarlo en Configuración: los perfiles guardan su propia copia y, al cambiar de perfil o al activar el perfil "Archy", puede volver el valor viejo (pasó el 12 nov).
4. Si la PC con GPU no aparece en `tailscale status` ("offline"), está apagada, suspendida o con Tailscale cerrado; no hay forma de conectarse hasta que vuelva.
5. Para usar el Ollama de la laptop como respaldo también necesita `OLLAMA_CONTEXT_LENGTH=16384` y estar abierto (icono junto al reloj). Con poca RAM libre (ej. 3 GB de 15 GB en la laptop de Roberto) en CPU será muy lento: mejor `qwen2.5:1.5b` o la PC con GPU.

**Reglas:**
- **Nunca** abrir el puerto 11434 en el router (port forwarding): Ollama no tiene contraseña y quedaría expuesto a internet.
- En redes que bloquean conexión directa (como la de la universidad), Tailscale pasa por un relevo (DERP); funciona igual, con algo más de latencia.
- Solo para **desarrollo con el dataset de prueba**. El contenido de los archivos viaja (cifrado) a otra PC, así que la **demo y el producto final** usan el Ollama de la propia PC del estudiante (`localhost`), como exige la regla de privacidad.
- Tailscale es gratis; su cliente es open source pero su servidor de coordinación no. Alternativa 100 % open source: Headscale (más complicada). Para desarrollo basta Tailscale.

## Interfaz de Archy (11 nov)

Se cambió el diseño **sin recompilar NyarchAssistant**, solo con la extensión `archy/organizador.py`:

- **Panel "Archy" en lugar de Arch-chan:** la extensión registra un "avatar" (`PanelArchy`, clave `archy`) que en el panel lateral muestra un explorador de **solo lectura** de `Trabajos`: logo, nombre, eslogan, la etiqueta "Agente automatizado · no es una persona", la ruta, un resumen y grupos desplegables (Sin organizar, cada materia, `_Por revisar`, otras carpetas y "No visibles" con el motivo de cada archivo omitido). Usa `guardian` + `escaner` en segundo plano y tiene botón de actualizar.
- **Perfil "Archy":** `archy/perfil_archy.py` lo crea como hijo de "Arch-chan" (hereda todo, incluido Ollama) y solo cambia el avatar (`archy`), la foto (el logo) y los prompts ("Show a personality" y "Show expressions" apagados). **"Arch-chan" no se borra**: sigue como perfil y Live2D sigue instalado; se puede volver desde el selector de perfiles. Ojo: los perfiles guardan su propio avatar, por eso cambiar solo Configuración → Avatar no basta (al arrancar, el perfil "Arch-chan" vuelve a poner Live2D).
- **Paleta** (colores exactos de la imagen del equipo; contraste WCAG medido):

  | Color | Hex | Uso | Contraste |
  |---|---|---|---|
  | Azul marino | `#152F67` | Barra superior | 12.8:1 con blanco |
  | Azul petróleo | `#1D6289` | Acento (botones, contador "Sin organizar") | 6.6:1 con blanco |
  | Turquesa | `#239CAC` | Acento en modo oscuro, detalles | 3.3:1 con blanco: no usar para texto chico sobre blanco |
  | Arena | `#D9C97C` | Contador "Por revisar" (texto marino) | 7.7:1 con marino |
  | Lima | `#D0DB93` | Contador de materias y etiqueta "Agente automatizado" (texto marino) | 8.7:1 con marino |

  El tema se aplica a toda la app con CSS desde la extensión y se apaga en Configuración → Extensiones → Archy → "Colores de Archy".
- **Logo:** `archy/assets/logo_original.jpg` (original), `logo.png` (512 px, esquinas redondeadas, para el panel) y `perfil.png` (256 px, foto del perfil). Usa un azul eléctrico (`#0513A8`) que no está en la paleta; combina, pero si se quiere coherencia total habría que ajustar el logo.
- **Limitación:** el icono y el nombre de la app en el menú y la barra de tareas siguen siendo de NyarchAssistant; cambiarlos obliga a recompilar el Flatpak (horas, varios GB, cada compañero instalaría nuestra versión). Se decidió no hacerlo.
- **Instalación en cada PC:** con la app cerrada, `bash archy/instalar.sh <ruta de Trabajos>` (en Linux sin argumento usa `~/Documentos/Trabajos`). Copia la extensión, el núcleo, el logo y `config.yaml` (si ya existe lo conserva y solo actualiza `carpeta_raiz`) a `~/.var/app/moe.nyarchlinux.assistant/data/archy/`, restringe el Flatpak a `Trabajos`, aplica el modo software en WSL y crea/activa el perfil "Archy". `.gitattributes` fuerza saltos de línea LF en los `.sh` para que el script funcione aunque se clone en Windows.
- **Verificado el 11 nov (WSL):** la app abre con el perfil "Archy", no carga Live2D, sin errores en el registro; vista previa del panel en modo claro y oscuro generada dentro del sandbox.

## Cómo son las extensiones (verificado el 6 nov con `archy/hola_archy.py`)

- Un solo `.py` con una clase que hereda de `NewelleExtension`, con `id` y `name` (≤ 50 caracteres). Imports relativos (`from .extensions import NewelleExtension`, `from .tools import create_io_tool`), porque la app carga el archivo dentro de su propio paquete.
- Herramientas en `get_tools()`. `create_io_tool(nombre, descripcion, funcion, title=..., tools_group=...)` genera el esquema a partir de los tipos de los parámetros (`str`, `int`, `bool`, `float`, `list`, `dict`).
- **`create_io_tool` no atrapa errores** (`src/tools.py`): si la función lanza una excepción, el chat se queda esperando. Toda herramienta de Archy debe usar `try/except` y devolver siempre un texto.
- Prompts del sistema en `get_additional_prompts()` como **diccionarios** (`key`, `setting_name`, `title`, `description`, `editable`, `show_in_settings`, `default`, `text`). El `PromptDescription` del wiki de Newelle **no existe** en NyarchAssistant.
- Dependencias pip: `get_extra_requirements()` + `install()`; importar las librerías opcionales dentro de las funciones, no arriba del archivo.
- Instalación: copiar el `.py` a `~/.var/app/moe.nyarchlinux.assistant/config/extensions/` y reiniciar la app (en WSL es más confiable que el selector de archivos).
- El código de Archy vive en la carpeta `archy/` de este repo (fork del equipo de NyarchAssistant), separado de `src/`.

## Reglas éticas y de seguridad (obligatorias, no negociables)

Vienen del documento de ética del equipo. Cualquier propuesta debe respetarlas:

- **Nunca borra archivos.** No debe existir una función de borrado.
- **No sobrescribe:** si el destino existe, agrega sufijo `_2`.
- **Acceso mínimo:** solo la carpeta `Trabajos` configurada. Doble barrera: permiso Flatpak solo a esa carpeta + el `guardian`. **Ojo:** el manifiesto de NyarchAssistant trae `--filesystem=home` (toda la carpeta personal) y `--talk-name=org.freedesktop.Flatpak` (permite `flatpak-spawn --host`, o sea, ejecutar comandos fuera del sandbox y saltarse cualquier restricción). Hay que quitar ambos con un override:
  - Linux: `flatpak override --user --nofilesystem=home --no-talk-name=org.freedesktop.Flatpak --filesystem=~/Documentos/Trabajos moe.nyarchlinux.assistant`
  - WSL: igual, pero `--filesystem=/mnt/c/Users/<usuario>/Documents/Trabajos`, **nunca** `/mnt/c` completo.
  - Comprobar: `flatpak override --user --show moe.nyarchlinux.assistant` debe mostrar `filesystems=!home;<ruta de Trabajos>;` y `org.freedesktop.Flatpak=none`.
  - Verificado el 11 nov en WSL: dentro del sandbox se ve `Trabajos` y la configuración de la app (extensiones), pero no `~/Documentos`, `~/.ssh` ni el resto de `C:\`, y `flatpak-spawn --host` falla. La app sigue abriendo; los mensajes `Portal call failed … --host only works…` en la terminal son la app intentando ejecutar comandos fuera del sandbox y siendo bloqueada (esperado). Se pierde la ejecución de comandos de terminal (que las reglas ya piden desactivar) y la aceleración GPU de llama.cpp (no se usa).
- **Lista negra siempre bloqueada:** `/`, `/etc`, `/usr`, `/bin`, `/boot`, `/root`, `/var`, `/proc`, `/sys`, `~/.ssh`, `~/.config`, `~/.var`, carpetas ocultas. En WSL además: `/mnt` y la raíz de cada unidad (`/mnt/c`, `/mnt/d`…) como ruta exacta (igual que `/`, porque `Trabajos` vive debajo), y con todo su contenido `/mnt/c/Windows`, `/mnt/c/Program Files`, `/mnt/c/Program Files (x86)`, `/mnt/c/ProgramData`, `/mnt/c/Users/<usuario>/AppData`. No sigue enlaces simbólicos ni accesos directos (`.lnk`).
- **Control humano:** modo simulación por defecto, el plan se muestra antes de actuar, aprobación por archivo, edición del plan y comando deshacer.
- **Transparencia:** cada decisión muestra confianza y motivo; el agente se presenta como "agente automatizado, no una persona" (el avatar animado de NyarchAssistant se desactiva).
- **Privacidad:** 100 % local. Sin nube, sin búsqueda web, sin telemetría, sin memoria a largo plazo. El log guarda rutas y metadatos, nunca el contenido. Excepción solo durante el desarrollo: usar el Ollama de otra PC del equipo por Tailscale con el dataset de prueba (ver "Servidor Ollama remoto"); nunca en la demo ni con archivos reales de estudiantes.
- **NyarchAssistant con perfil "Organizador TIID":** ejecución de comandos de terminal desactivada, solo proveedor **"Ollama Instance"** (nunca "Nyarch Demo API", que viene por defecto y es nube), Smart Prompts desactivado. Sin personaje: en Configuración → Prompts desactivar **"Show a personality"** (tono de personaje "Arch-chan") y **"Show expressions"** (etiquetas como "(Happy)", "(Wink)" para animar el avatar), y cambiar el nombre del asistente de "Arch-chan" a "Archy".
- **Imparcialidad:** criterios solo por materia y tipo; nunca modifica el contenido de los archivos.

## Normas ISO de referencia (alineación, no certificación)

ISO/IEC 42001:2023 (gestión de IA), ISO/IEC 23894:2023 (riesgos de IA), ISO/IEC 22989:2022 (terminología de IA), ISO/IEC 27001:2022 (seguridad de la información), ISO/IEC 27701 (privacidad), ISO/IEC 25010:2023 (calidad de software), ISO/IEC/IEEE 29119 (pruebas).

## Cronograma (5 nov – 2 dic 2026)

| Fecha | Actividad |
|---|---|
| Jue 5 nov | Planeación, documentación (plan, normas ISO, cronograma) y diseño de identidad (nombre y eslogan) ✅ |
| Vie 6 nov | Instalar NyarchAssistant + Ollama + qwen2.5:3b en ≥ 2 equipos Linux y probarlo en ≥ 1 equipo Windows con WSL2; leer el wiki de extensiones y hacer una extensión "hola mundo"; crear repo y `config.yaml` |
| 9–13 nov | `guardian` + pruebas de seguridad ✅ (10 nov); permiso Flatpak ✅ (11 nov); `escaner` ✅ (11 nov); nueva interfaz de Archy ✅ (11 nov, no planeada); `extractor` ✅ (12 nov); dataset de prueba etiquetado (60–90 archivos) |
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
- Confirmar quién tiene Linux y quién usará Windows con WSL2 (revisar que su PC tenga virtualización activada); VM o USB solo si WSL no es posible.
- ~~Permiso Flatpak a `/mnt/c/.../Trabajos` en WSL2~~ ✅ 11 nov (ver "Acceso mínimo"). Falta probar el selector de archivos de la app con el permiso restringido.
- **Contexto de Ollama (problema confirmado el 6 nov):** Ollama usa 4096 tokens por defecto y NyarchAssistant no le indica otro valor (no manda `num_ctx`). Cada mensaje de NyarchAssistant pesa ~5,700–8,600 tokens (instrucciones + definición de todas sus herramientas + historial, según `data/usage.sqlite3` de la app), así que Ollama recorta el prompt y Qwen devuelve **respuestas vacías** (`out=0` en ese registro). Pasa sobre todo al usar una herramienta (`saludar`), porque la llamada y su resultado agregan más texto; los mensajes cortos sí responden.
  - Arreglo: en la PC que corre Ollama, `setx OLLAMA_CONTEXT_LENGTH 16384` y reiniciar Ollama. Comprobar con `ollama ps` (columna CONTEXT) o `/api/ps` (`context_length`). En GPU cuesta ~0.6 GB más de VRAM; en CPU hace más lentas las respuestas.
  - Pendiente: verificar que con 16384 `saludar` responde, y medir cuánto pesa el prompt.
  - Solución de fondo: en el perfil "Organizador TIID", desactivar las herramientas y prompts de NyarchAssistant que Archy no usa (búsqueda web, memoria, terminal, etc.) para achicar el prompt y que también funcione en laptops con CPU.
- ~~Perfil sin la personalidad "Arch-chan"~~ ✅ 11 nov: el perfil "Archy" (creado por `instalar.sh`) apaga "Show a personality" y "Show expressions" y usa el nombre y logo de Archy. Falta en ese perfil: desactivar la ejecución de comandos de terminal, Smart Prompts y las herramientas que Archy no usa (ver "Contexto de Ollama").
- Averiguar qué descarga NyarchAssistant de HuggingFace al arrancar (probablemente un modelo de embeddings o voz activado por defecto) y desactivarlo en el perfil "Organizador TIID" si choca con la regla de 100 % local. También descarga al arrancar el catálogo de modelos de `ollama.com` (lista pública, no manda datos del usuario).
- ~~Logo y paleta de colores de Archy~~ ✅ 11 nov (ver "Interfaz de Archy").
- ~~Verificar en el wiki de Newelle el formato real de extensiones y herramientas~~ ✅ Hecho el 6 nov (ver "Cómo son las extensiones"). Referencia: [Developing extensions](https://github.com/qwersyk/Newelle/wiki/Developing-extensions), [Creating Tools](https://github.com/qwersyk/Newelle/wiki/Creating-Tools).

## Cómo ayudar en esta fase

- Responde en español.
- Antes de proponer código, explica el enfoque y espera aprobación.
- Al revisar ideas, verifica que cumplan las reglas éticas de arriba.
- Prioriza soluciones simples que un equipo estudiantil pueda terminar en 4 semanas.
