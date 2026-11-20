"""Crea o actualiza el perfil "Archy" en NyarchAssistant.

- Es hijo del perfil "Arch-chan": hereda todo (modelo de Ollama, ajustes, etc.)
  y solo cambia el avatar y los prompts.
- Avatar: el panel explorador de Archy (no un personaje).
- Prompts: apaga "Show a personality" y "Show expressions" (regla de transparencia),
  y los prompts de NyarchAssistant que confunden a Qwen (ver PROMPTS_APAGADOS).
- Herramientas: deja solo las de Archy. NyarchAssistant trae ~25 propias
  (terminal, búsqueda web, editar archivos, capturas...); con todas, el prompt
  pesa ~8,000 tokens y Qwen 2.5 3B deja de llamar a ver_archivo (probado el
  20 nov: solo con las de Archy acierta 5 de 5). Además las reglas éticas piden
  apagar la terminal y la búsqueda web.
- Foto: el logo de Archy.
- El perfil "Arch-chan" NO se borra ni se modifica; se puede volver a él
  desde el selector de perfiles.

Se ejecuta DENTRO del Flatpak y con la app cerrada (instalar.sh lo hace):
    flatpak run --command=python3 moe.nyarchlinux.assistant perfil_archy.py <foto.png>
"""

import json
import sys

APPID = "moe.nyarchlinux.assistant"
PERFIL_RAIZ = "Arch-chan"
PERFIL = "Archy"

# Grupos de ajustes que el perfil Archy sobrescribe (igual que en src/constants.py).
GRUPOS = {
    "avatar": ["avatar-on", "hide-avatar-on-startup", "avatar-model", "avatars"],
    "prompts": ["prompts-settings", "user-message-prompts", "custom-extra-prompt",
                "custom-prompts", "prompts-order", "user-custom-prompts"],
    "tools": ["tools-settings", "mcp-servers", "skills-settings", "file-permissions",
              "command-execution-permissions", "path-security-levels", "default-risk-level"],
}

HERRAMIENTAS_ARCHY = ("proponer_plan", "ver_archivo", "deshacer", "historial", "medir_clasificador")

# Herramientas de NyarchAssistant 1.6 (por si no se pueden listar desde la app)
# y la de la extensión de prueba hola_archy.py.
HERRAMIENTAS_CONOCIDAS = (
    "ask_user", "edit", "execute_command", "get_official_package_info", "get_wiki_page", "glob",
    "grep_search", "list_directory", "read_file", "read_image", "run_subagent", "schedule_task",
    "search", "search_arch_wiki", "search_aur", "show_image", "show_video", "sleep",
    "speech_to_text", "switch_mode", "take_screenshot", "text_to_speech", "todo", "website",
    "write_file", "send_message", "saludar", "rag_search_files",
)

# Prompts de NyarchAssistant que se apagan en el perfil Archy (medido el 20 nov
# con el registro de lo que recibe Qwen): "environment" agrega ~900 caracteres
# antes de CADA mensaje del estudiante (datos del sistema y reglas para ejecutar
# comandos) y su pregunta queda al final; "source_attribution" pide citas y
# fuentes; "todo" y "skills" no aplican. "tools" se deja: de ahí salen las
# herramientas que recibe el modelo.
PROMPTS_APAGADOS = ("environment", "source_attribution", "todo", "skills",
                    "personality-prompt", "expression-prompt")


def herramientas_de_la_app() -> set[str]:
    """Nombres de las herramientas de las integraciones de NyarchAssistant instaladas."""
    nombres = set(HERRAMIENTAS_CONOCIDAS)
    try:
        import builtins
        import gettext
        builtins.__dict__.setdefault("_", gettext.gettext)
        sys.path.insert(0, "/app/share/nyarchassistant")
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        gi.require_version("GtkSource", "5")
        from gi.repository import Gio
        Gio.Resource.load("/app/share/nyarchassistant/nyarchassistant.gresource")._register()
        from nyarchassistant.constants import AVAILABLE_INTEGRATIONS
        ajustes = Gio.Settings.new(APPID)
        for clase in AVAILABLE_INTEGRATIONS:
            try:
                nombres.update(t.name for t in clase("", "", ajustes).get_tools())
            except Exception:
                pass
    except Exception as error:
        print(f"AVISO: no se pudieron listar las herramientas de la app ({error}); se usa la lista conocida.")
    return nombres


def solo_herramientas_de_archy(actuales: dict, todas) -> dict:
    """Ajuste "tools-settings" con todo apagado salvo las herramientas de Archy."""
    nuevos = {nombre: dict(valor) for nombre, valor in (actuales or {}).items() if isinstance(valor, dict)}
    for nombre in set(todas) | set(nuevos) | set(HERRAMIENTAS_ARCHY):
        entrada = nuevos.setdefault(nombre, {"custom_prompt": None})
        entrada["enabled"] = nombre in HERRAMIENTAS_ARCHY
    return nuevos


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: perfil_archy.py <ruta de la foto del perfil>", file=sys.stderr)
        return 2
    foto = sys.argv[1]
    todas = herramientas_de_la_app()
    from gi.repository import Gio, GLib

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
    for clave in PROMPTS_APAGADOS:
        prompts[clave] = False
    valores["prompts-settings"] = json.dumps(prompts)
    try:
        herramientas = json.loads(valores.get("tools-settings") or "{}")
    except ValueError:
        herramientas = {}
    valores["tools-settings"] = json.dumps(solo_herramientas_de_archy(herramientas, todas))

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

    apagadas = len(todas - set(HERRAMIENTAS_ARCHY))
    print(f"Perfil '{PERFIL}' listo (hijo de '{PERFIL_RAIZ}'). Perfiles: {', '.join(perfiles)}")
    print(f"Herramientas: solo las de Archy; se apagaron {apagadas} de NyarchAssistant en este perfil.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
