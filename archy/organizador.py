"""Archy - extensión principal para NyarchAssistant.

Por ahora aporta:
- el panel "Archy": un explorador de solo lectura de la carpeta Trabajos que
  ocupa el lugar del avatar animado (Arch-chan sigue instalada; solo se elige
  "Archy" en Configuración -> Avatar);
- el tema de colores de Archy (se puede apagar en los ajustes de la extensión);
- herramientas de solo lectura para el chat: clasificar_carpeta, ver_archivo y,
  en modo desarrollo, medir_clasificador. Cada una muestra su tabla en el chat
  y al modelo solo le pasa un resumen corto. Ninguna mueve ni renombra nada.

Faltan proponer_plan, aplicar_plan, deshacer e historial (planificador,
ejecutor y bitácora).

Instalación: ejecutar `archy/instalar.sh`. Copia este archivo a la carpeta de
extensiones y el núcleo, config.yaml y el logo a
~/.var/app/moe.nyarchlinux.assistant/data/archy/.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from urllib.parse import urlparse
from gettext import gettext as _

from gi.repository import Adw, Gdk, GLib, Gtk, Pango

# NyarchAssistant carga este archivo dentro de su propio paquete: imports relativos.
from .extensions import NewelleExtension
from .handlers import ExtraSettings
from .handlers.avatar import AvatarHandler
from .tools import Tool, ToolResult

# Carpeta con el núcleo, config.yaml y el logo (la app siempre puede leerla).
ARCHY_DIR = os.path.join(GLib.get_user_data_dir(), "archy")
if ARCHY_DIR not in sys.path:
    sys.path.insert(0, ARCHY_DIR)

LOGO = os.path.join(ARCHY_DIR, "assets", "logo.png")
CONFIG = os.path.join(ARCHY_DIR, "config.yaml")
ETIQUETAS = os.path.join(ARCHY_DIR, "dataset", "etiquetas.csv")
OLLAMA_POR_DEFECTO = "http://localhost:11434"

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
.archy-tarjeta {{ padding: 12px; }}
.archy-titulo {{ font-weight: 800; }}
.archy-mono {{ font-family: monospace; font-size: 0.85em; }}
.archy-aviso {{
  border-radius: 8px; padding: 6px 10px; font-size: 0.85em;
  background-color: alpha({PALETA["arena"]}, 0.35);
}}
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


# ---------------------------------------------------------------------------
# Herramientas del chat: widgets
# ---------------------------------------------------------------------------

CLASE_DECISION = {"mover": "archy-pill-organizado", "advertir": "archy-pill-suelto",
                  "revisar": "archy-pill-revisar"}

# Resultados de esta sesión, para volver a dibujar la tabla al reabrir un chat.
# Solo en memoria: no se guarda en disco (la bitácora será otra cosa).
_RESULTADOS: dict[str, tuple] = {}


def _en_hilo_principal(funcion, *args):
    """Ejecuta `funcion` en el hilo de GTK y devuelve su resultado."""
    if threading.current_thread() is threading.main_thread():
        return funcion(*args)
    caja, listo = [], threading.Event()

    def correr():
        try:
            caja.append(funcion(*args))
        finally:
            listo.set()
        return False

    GLib.idle_add(correr)
    listo.wait(15)
    return caja[0] if caja else None


def _texto(texto: str) -> str:
    return GLib.markup_escape_text(texto or "")


def _fila(titulo: str, subtitulo: str = "", icono: str | None = None,
          sufijo: Gtk.Widget | None = None, lineas: int = 0) -> Adw.ActionRow:
    fila = Adw.ActionRow(title=_texto(titulo), subtitle=_texto(subtitulo))
    fila.set_subtitle_lines(lineas)
    if icono:
        fila.add_prefix(Gtk.Image.new_from_icon_name(icono))
    if sufijo is not None:
        fila.add_suffix(sufijo)
    return fila


def _aviso(texto: str) -> Gtk.Label:
    etiqueta = Gtk.Label(label=texto, wrap=True, xalign=0)
    etiqueta.add_css_class("archy-aviso")
    return etiqueta


class TarjetaArchy(Gtk.Box):
    """Tarjeta que una herramienta de Archy muestra en el chat.

    Empieza con un indicador de progreso y luego muestra el resultado. Sus
    métodos públicos se pueden llamar desde cualquier hilo.
    """

    def __init__(self, titulo: str, icono: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        _poner_css("panel", CSS_PANEL)
        self.add_css_class("card")
        self.add_css_class("archy-tarjeta")
        encabezado = Gtk.Box(spacing=8)
        encabezado.append(Gtk.Image.new_from_icon_name(icono))
        etiqueta = Gtk.Label(label=titulo, xalign=0, hexpand=True)
        etiqueta.add_css_class("archy-titulo")
        encabezado.append(etiqueta)
        agente = Gtk.Label(label=_("Agente automatizado"))
        agente.add_css_class("archy-agente")
        encabezado.append(agente)
        self.append(encabezado)

        self._estado = Gtk.Box(spacing=8)
        self._spinner = Gtk.Spinner()
        self._spinner.start()
        self._mensaje = Gtk.Label(label=_("Revisando la carpeta…"), xalign=0, wrap=True)
        self._mensaje.add_css_class("dim-label")
        self._estado.append(self._spinner)
        self._estado.append(self._mensaje)
        self.append(self._estado)

    def progreso(self, texto: str):
        GLib.idle_add(self._mensaje.set_label, texto)

    def mostrar(self, construir, *args):
        """Cambia el progreso por lo que devuelva `construir(*args)` (una lista de widgets)."""
        def poner():
            self._spinner.stop()
            self.remove(self._estado)
            for widget in construir(*args):
                self.append(widget)
            return False
        if threading.current_thread() is threading.main_thread():
            poner()
        else:
            GLib.idle_add(poner)


def _widgets_mensaje(texto: str, icono: str = "dialog-information-symbolic") -> list:
    caja = Gtk.Box(spacing=8)
    caja.append(Gtk.Image.new_from_icon_name(icono))
    caja.append(Gtk.Label(label=texto, wrap=True, xalign=0, hexpand=True))
    return [caja]


def _resumen_decisiones(filas) -> Gtk.Box:
    from nucleo.clasificador import ADVERTIR, MOVER, REVISAR
    caja = Gtk.Box(spacing=6)
    for decision, texto in ((MOVER, "se mueven"), (ADVERTIR, "con advertencia"), (REVISAR, "a revisar")):
        n = sum(f.decision == decision for f in filas)
        caja.append(_pill(f"{n} {texto}", CLASE_DECISION[decision] if n else "archy-pill-vacio"))
    return caja


def _fila_archivo(f) -> Adw.ActionRow:
    from nucleo.reporte import TEXTO_DECISION
    partes = []
    if f.renombrar:
        partes.append(f"→ {f.nombre_propuesto}")
    partes.append(f"{NOMBRE_TIPO.get(f.tipo, f.tipo)} · {TEXTO_DECISION[f.decision]}")
    partes.append(f.motivo)
    if f.aviso:
        partes.append(f"Aviso: {f.aviso}")
    fila = _fila(f.nombre, "\n".join(partes), ICONOS_TIPO.get(f.tipo, ICONO_OTROS),
                 _pill(f"{f.confianza:.2f}", CLASE_DECISION[f.decision]))
    fila.set_tooltip_text(f.ruta_relativa)
    return fila


def _widgets_clasificacion(filas, materias, carpeta_dudas, notas, otros) -> list:
    widgets = []
    if not filas:
        texto = _("No hay archivos sin organizar en Trabajos.")
        if otros:
            texto += " " + _plural(otros, "archivo ya está organizado.", "archivos ya están organizados.")
        return _widgets_mensaje(texto)
    resumen = Gtk.Label(label=f"{_plural(len(filas), 'archivo sin organizar', 'archivos sin organizar')} · "
                              f"modo simulación: no se movió nada", xalign=0, wrap=True)
    resumen.add_css_class("dim-label")
    widgets += [resumen, _resumen_decisiones(filas)]
    widgets += [_aviso(n) for n in notas]

    lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lista.add_css_class("boxed-list")
    expandir = len(filas) <= 15
    for grupo in list(materias) + [carpeta_dudas]:
        del_grupo = [f for f in filas if f.materia == grupo]
        if not del_grupo:
            continue
        fila = Adw.ExpanderRow(title=_texto(grupo))
        fila.add_prefix(Gtk.Image.new_from_icon_name("folder-symbolic"))
        clase = "archy-pill-revisar" if grupo == carpeta_dudas else "archy-pill-organizado"
        fila.add_suffix(_pill(str(len(del_grupo)), clase))
        for f in sorted(del_grupo, key=lambda f: -f.confianza):
            fila.add_row(_fila_archivo(f))
        fila.set_expanded(expandir)
        lista.append(fila)
    widgets.append(lista)
    pie = Gtk.Label(label=_("Confianza ≥ 0.70: se propone mover · 0.45–0.70: con advertencia · "
                            "< 0.45: _Por revisar. Abre cada materia para ver el motivo."),
                    xalign=0, wrap=True)
    pie.add_css_class("dim-label")
    pie.add_css_class("caption")
    widgets.append(pie)
    return widgets


def _widgets_archivo(f, extraccion, notas) -> list:
    from nucleo.reporte import TEXTO_DECISION
    widgets = [_aviso(n) for n in notas]
    lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lista.add_css_class("boxed-list")
    lista.append(_fila(f.ruta_relativa, f"{NOMBRE_TIPO.get(f.tipo, f.tipo)}",
                       ICONOS_TIPO.get(f.tipo, ICONO_OTROS)))
    lista.append(_fila(f"Materia: {f.materia}", f.motivo, "folder-symbolic",
                       _pill(f"{f.confianza:.2f}", CLASE_DECISION[f.decision])))
    etapa = {"reglas": "reglas y palabras clave", "embeddings": "reglas + parecido semántico",
             "qwen": "reglas + consulta a Qwen"}.get(f.etapa, f.etapa)
    lista.append(_fila(f"Decisión: {TEXTO_DECISION[f.decision]}", f"Etapa usada: {etapa}",
                       "emblem-default-symbolic"))
    nombre = f"Nombre propuesto: {f.nombre_propuesto}" if f.renombrar else "Se conserva el nombre"
    lista.append(_fila(nombre, f.motivo_nombre, "document-edit-symbolic"))
    lectura = f"Leído como: {extraccion.metodo}"
    detalle = "se leyeron los primeros caracteres" if extraccion.truncado else "se leyó completo"
    if extraccion.aviso:
        detalle = extraccion.aviso
    lista.append(_fila(lectura, detalle, "x-office-document-symbolic"))
    if extraccion.texto.strip():
        texto = Adw.ExpanderRow(title=_("Lo que Archy leyó"),
                                subtitle=_("Solo se usa para clasificar; nunca se guarda"))
        texto.add_prefix(Gtk.Image.new_from_icon_name("view-reveal-symbolic"))
        contenido = Gtk.Label(label=extraccion.texto[:1500], wrap=True, xalign=0, selectable=True,
                              wrap_mode=Pango.WrapMode.WORD_CHAR)
        contenido.add_css_class("archy-mono")
        contenido.set_margin_start(12)
        contenido.set_margin_end(12)
        contenido.set_margin_top(8)
        contenido.set_margin_bottom(8)
        texto.add_row(contenido)
        lista.append(texto)
    widgets.append(lista)
    return widgets


def _widgets_medicion(m, etapas, notas, meta=0.85) -> list:
    if not m.total:
        return _widgets_mensaje(_("No hay archivos etiquetados sin organizar en Trabajos. Copia el "
                                  "dataset con verificar_dataset.py --copiar-a."), "dialog-warning-symbolic")
    widgets = [_aviso(n) for n in notas]
    lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lista.add_css_class("boxed-list")
    cumple = m.exactitud >= meta
    lista.append(_fila(f"Exactitud en materia: {m.aciertos}/{m.total}", f"Etapas: {etapas} · meta {meta:.0%}",
                       "emblem-default-symbolic" if cumple else "dialog-warning-symbolic",
                       _pill(f"{m.exactitud:.0%}", "archy-pill-organizado" if cumple else "archy-pill-revisar")))
    lista.append(_fila(f"Errores graves: {len(m.graves)}",
                       "Archivos que se moverían con confianza a la materia equivocada",
                       "dialog-error-symbolic" if m.graves else "emblem-default-symbolic",
                       _pill(str(len(m.graves)), "archy-pill-revisar" if m.graves else "archy-pill-organizado")))
    lista.append(_fila(f"Decisiones: {m.decisiones['mover']} mover · {m.decisiones['advertir']} advertencia · "
                       f"{m.decisiones['revisar']} a revisar",
                       f"Consultas a Qwen: {m.consultas_qwen} (acertó en {m.aciertos_qwen})",
                       "emblem-system-symbolic"))
    lista.append(_fila(f"Nombres válidos en PascalCase: {m.nombres_validos}/{m.nombres_propuestos}",
                       "Meta: 100 %", "document-edit-symbolic"))
    orden = {"facil": 0, "fácil": 0, "medio": 1, "media": 1, "dificil": 2, "difícil": 2}
    for dificultad in sorted(m.por_dificultad, key=lambda d: (orden.get(d, 9), d)):
        a, n = m.por_dificultad[dificultad]
        lista.append(_fila(f"Dificultad {dificultad}", f"{a}/{n} correctos", "view-list-symbolic",
                           _pill(f"{a / n:.0%}" if n else "—", "archy-pill-vacio")))
    if m.errores:
        errores = Adw.ExpanderRow(title=_texto(f"Errores de materia ({len(m.errores)})"),
                                  subtitle=_("Abre para ver el motivo de cada uno"))
        errores.add_prefix(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        for f, esperada in m.errores:
            grave = "GRAVE · " if f.decision == "mover" else ""
            errores.add_row(_fila(f.nombre, f"{grave}esperado: {esperada} · propuso: {f.materia} "
                                            f"({f.confianza:.2f})\n{f.motivo}",
                                  ICONOS_TIPO.get(f.tipo, ICONO_OTROS)))
        lista.append(errores)
    widgets.append(lista)
    if m.faltantes:
        widgets.append(_aviso(f"Faltan {len(m.faltantes)} archivos etiquetados en Trabajos."))
    pie = Gtk.Label(label=_("Advertencia: el dataset lo escribió el mismo equipo, así que estas cifras "
                            "son optimistas. La medición honesta será con trabajos reales."),
                    xalign=0, wrap=True)
    pie.add_css_class("dim-label")
    pie.add_css_class("caption")
    widgets.append(pie)
    return widgets


# ---------------------------------------------------------------------------
# Herramientas del chat: lógica
# ---------------------------------------------------------------------------

PROMPT_ARCHY = """Eres Archy, un agente automatizado (no una persona) que ayuda a un estudiante a organizar su carpeta Trabajos por materia (Seguridad Informática, Minería de Texto, Fundamentos de IA) y tipo de archivo.
- Si pide organizar, clasificar o revisar la carpeta, llama a clasificar_carpeta.
- Si pregunta por un archivo concreto (qué es, de qué materia, por qué), llama a ver_archivo con su nombre.
- Las herramientas ya le muestran al estudiante una tabla con todo el detalle: no la repitas; resume en 2 o 3 frases con los números del resultado.
- La clasificación la hace la herramienta, no tú: no cambies sus materias ni inventes archivos.
- Por ahora solo propones (modo simulación): no puedes mover, renombrar ni borrar archivos.
Responde en español, breve y claro."""

ESQUEMA_VACIO = {"type": "object", "properties": {}, "required": []}
ESQUEMA_VER = {
    "type": "object",
    "properties": {"nombre": {"type": "string",
                              "description": "Nombre del archivo o parte de él, ej. 'Doc1.docx'"}},
    "required": ["nombre"],
}
ESQUEMA_MEDIR = {
    "type": "object",
    "properties": {
        "embeddings": {"type": "boolean", "description": "Usar embeddings cuando las reglas dudan (por defecto true)"},
        "qwen": {"type": "boolean", "description": "Consultar a Qwen en los casos dudosos (por defecto true)"},
    },
    "required": [],
}


def _a_bool(valor, defecto: bool = True) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() not in ("false", "no", "0", "")
    return defecto


def _es_local(endpoint: str) -> bool:
    return (urlparse(endpoint).hostname or "") in ("localhost", "127.0.0.1", "::1")


class ArchyExtension(NewelleExtension):
    id = "archy"
    name = "Archy: organizador de archivos"

    # -- Herramientas -----------------------------------------------------------

    def get_tools(self) -> list:
        herramientas = [
            Tool("clasificar_carpeta",
                 "Clasifica los archivos sin organizar de la carpeta Trabajos: materia, tipo, confianza, "
                 "decisión, motivo y nombre propuesto. Solo lee; muestra la tabla al estudiante.",
                 self._clasificar_carpeta, schema=ESQUEMA_VACIO, title=_("Clasificar Trabajos"),
                 restore_func=self._restaurar, tools_group="Archy", icon_name="folder-symbolic"),
            Tool("ver_archivo",
                 "Explica un archivo de Trabajos: qué leyó Archy de él, a qué materia pertenece y por qué, "
                 "y qué nombre propone. Solo lee.",
                 self._ver_archivo, schema=ESQUEMA_VER, title=_("Ver archivo"),
                 restore_func=self._restaurar, tools_group="Archy", icon_name="x-office-document-symbolic"),
        ]
        if self._modo_desarrollo():
            herramientas.append(Tool(
                "medir_clasificador",
                "Solo para el equipo de desarrollo: mide la exactitud del clasificador con el dataset "
                "etiquetado copiado en Trabajos.",
                self._medir_clasificador, schema=ESQUEMA_MEDIR, title=_("Medir clasificador"),
                restore_func=self._restaurar, tools_group="Archy", icon_name="view-list-symbolic"))
        return herramientas

    def get_additional_prompts(self) -> list:
        return [{
            "key": "archy",
            "setting_name": "archy",
            "title": _("Archy"),
            "description": _("Explica al modelo cuándo usar las herramientas de Archy"),
            "editable": True,
            "show_in_settings": True,
            "default": True,
            "text": PROMPT_ARCHY,
        }]

    def _modo_desarrollo(self) -> bool:
        try:
            from nucleo.configuracion import cargar_config
            return cargar_config(CONFIG).modo_desarrollo
        except Exception:
            return False

    def _endpoint(self) -> str:
        """El mismo Ollama que usa la app (lo cambia usar_ollama.sh)."""
        try:
            ajustes = json.loads(self.settings.get_string("llm-settings"))
            endpoint = (ajustes.get("ollama") or {}).get("endpoint")
            if isinstance(endpoint, str) and endpoint.startswith("http"):
                return endpoint
        except Exception:
            pass
        return OLLAMA_POR_DEFECTO

    def _preparar(self, embeddings: bool = True, qwen: bool = True):
        """Carga config, guardián y clasificador. Si Ollama no está, usa solo reglas."""
        from nucleo.clasificador import Clasificador
        from nucleo.configuracion import cargar_config
        from nucleo.guardian import Guardian
        from nucleo.ollama import chat_json, disponible, embebedor

        config = cargar_config(CONFIG)
        guardian = Guardian(config.carpeta_raiz, config.lista_negra_extra)
        notas, embeber, consultar = [], None, None
        if embeddings or qwen:
            endpoint = self._endpoint()
            if not _es_local(endpoint):
                notas.append(f"Ollama remoto ({urlparse(endpoint).hostname}): solo para desarrollo con el "
                             "dataset de prueba; el contenido de los archivos viaja a otra PC.")
            if embeddings:
                if disponible(endpoint, config.modelo_embeddings):
                    embeber = embebedor(endpoint, config.modelo_embeddings)
                else:
                    notas.append(f"Ollama no tiene '{config.modelo_embeddings}' o no responde: sin embeddings.")
            if qwen:
                if disponible(endpoint, config.modelo):
                    # Mismo contexto que el chat, para que Ollama no recargue el modelo.
                    consultar = chat_json(endpoint, config.modelo, contexto=config.contexto_minimo)
                else:
                    notas.append(f"Ollama no tiene '{config.modelo}' o no responde: sin consultas a Qwen.")
        clasificador = Clasificador(config, embeber=embeber, consultar=consultar)
        respaldo = Clasificador(config) if (embeber or consultar) else None
        etapas = " → ".join(["reglas"] + (["embeddings"] if embeber else []) + (["Qwen"] if consultar else []))
        return config, guardian, clasificador, respaldo, etapas, notas

    def _lanzar(self, titulo: str, icono: str, trabajo, tool_uuid) -> ToolResult:
        """Crea la tarjeta, corre `trabajo(tarjeta)` en segundo plano y nunca deja el chat colgado.

        `trabajo` devuelve (texto para el modelo, constructor de widgets, argumentos).
        """
        resultado = ToolResult()
        tarjeta = _en_hilo_principal(TarjetaArchy, titulo, icono)
        if tarjeta is not None:
            resultado.set_widget(tarjeta)

        def correr():
            try:
                texto, construir, args = trabajo(tarjeta)
            except Exception as error:  # create_io_tool/Tool no atrapan errores
                texto = f"Archy no pudo completar la herramienta: {error}"
                construir, args = _widgets_mensaje, (texto, "dialog-error-symbolic")
            if tool_uuid:
                _RESULTADOS[tool_uuid] = (titulo, icono, construir, args)
            if tarjeta is not None:
                tarjeta.mostrar(construir, *args)
            resultado.set_output(texto)

        threading.Thread(target=correr, daemon=True).start()
        return resultado

    def _restaurar(self, tool_uuid: str = None, **_ignorados) -> ToolResult:
        resultado = ToolResult()
        guardado = _RESULTADOS.get(tool_uuid or "")
        if guardado is not None:
            titulo, icono, construir, args = guardado
        else:
            titulo, icono = _("Resultado de Archy"), "folder-symbolic"
            construir, args = _widgets_mensaje, (_("Este resultado es de una sesión anterior y no se guardó. "
                                                    "Pídele a Archy que lo haga de nuevo."),)
        tarjeta = _en_hilo_principal(TarjetaArchy, titulo, icono)
        if tarjeta is not None:
            tarjeta.mostrar(construir, *args)
            resultado.set_widget(tarjeta)
        resultado.set_output(None)
        return resultado

    def _clasificar_carpeta(self, tool_uuid: str = None, **_ignorados) -> ToolResult:
        def trabajo(tarjeta):
            from nucleo.escaner import escanear
            from nucleo.reporte import AVISO_MODELO, clasificar_archivos, resumen_clasificacion
            config, guardian, clasificador, respaldo, etapas, notas = self._preparar()
            escaneo = escanear(guardian, config)
            sueltos = [a for a in escaneo.archivos if a.ubicacion == "suelto"]
            otros = len(escaneo.archivos) - len(sueltos)

            def progreso(i, n):
                if tarjeta is not None:
                    tarjeta.progreso(f"Clasificando {i}/{n} ({etapas})…")

            filas = clasificar_archivos(guardian, config, sueltos, clasificador, respaldo, progreso)
            if any(f.aviso and AVISO_MODELO in f.aviso for f in filas):
                notas.append("Ollama dejó de responder durante la clasificación: el resto se hizo solo con reglas.")
            nota = f"Etapas usadas: {etapas}." + (" " + " ".join(notas) if notas else "")
            texto = resumen_clasificacion(filas, config, otros, nota)
            return texto, _widgets_clasificacion, (filas, config.nombres_materias, config.carpeta_dudas, notas, otros)

        return self._lanzar(_("Clasificación de Trabajos"), "folder-symbolic", trabajo, tool_uuid)

    def _ver_archivo(self, nombre: str = "", tool_uuid: str = None, **_ignorados) -> ToolResult:
        def trabajo(tarjeta):
            from nucleo.escaner import escanear
            from nucleo.reporte import TEXTO_DECISION, buscar_archivo, clasificar_uno
            config, guardian, clasificador, respaldo, etapas, notas = self._preparar()
            escaneo = escanear(guardian, config)
            archivo, candidatos = buscar_archivo(escaneo.archivos, str(nombre or ""))
            if archivo is None:
                if candidatos:
                    texto = (f"Hay varios archivos que coinciden con '{nombre}': " + ", ".join(candidatos[:10])
                             + ". Pide al estudiante que diga cuál.")
                else:
                    texto = f"No encontré '{nombre}' en la carpeta Trabajos."
                return texto, _widgets_mensaje, (texto, "dialog-question-symbolic")
            if tarjeta is not None:
                tarjeta.progreso(f"Leyendo {archivo.nombre}…")
            fila, extraccion = clasificar_uno(guardian, config, archivo, clasificador, respaldo)
            texto = (f"{fila.ruta_relativa}: {fila.materia} (confianza {fila.confianza:.2f}, "
                     f"{TEXTO_DECISION[fila.decision]}). Motivo: {fila.motivo}. "
                     + (f"Nombre propuesto: {fila.nombre_propuesto}. " if fila.renombrar else "Se conserva el nombre. ")
                     + f"Leído como {extraccion.metodo}. Inicio del contenido: {extraccion.texto[:300]!r}. "
                     "El detalle ya se muestra al estudiante.")
            return texto, _widgets_archivo, (fila, extraccion, notas)

        return self._lanzar(_("Archivo"), "x-office-document-symbolic", trabajo, tool_uuid)

    def _medir_clasificador(self, embeddings=True, qwen=True, tool_uuid: str = None, **_ignorados) -> ToolResult:
        def trabajo(tarjeta):
            from nucleo.escaner import escanear
            from nucleo.reporte import (archivos_del_dataset, clasificar_archivos, leer_etiquetas, medir,
                                        resumen_medicion)
            if not os.path.exists(ETIQUETAS):
                texto = "No están las etiquetas: instala con 'bash archy/instalar.sh <Trabajos> --desarrollo'."
                return texto, _widgets_mensaje, (texto, "dialog-warning-symbolic")
            config, guardian, clasificador, respaldo, etapas, notas = self._preparar(
                _a_bool(embeddings), _a_bool(qwen))
            etiquetas = leer_etiquetas(ETIQUETAS)
            # Solo los archivos del dataset (una carpeta): nunca se clasifican ni se envían otros.
            sueltos = [a for a in escanear(guardian, config).archivos if a.ubicacion == "suelto"]
            archivos = archivos_del_dataset(sueltos, {e["archivo"] for e in etiquetas})

            def progreso(i, n):
                if tarjeta is not None:
                    tarjeta.progreso(f"Midiendo {i}/{n} ({etapas})…")

            filas = clasificar_archivos(guardian, config, archivos, clasificador, respaldo, progreso)
            m = medir(filas, etiquetas)
            return resumen_medicion(m, etapas), _widgets_medicion, (m, etapas, notas)

        return self._lanzar(_("Medición del clasificador"), "view-list-symbolic", trabajo, tool_uuid)

    # -- Panel y tema -------------------------------------------------------------

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
