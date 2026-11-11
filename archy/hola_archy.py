"""Archy - extensión "hola mundo" para NyarchAssistant.

Sirve solo para comprobar que una extensión se carga, que registra una
herramienta que el modelo puede llamar y que agrega un prompt del sistema.

Instalación (dentro de Ubuntu/WSL o en Linux):
    cp archy/hola_archy.py ~/.var/app/moe.nyarchlinux.assistant/config/extensions/
Después reiniciar NyarchAssistant y revisar Configuración -> Extensiones.
"""

from gettext import gettext as _

# NyarchAssistant carga este archivo como parte de su propio paquete,
# por eso los imports son relativos.
from .extensions import NewelleExtension
from .tools import create_io_tool


class ArchyHolaExtension(NewelleExtension):
    id = "archy-hola"
    name = "Archy (hola mundo)"

    def saludar(self, nombre: str) -> str:
        # create_io_tool no atrapa errores: si esta función fallara, el chat
        # se quedaría esperando. Por eso toda herramienta de Archy devuelve
        # un texto también cuando algo sale mal.
        try:
            nombre = str(nombre).strip() or "estudiante"
            return (
                f"Hola {nombre}, soy Archy, un agente automatizado (no una persona). "
                "Por ahora solo sé saludar; pronto podré organizar tu carpeta Trabajos."
            )
        except Exception as error:
            return f"Archy no pudo saludar: {error}"

    def get_tools(self) -> list:
        return [
            create_io_tool(
                "saludar",
                "Saluda al usuario por su nombre y presenta a Archy. "
                "Úsala cuando el usuario pida que Archy lo salude.",
                self.saludar,
                title=_("Saludar (Archy)"),
                tools_group=_("Archy"),
            )
        ]

    def get_additional_prompts(self) -> list:
        # En NyarchAssistant los prompts son diccionarios (no PromptDescription
        # como dice el wiki de Newelle).
        return [
            {
                "key": "archy-hola",
                "setting_name": "archy-hola",
                "title": _("Archy: presentación"),
                "description": _("Indica al modelo que se presente como Archy, un agente automatizado"),
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": (
                    "Eres Archy, un agente automatizado (no una persona) que ayuda a "
                    "estudiantes de TIID a organizar sus archivos. Responde en español. "
                    "Si el usuario pide un saludo, usa la herramienta saludar."
                ),
            }
        ]
