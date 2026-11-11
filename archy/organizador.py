"""Archy - extensión principal para NyarchAssistant.

Por ahora aporta:
- el panel "Archy": un explorador de solo lectura de la carpeta Trabajos que
  ocupa el lugar del avatar animado (Arch-chan sigue instalada; solo se elige
  "Archy" en Configuración -> Avatar);
- el tema de colores de Archy (se puede apagar en los ajustes de la extensión).

Las herramientas del agente (escanear_carpeta, proponer_plan, ...) se agregarán
aquí después.

Instalación: ejecutar `archy/instalar.sh`. Copia este archivo a la carpeta de
extensiones y el núcleo, config.yaml y el logo a
~/.var/app/moe.nyarchlinux.assistant/data/archy/.
"""

from __future__ import annotations

import os
import sys
import threading
from gettext import gettext as _

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

# NyarchAssistant carga este archivo dentro de su propio paquete: imports relativos.
from .extensions import NewelleExtension
from .handlers import ExtraSettings
from .handlers.avatar import AvatarHandler

# Carpeta con el núcleo, config.yaml y el logo (la app siempre puede leerla).
ARCHY_DIR = os.path.join(GLib.get_user_data_dir(), "archy")
if ARCHY_DIR not in sys.path:
    sys.path.insert(0, ARCHY_DIR)

LOGO = os.path.join(ARCHY_DIR, "assets", "logo.png")
CONFIG = os.path.join(ARCHY_DIR, "config.yaml")

PALETA = {
    "marino": "#152F67",
    "petroleo": "#1D6289",
    "turquesa": "#239CAC",
    "arena": "#D9C97C",
    "lima": "#D0DB93",
}

ICONOS_TIPO = {
    "Codigo": "text-x-script-symbolic",
    "Documentos": "x-office-document-symbolic",
    "Datos": "x-office-spreadsheet-symbolic",
    "Presentaciones": "x-office-presentation-symbolic",
}
ICONO_OTROS = "text-x-generic-symbolic"

# Las carpetas no llevan acentos (regla de nombres), pero en pantalla sí.
NOMBRE_TIPO = {"Codigo": "Código"}

# Estilos del panel (siempre activos: solo afectan a clases "archy-*").
CSS_PANEL = f"""
.archy-panel {{ padding: 14px; }}
.archy-nombre {{ font-weight: 800; font-size: 1.5em; }}
.archy-agente {{
  border-radius: 999px; padding: 1px 10px; font-size: 0.8em; font-weight: 700;
  color: {PALETA["marino"]}; background-color: {PALETA["lima"]};
}}
.archy-ruta {{
  font-family: monospace; font-size: 0.85em; padding: 6px 10px; border-radius: 8px;
  background-color: alpha({PALETA["petroleo"]}, 0.14);
}}
.archy-pill {{ border-radius: 999px; padding: 1px 9px; font-size: 0.8em; font-weight: 700; }}
.archy-pill-organizado {{ background-color: {PALETA["lima"]}; color: {PALETA["marino"]}; }}
.archy-pill-revisar {{ background-color: {PALETA["arena"]}; color: {PALETA["marino"]}; }}
.archy-pill-suelto {{ background-color: {PALETA["petroleo"]}; color: #ffffff; }}
.archy-pill-vacio {{ background-color: alpha(currentColor, 0.10); }}
"""

# Tema de toda la app (se puede apagar).
CSS_TEMA = f"""
@define-color accent_bg_color {PALETA["petroleo"]};
@define-color accent_fg_color #ffffff;
@define-color accent_color {PALETA["petroleo"]};
@define-color headerbar_bg_color {PALETA["marino"]};
@define-color headerbar_fg_color #ffffff;
@define-color headerbar_backdrop_color {PALETA["marino"]};
:root {{
  --accent-bg-color: {PALETA["petroleo"]};
  --accent-fg-color: #ffffff;
  --accent-color: {PALETA["petroleo"]};
  --headerbar-bg-color: {PALETA["marino"]};
  --headerbar-fg-color: #ffffff;
  --headerbar-backdrop-color: {PALETA["marino"]};
}}
@media (prefers-color-scheme: dark) {{
  :root {{ --accent-color: {PALETA["turquesa"]}; }}
}}
headerbar, toolbarview > .top-bar headerbar {{
  background-color: {PALETA["marino"]};
  color: #ffffff;
}}
headerbar .dim-label, headerbar .subtitle {{ color: alpha(#ffffff, 0.75); }}
"""

_PRIORIDAD = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10


def _poner_css(nombre: str, css: str | None) -> bool:
    """Agrega o quita una hoja de estilos de toda la app.

    El proveedor se guarda en el módulo Gtk para no duplicarlo cuando la app
    recarga las extensiones (cada recarga crea un módulo nuevo).
    """
    display = Gdk.Display.get_default()
    if display is None:
        return False
    atributo = f"_archy_css_{nombre}"
    anterior = getattr(Gtk, atributo, None)
    if anterior is not None:
        Gtk.StyleContext.remove_provider_for_display(display, anterior)
        setattr(Gtk, atributo, None)
    if css:
        proveedor = Gtk.CssProvider()
        if hasattr(proveedor, "load_from_string"):
            proveedor.load_from_string(css)
        else:
            proveedor.load_from_data(css, -1)
        Gtk.StyleContext.add_provider_for_display(display, proveedor, _PRIORIDAD)
        setattr(Gtk, atributo, proveedor)
    return False  # para GLib.idle_add


def _tamano(nbytes: int) -> str:
    for unidad in ("B", "KB", "MB"):
        if nbytes < 1024 or unidad == "MB":
            return f"{nbytes:.0f} {unidad}" if unidad == "B" else f"{nbytes:.1f} {unidad}"
        nbytes /= 1024
    return f"{nbytes:.1f} MB"


def _pill(texto: str, clase: str) -> Gtk.Label:
    etiqueta = Gtk.Label(label=texto, valign=Gtk.Align.CENTER)
    etiqueta.add_css_class("archy-pill")
    etiqueta.add_css_class(clase)
    return etiqueta


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


class PanelArchy(AvatarHandler):
    """Explorador de solo lectura de la carpeta Trabajos (en el lugar del avatar)."""

    key = "archy"

    def __init__(self, settings, path: str):
        super().__init__(settings, path)
        # AvatarHandler no inicializa estos atributos de Handler y la app los consulta.
        self.error_func = None
        self._is_installed_cache = True
        self.pip_path = os.path.join(os.path.dirname(os.path.abspath(path)), "pip")
        self._lista: Gtk.ListBox | None = None
        self._ruta: Gtk.Label | None = None
        self._resumen: Gtk.Label | None = None
        self._spinner: Gtk.Spinner | None = None
        self._boton: Gtk.Button | None = None

    # -- Lo que pide AvatarHandler (Archy no tiene cara ni voz) -------------

    @staticmethod
    def support_emotions() -> bool:
        return False

    def is_installed(self) -> bool:
        return True  # no necesita descargar nada

    def get_expressions(self) -> list[str]:
        return []

    def get_motions(self) -> list[str]:
        return []

    def set_expression(self, expression: str):
        pass

    def do_motion(self, motion: str):
        pass

    def speak_with_tts(self, *args, **kwargs):
        pass

    def speak(self, *args, **kwargs):
        pass

    def set_mouth(self, value: float):
        pass

    # -- Interfaz -----------------------------------------------------------

    def create_gtk_widget(self) -> Gtk.Widget:
        _poner_css("panel", CSS_PANEL)
        self.stop_request = False

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                        hexpand=True, vexpand=True)
        panel.add_css_class("archy-panel")

        # Encabezado: logo, nombre, eslogan y aviso de transparencia.
        encabezado = Gtk.Box(spacing=12)
        if os.path.exists(LOGO):
            logo = Gtk.Picture.new_for_filename(LOGO)
            logo.set_size_request(64, 64)
            logo.set_can_shrink(True)
            if hasattr(logo, "set_content_fit"):
                logo.set_content_fit(Gtk.ContentFit.CONTAIN)
            encabezado.append(logo)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
        nombre = Gtk.Label(label="Archy", xalign=0)
        nombre.add_css_class("archy-nombre")
        eslogan = Gtk.Label(label=_("Tu archivista de confianza, 100 % local."), xalign=0, wrap=True)
        eslogan.add_css_class("dim-label")
        eslogan.add_css_class("caption")
        agente = Gtk.Label(label=_("Agente automatizado · no es una persona"), xalign=0, halign=Gtk.Align.START)
        agente.add_css_class("archy-agente")
        for w in (nombre, eslogan, agente):
            textos.append(w)
        encabezado.append(textos)
        panel.append(encabezado)

        # Ruta de la carpeta Trabajos.
        fila_ruta = Gtk.Box(spacing=8)
        fila_ruta.add_css_class("archy-ruta")
        fila_ruta.append(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
        self._ruta = Gtk.Label(label="…", xalign=0, hexpand=True,
                               ellipsize=Pango.EllipsizeMode.START)
        fila_ruta.append(self._ruta)
        panel.append(fila_ruta)

        # Resumen + botón de actualizar.
        barra = Gtk.Box(spacing=8)
        self._resumen = Gtk.Label(label=_("Revisando la carpeta…"), xalign=0, hexpand=True, wrap=True)
        self._resumen.add_css_class("dim-label")
        self._spinner = Gtk.Spinner()
        self._boton = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Actualizar"))
        self._boton.add_css_class("flat")
        self._boton.connect("clicked", lambda *_a: self.actualizar())
        for w in (self._resumen, self._spinner, self._boton):
            barra.append(w)
        panel.append(barra)

        # Contenido.
        self._lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._lista.add_css_class("boxed-list")
        desplazable = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        desplazable.set_child(self._lista)
        panel.append(desplazable)

        pie = Gtk.Label(label=_("Solo lectura: Archy no mueve nada sin tu aprobación."),
                        wrap=True, xalign=0)
        pie.add_css_class("dim-label")
        pie.add_css_class("caption")
        panel.append(pie)

        self.actualizar()
        return panel

    def actualizar(self):
        """Vuelve a escanear Trabajos en segundo plano."""
        if self._spinner is not None:
            self._spinner.start()
        if self._boton is not None:
            self._boton.set_sensitive(False)
        threading.Thread(target=self._escanear, daemon=True).start()

    def _escanear(self):
        try:
            from nucleo.configuracion import ConfigInvalida, cargar_config
            from nucleo.escaner import escanear
            from nucleo.guardian import ErrorGuardian, Guardian
        except ImportError:
            GLib.idle_add(self._mostrar_error, None,
                          _("No se encontró el núcleo de Archy. Ejecuta archy/instalar.sh."))
            return
        try:
            config = cargar_config(CONFIG)
            guardian = Guardian(config.carpeta_raiz, config.lista_negra_extra)
            resultado = escanear(guardian, config)
        except ConfigInvalida as error:
            GLib.idle_add(self._mostrar_error, None, str(error))
        except ErrorGuardian as error:
            GLib.idle_add(self._mostrar_error, None, str(error))
        except Exception as error:  # nunca dejar el panel colgado
            GLib.idle_add(self._mostrar_error, None, _("Error inesperado: ") + str(error))
        else:
            GLib.idle_add(self._mostrar, config, resultado)

    def _terminar_carga(self):
        if self._spinner is not None:
            self._spinner.stop()
        if self._boton is not None:
            self._boton.set_sensitive(True)

    def _limpiar(self):
        while (fila := self._lista.get_first_child()) is not None:
            self._lista.remove(fila)

    def _mostrar_error(self, ruta, mensaje: str):
        if self.stop_request or self._lista is None:
            return False
        self._terminar_carga()
        self._limpiar()
        if ruta:
            self._ruta.set_label(ruta)
        self._resumen.set_label(_("No se pudo revisar la carpeta."))
        fila = Adw.ActionRow(title=_("Revisa la configuración de Archy"), subtitle=mensaje)
        fila.set_subtitle_lines(0)
        fila.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        self._lista.append(fila)
        return False

    def _mostrar(self, config, resultado):
        if self.stop_request or self._lista is None:
            return False
        self._terminar_carga()
        self._limpiar()
        self._ruta.set_label(resultado.raiz)
        self._ruta.set_tooltip_text(resultado.raiz)

        sin_organizar = []
        grupos: dict[str, list] = {}
        for archivo in resultado.archivos:
            partes = archivo.ruta_relativa.split("/")
            if len(partes) == 1:
                sin_organizar.append(archivo)
            else:
                grupos.setdefault(partes[0].casefold(), []).append(archivo)

        resumen = resultado.resumen()
        sueltos = resumen["por_ubicacion"].get("suelto", 0)
        texto = (f"{_plural(resumen['archivos'], 'archivo', 'archivos')} · "
                 f"{sueltos} sin organizar")
        if resultado.limite_alcanzado:
            texto += " · se alcanzó el límite de archivos"
        self._resumen.set_label(texto)

        # 1. Archivos sueltos en la raíz: es el trabajo pendiente.
        self._agregar_grupo(_("Sin organizar"), "folder-symbolic", sin_organizar,
                            "archy-pill-suelto", expandido=True)
        # 2. Materias (aunque estén vacías) y carpeta de dudas.
        for materia in config.nombres_materias:
            self._agregar_grupo(materia, "folder-symbolic", grupos.pop(materia.casefold(), []),
                                "archy-pill-organizado")
        self._agregar_grupo(config.carpeta_dudas, "folder-symbolic",
                            grupos.pop(config.carpeta_dudas.casefold(), []), "archy-pill-revisar")
        # 3. Otras carpetas que el estudiante ya tenía.
        for clave in sorted(grupos):
            archivos = grupos[clave]
            nombre = archivos[0].ruta_relativa.split("/")[0]
            self._agregar_grupo(nombre, "folder-symbolic", archivos, "archy-pill-suelto")
        # 4. Lo que no se muestra y por qué (transparencia).
        if resultado.omitidos:
            fila = Adw.ExpanderRow(title=_("No visibles"),
                                   subtitle=_("Archy no los revisa; abre para ver el motivo"))
            fila.add_prefix(Gtk.Image.new_from_icon_name("action-unavailable-symbolic"))
            fila.add_suffix(_pill(str(len(resultado.omitidos)), "archy-pill-vacio"))
            for omitido in resultado.omitidos:
                hijo = Adw.ActionRow(title=GLib.markup_escape_text(omitido.ruta_relativa),
                                     subtitle=GLib.markup_escape_text(omitido.motivo))
                hijo.set_subtitle_lines(0)
                fila.add_row(hijo)
            self._lista.append(fila)
        return False

    def _agregar_grupo(self, titulo: str, icono: str, archivos: list, clase_pill: str,
                       expandido: bool = False):
        fila = Adw.ExpanderRow(title=GLib.markup_escape_text(titulo))
        fila.add_prefix(Gtk.Image.new_from_icon_name(icono))
        fila.add_suffix(_pill(str(len(archivos)), clase_pill if archivos else "archy-pill-vacio"))
        if not archivos:
            fila.set_subtitle(_("vacía"))
            fila.set_enable_expansion(False)
        for archivo in archivos:
            partes = archivo.ruta_relativa.split("/")
            carpeta = "/".join(partes[1:-1])
            detalle = f"{NOMBRE_TIPO.get(archivo.tipo, archivo.tipo)} · {_tamano(archivo.tamano_bytes)}"
            if carpeta:
                detalle = f"{carpeta}/ · {detalle}"
            hijo = Adw.ActionRow(title=GLib.markup_escape_text(archivo.nombre),
                                 subtitle=GLib.markup_escape_text(detalle))
            hijo.set_title_lines(1)
            hijo.add_prefix(Gtk.Image.new_from_icon_name(ICONOS_TIPO.get(archivo.tipo, ICONO_OTROS)))
            hijo.set_tooltip_text(archivo.ruta_relativa)
            fila.add_row(hijo)
        if archivos and expandido:
            fila.set_expanded(True)
        self._lista.append(fila)

    def stop(self):
        self.stop_request = True

    def destroy(self, add=None):
        self.stop_request = True


class ArchyExtension(NewelleExtension):
    id = "archy"
    name = "Archy: organizador de archivos"

    def get_avatar_handlers(self) -> list[dict]:
        # La app solo llama esto si la extensión está activa: buen momento para el tema.
        GLib.idle_add(self._actualizar_tema)
        return [{
            "key": PanelArchy.key,
            "title": _("Archy: explorador de Trabajos"),
            "description": _("Muestra la carpeta Trabajos en lugar de un personaje animado"),
            "class": PanelArchy,
        }]

    def get_extra_settings(self) -> list:
        return [
            ExtraSettings.ToggleSetting(
                "tema", _("Colores de Archy"),
                _("Aplica la paleta de Archy (azul marino, petróleo y turquesa) a toda la app"),
                True,
            ),
        ]

    def set_setting(self, key, value):
        super().set_setting(key, value)
        if key == "tema":
            GLib.idle_add(self._actualizar_tema)

    def _actualizar_tema(self):
        activo = self.get_setting("tema", False, True)
        _poner_css("tema", CSS_TEMA if activo else None)
        return False

    def on_uninstall(self):
        GLib.idle_add(_poner_css, "tema", None)
