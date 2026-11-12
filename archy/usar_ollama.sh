#!/bin/bash
# Cambia el servidor Ollama (y el modelo) que usa NyarchAssistant.
#
# Uso (con la app CERRADA, en Ubuntu/WSL o Linux):
#   bash archy/usar_ollama.sh local                         # Ollama de esta PC
#   bash archy/usar_ollama.sh http://100.92.78.19:11434     # Ollama de otra PC (Tailscale)
#   bash archy/usar_ollama.sh local qwen2.5:1.5b            # otro modelo
#
# Por qué existe: los perfiles de NyarchAssistant guardan su propia copia de
# los ajustes. Si solo se cambia el endpoint en la ventana de Configuración,
# al cambiar de perfil o reiniciar puede volver el valor viejo. Este script lo
# cambia en los ajustes activos y en todos los perfiles que guardan ajustes del
# modelo (el perfil base "Arch-chan", del que hereda "Archy").
set -euo pipefail

APPID=moe.nyarchlinux.assistant
DESTINO="${1:-}"
MODELO="${2:-qwen2.5:3b}"

if [ -z "$DESTINO" ]; then
  sed -n '2,8p' "$0"
  exit 1
fi
[ "$DESTINO" = "local" ] && DESTINO="http://localhost:11434"
case "$DESTINO" in
  http://*|https://*) ;;
  *) echo "ERROR: usa 'local' o una URL como http://100.92.78.19:11434" >&2; exit 1 ;;
esac
DESTINO="${DESTINO%/}"

if flatpak ps --columns=application 2>/dev/null | grep -qx "$APPID"; then
  echo "ERROR: NyarchAssistant está abierto. Ciérralo y vuelve a ejecutar el script." >&2
  exit 1
fi

echo "==> Probando $DESTINO ..."
if MODELOS=$(curl -s -m 8 "$DESTINO/api/tags"); then
  if echo "$MODELOS" | grep -q "\"$MODELO\""; then
    echo "    Responde y tiene $MODELO."
  else
    echo "    AVISO: responde, pero no tiene $MODELO (ejecuta 'ollama pull $MODELO' en esa PC)."
  fi
else
  echo "    AVISO: no responde ahora (¿PC apagada, Tailscale desconectado u Ollama cerrado?)."
  echo "    Se guarda igual; funcionará cuando ese servidor esté disponible."
fi

TMP="$HOME/.var/app/$APPID/cache/usar_ollama.py"
mkdir -p "$(dirname "$TMP")"
cat > "$TMP" <<'PY'
import json, sys
from gi.repository import Gio, GLib

destino, modelo = sys.argv[1], sys.argv[2]
ajustes = Gio.Settings.new("moe.nyarchlinux.assistant")

def actualizar(llm_json: str) -> str:
    llm = json.loads(llm_json or "{}")
    ollama = llm.setdefault("ollama", {})
    ollama["endpoint"] = destino
    ollama["model"] = modelo
    ollama["thinking"] = False
    return json.dumps(llm)

ajustes.set_string("language-model", "ollama")
ajustes.set_string("llm-settings", actualizar(ajustes.get_string("llm-settings")))

perfiles = json.loads(ajustes.get_string("profiles") or "{}")
cambiados = []
for nombre, perfil in perfiles.items():
    datos = perfil.get("settings") if isinstance(perfil, dict) else None
    if isinstance(datos, dict) and "llm-settings" in datos:
        datos["llm-settings"] = actualizar(datos["llm-settings"])
        datos["language-model"] = "ollama"
        cambiados.append(nombre)
ajustes.set_string("profiles", json.dumps(perfiles))
Gio.Settings.sync()
print(f"    Ollama: {destino} · modelo: {modelo} · perfiles actualizados: {', '.join(cambiados) or 'ninguno'}")
PY

echo "==> Guardando la configuración de NyarchAssistant"
flatpak run --command=python3 "$APPID" "$TMP" "$DESTINO" "$MODELO"
rm -f "$TMP"
echo "Listo. Abre la app: flatpak run $APPID"
