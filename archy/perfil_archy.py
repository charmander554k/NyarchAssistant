"""Crea o actualiza el perfil "Archy" en NyarchAssistant.

- Es hijo del perfil "Arch-chan": hereda todo (modelo de Ollama, ajustes, etc.)
  y solo cambia el avatar y los prompts.
- Avatar: el panel explorador de Archy (no un personaje).
- Prompts: apaga "Show a personality" y "Show expressions" (regla de transparencia).
- Foto: el logo de Archy.
- El perfil "Arch-chan" NO se borra ni se modifica; se puede volver a él
  desde el selector de perfiles.

Se ejecuta DENTRO del Flatpak y con la app cerrada (instalar.sh lo hace):
    flatpak run --command=python3 moe.nyarchlinux.assistant perfil_archy.py <foto.png>
"""

import json
import sys

from gi.repository import Gio, GLib

APPID = "moe.nyarchlinux.assistant"
PERFIL_RAIZ = "Arch-chan"
PERFIL = "Archy"

# Grupos de ajustes que el perfil Archy sobrescribe (igual que en src/constants.py).
GRUPOS = {
    "avatar": ["avatar-on", "hide-avatar-on-startup", "avatar-model", "avatars"],
    "prompts": ["prompts-settings", "user-message-prompts", "custom-extra-prompt",
                "custom-prompts", "prompts-order", "user-custom-prompts"],
}


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: perfil_archy.py <ruta de la foto del perfil>", file=sys.stderr)
        return 2
    foto = sys.argv[1]

    ajustes = Gio.Settings.new(APPID)
    disponibles = set(ajustes.props.settings_schema.list_keys())
    try:
        perfiles = json.loads(ajustes.get_string("profiles") or "{}")
    except ValueError:
        perfiles = {}
    if not isinstance(perfiles, dict) or PERFIL_RAIZ not in perfiles:
        print(f"ERROR: no se encontró el perfil '{PERFIL_RAIZ}'. Abre la app una vez y ciérrala.",
              file=sys.stderr)
        return 1

    claves = [k for grupo in GRUPOS.values() for k in grupo if k in disponibles]
    valores = {k: ajustes.get_value(k).unpack() for k in claves}
    valores["avatar-on"] = True
    valores["hide-avatar-on-startup"] = False
    valores["avatar-model"] = "archy"
    try:
        prompts = json.loads(valores.get("prompts-settings") or "{}")
    except ValueError:
        prompts = {}
    prompts["personality-prompt"] = False
    prompts["expression-prompt"] = False
    valores["prompts-settings"] = json.dumps(prompts)

    registro = perfiles.get(PERFIL) if isinstance(perfiles.get(PERFIL), dict) else {}
    registro["picture"] = foto
    registro["settings"] = {**(registro.get("settings") or {}), **valores}
    registro["settings_groups"] = sorted(set(registro.get("settings_groups") or []) | set(GRUPOS))
    registro["parent"] = PERFIL_RAIZ
    perfiles[PERFIL] = registro
    ajustes.set_string("profiles", json.dumps(perfiles))

    # Deja el perfil Archy activo con sus valores ya aplicados.
    for clave, valor in valores.items():
        tipo = ajustes.get_value(clave).get_type_string()
        ajustes.set_value(clave, GLib.Variant(tipo, valor))
    ajustes.set_string("current-profile", PERFIL)
    Gio.Settings.sync()

    print(f"Perfil '{PERFIL}' listo (hijo de '{PERFIL_RAIZ}'). Perfiles: {', '.join(perfiles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
