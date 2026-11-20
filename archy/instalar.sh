#!/bin/bash
# Instala Archy en NyarchAssistant (Flatpak) y restringe sus permisos.
#
# Uso:
#   Linux:  bash archy/instalar.sh                      (usa ~/Documentos/Trabajos)
#           bash archy/instalar.sh /ruta/a/Trabajos
#   WSL:    bash archy/instalar.sh /mnt/c/Users/<usuario>/Documents/Trabajos
#   Equipo: agregar --desarrollo activa la herramienta medir_clasificador y copia
#           dataset/etiquetas.csv (sin la opción, se desactiva).
#
# Qué hace:
#   1. Crea la carpeta Trabajos si no existe.
#   2. Copia el núcleo, el logo y config.yaml a ~/.var/app/<app>/data/archy/
#      (pone carpeta_raiz; si el config.yaml anterior tenía otros cambios, lo
#      guarda en config.yaml.anterior-<fecha>).
#   3. Copia la extensión (organizador.py) a la carpeta de extensiones.
#   4. Restringe el Flatpak: quita el acceso a toda la carpeta personal y la
#      salida del sandbox, y da acceso solo a Trabajos.
#   5. En WSL, aplica además el modo gráfico por software.
#   6. Crea el perfil "Archy" (hijo de "Arch-chan", que se conserva) y lo activa.
#      Requiere que la app esté cerrada.
set -euo pipefail

APPID=moe.nyarchlinux.assistant
AQUI="$(cd "$(dirname "$0")" && pwd)"
APPDIR="$HOME/.var/app/$APPID"
DATA="$APPDIR/data/archy"
EXT="$APPDIR/config/extensions"

es_wsl() { grep -qi microsoft /proc/version 2>/dev/null; }

if ! flatpak info "$APPID" >/dev/null 2>&1; then
  echo "ERROR: NyarchAssistant ($APPID) no está instalado con Flatpak." >&2
  exit 1
fi

DESARROLLO=false
TRABAJOS=""
for arg in "$@"; do
  case "$arg" in
    --desarrollo) DESARROLLO=true ;;
    *) TRABAJOS="$arg" ;;
  esac
done
if [ -z "$TRABAJOS" ]; then
  if es_wsl; then
    echo "ERROR: en WSL indica la carpeta, ej.:" >&2
    echo "  bash archy/instalar.sh /mnt/c/Users/<usuario>/Documents/Trabajos" >&2
    exit 1
  fi
  TRABAJOS="$HOME/Documentos/Trabajos"
fi
case "$TRABAJOS" in
  /*) ;;
  *) echo "ERROR: la ruta de Trabajos debe ser completa (empezar con /)." >&2; exit 1 ;;
esac
TRABAJOS="${TRABAJOS%/}"

echo "==> Carpeta Trabajos: $TRABAJOS"
mkdir -p "$TRABAJOS"

echo "==> Copiando el núcleo y el logo a $DATA"
mkdir -p "$DATA/assets" "$EXT"
rm -rf "$DATA/nucleo"
cp -r "$AQUI/nucleo" "$DATA/nucleo"
find "$DATA/nucleo" -name "__pycache__" -type d -prune -exec rm -rf {} +
cp "$AQUI/assets/logo.png" "$AQUI/assets/perfil.png" "$DATA/assets/"

# config.yaml: se instala el del repositorio (vocabulario y modelos al día).
# Si el instalado tenía otros cambios además de carpeta_raiz y modo_desarrollo,
# se guarda una copia con fecha (config.yaml.anterior-AAAAMMDD-HHMMSS).
sin_lineas_locales() { tr -d '\r' < "$1" | grep -vE '^(carpeta_raiz|modo_desarrollo):'; }
if [ -f "$DATA/config.yaml" ] && \
   ! diff -q <(sin_lineas_locales "$DATA/config.yaml") <(sin_lineas_locales "$AQUI/config.yaml") >/dev/null; then
  RESPALDO="$DATA/config.yaml.anterior-$(date +%Y%m%d-%H%M%S)"
  cp "$DATA/config.yaml" "$RESPALDO"
  echo "==> El config.yaml instalado era distinto: se guardó en $(basename "$RESPALDO")"
fi
tr -d '\r' < "$AQUI/config.yaml" > "$DATA/config.yaml"
# Actualiza solo las líneas carpeta_raiz y modo_desarrollo.
python3 - "$DATA/config.yaml" "$TRABAJOS" "$DESARROLLO" <<'PY'
import re, sys
ruta, trabajos, desarrollo = sys.argv[1], sys.argv[2], sys.argv[3]
texto = open(ruta, encoding="utf-8").read()
nuevo, n = re.subn(r'^carpeta_raiz:.*$', 'carpeta_raiz: "%s"' % trabajos.replace('"', '\\"'), texto, flags=re.M)
if n != 1:
    sys.exit("ERROR: no se encontró 'carpeta_raiz' en config.yaml")
nuevo, n = re.subn(r'^modo_desarrollo:.*$', 'modo_desarrollo: ' + desarrollo, nuevo, flags=re.M)
if n == 0:
    nuevo = nuevo.rstrip("\n") + "\n\nmodo_desarrollo: " + desarrollo + "\n"
open(ruta, "w", encoding="utf-8").write(nuevo)
PY
if [ "$DESARROLLO" = true ]; then
  echo "==> Modo desarrollo: se activa medir_clasificador y se copian las etiquetas"
  mkdir -p "$DATA/dataset"
  cp "$AQUI/dataset/etiquetas.csv" "$DATA/dataset/etiquetas.csv"
else
  rm -rf "$DATA/dataset"
fi

echo "==> Instalando la extensión en $EXT"
cp "$AQUI/organizador.py" "$EXT/organizador.py"
cp "$AQUI/perfil_archy.py" "$DATA/perfil_archy.py"

echo "==> Restringiendo permisos del Flatpak (solo Trabajos)"
flatpak override --user --nofilesystem=home --no-talk-name=org.freedesktop.Flatpak \
  --filesystem="$TRABAJOS" "$APPID"

if es_wsl; then
  echo "==> WSL detectado: modo gráfico por software"
  flatpak override --user --env=GSK_RENDERER=cairo --env=WEBKIT_DISABLE_DMABUF_RENDERER=1 \
    --env=WEBKIT_DISABLE_COMPOSITING_MODE=1 --env=LIBGL_ALWAYS_SOFTWARE=1 "$APPID"
fi

PERFIL_LISTO=no
if flatpak ps --columns=application 2>/dev/null | grep -qx "$APPID"; then
  echo "==> AVISO: NyarchAssistant está abierto; no se creó el perfil Archy."
  echo "    Ciérralo y vuelve a ejecutar este script."
else
  echo "==> Creando el perfil 'Archy' (Arch-chan se conserva como otro perfil)"
  if flatpak run --command=python3 "$APPID" "$DATA/perfil_archy.py" "$DATA/assets/perfil.png"; then
    PERFIL_LISTO=si
  fi
fi

cat <<EOF

Listo. Siguientes pasos:
  1. Abre NyarchAssistant:  flatpak run $APPID
  2. Perfil activo: "Archy" (logo como foto, panel explorador en lugar del avatar,
     sin personalidad ni expresiones). Arch-chan sigue disponible en el selector
     de perfiles; no se borró nada.
  3. Configuración -> Extensiones -> Archy: "Colores de Archy" (activado por defecto).
EOF
[ "$PERFIL_LISTO" = si ] || echo "  (Falta el perfil: cierra la app y ejecuta de nuevo este script.)"
