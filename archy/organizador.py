"""Archy - extensión principal para NyarchAssistant.

Por ahora aporta:
- el panel "Archy": un explorador de solo lectura de la carpeta Trabajos que
  ocupa el lugar del avatar animado (Arch-chan sigue instalada; solo se elige
  "Archy" en Configuración -> Avatar);
- el tema de colores de Archy (se puede apagar en los ajustes de la extensión);
- herramientas del chat: proponer_plan, ver_archivo, deshacer, historial y,
  en modo desarrollo, medir_clasificador. Cada una muestra una tarjeta en el
  chat y al modelo solo le pasa un resumen corto.

El modelo NO puede mover archivos: el plan se aprueba, edita y aplica con los
botones de la tarjeta (con confirmación), y deshacer también es un botón.
Por defecto todo es simulación; para mover de verdad se activa "Modo real"
en Configuración -> Extensiones -> Archy.

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
# Bitácora fuera de Trabajos: solo rutas y metadatos, nunca contenido.
BITACORA = os.path.join(ARCHY_DIR, "bitacora.sqlite3")
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
        PanelArchy._activo = self      # las tarjetas lo refrescan después de mover o deshacer

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


def _confirmar(widget: Gtk.Widget, titulo: str, cuerpo: str, boton: str, al_aceptar) -> None:
    """Diálogo de confirmación (control humano antes de mover o deshacer)."""
    if hasattr(Adw, "AlertDialog"):
        dialogo = Adw.AlertDialog(heading=titulo, body=cuerpo)
    else:
        dialogo = Adw.MessageDialog(transient_for=widget.get_root(), heading=titulo, body=cuerpo)
    dialogo.add_response("cancelar", _("Cancelar"))
    dialogo.add_response("aceptar", boton)
    dialogo.set_response_appearance("aceptar", Adw.ResponseAppearance.SUGGESTED)
    dialogo.set_default_response("cancelar")
    dialogo.set_close_response("cancelar")
    dialogo.connect("response", lambda _d, respuesta: al_aceptar() if respuesta == "aceptar" else None)
    if hasattr(Adw, "AlertDialog"):
        dialogo.present(widget)
    else:
        dialogo.present()


def _actualizar_panel() -> None:
    panel = getattr(PanelArchy, "_activo", None)
    if panel is not None and not panel.stop_request:
        GLib.idle_add(panel.actualizar)


ICONO_ESTADO = {"movido": "emblem-default-symbolic", "simulado": "view-reveal-symbolic",
                "omitido": "action-unavailable-symbolic", "error": "dialog-warning-symbolic"}


def _widget_resultados(resultados, simular: bool, deshaciendo: bool = False) -> Gtk.Widget:
    caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    hechos = sum(r.estado in ("movido", "simulado") for r in resultados)
    omitidos = sum(r.estado == "omitido" for r in resultados)
    errores = sum(r.estado == "error" for r in resultados)
    if deshaciendo:
        texto = f"Se regresaron {hechos} archivos a su lugar"
    elif simular:
        texto = f"Simulación: se moverían {hechos} archivos (no se movió nada)"
    else:
        texto = f"Se movieron {hechos} archivos"
    if omitidos:
        texto += f" · {omitidos} omitidos"
    if errores:
        texto += f" · {errores} con problema"
    etiqueta = Gtk.Label(label=texto, xalign=0, wrap=True)
    etiqueta.add_css_class("archy-titulo")
    caja.append(etiqueta)
    lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lista.add_css_class("boxed-list")
    detalle = Adw.ExpanderRow(title=_("Detalle"), subtitle=_("Qué pasó con cada archivo"))
    for r in resultados:
        destino = f"→ {r.destino} · " if r.destino else ""
        detalle.add_row(_fila(r.origen or _("Operación"), f"{destino}{r.detalle}",
                              ICONO_ESTADO.get(r.estado, ICONO_OTROS)))
    detalle.set_expanded(errores > 0 or len(resultados) <= 5)
    lista.append(detalle)
    caja.append(lista)
    return caja


def _boton_deshacer(ext, id_operacion: int, movidos: int, contenedor: Gtk.Box) -> Gtk.Button:
    """Botón que deshace una operación, con confirmación, y muestra el resultado en `contenedor`."""
    boton = Gtk.Button(label=_("Deshacer"), halign=Gtk.Align.START)

    def trabajar():
        try:
            from nucleo.ejecutor import deshacer
            config = ext._config()
            _op, resultados = deshacer(ext._bitacora(), ext._guardian(config), id_operacion)
            GLib.idle_add(mostrar, resultados, None)
        except Exception as error:
            GLib.idle_add(mostrar, [], str(error))

    def mostrar(resultados, error):
        if error:
            contenedor.append(_aviso(f"No se pudo deshacer: {error}"))
            boton.set_sensitive(True)
        else:
            contenedor.append(_widget_resultados(resultados, False, deshaciendo=True))
            _actualizar_panel()
        return False

    def al_aceptar():
        boton.set_sensitive(False)
        threading.Thread(target=trabajar, daemon=True).start()

    boton.connect("clicked", lambda _b: _confirmar(
        contenedor, _("¿Deshacer los cambios?"),
        f"Archy regresará {movidos} archivos a donde estaban. Si alguno cambió o su lugar original "
        "ya está ocupado, ese no se toca.", _("Deshacer"), al_aceptar))
    return boton


class _PlanUI:
    """Tarjeta del plan: el estudiante aprueba, corrige la materia, decide el renombre y aplica."""

    def __init__(self, plan, config, ocupadas, notas, ext):
        self.plan, self.config, self.ocupadas, self.ext = plan, config, list(ocupadas), ext
        self.opciones = list(config.nombres_materias) + [config.carpeta_dudas]
        self.filas: list = []
        self.controles: list = []
        self.caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        if not plan.acciones:
            for w in _widgets_mensaje(_("No hay archivos sin organizar en Trabajos.")):
                self.caja.append(w)
            return
        resumen = Gtk.Label(label=f"{_plural(len(plan.acciones), 'archivo sin organizar', 'archivos sin organizar')}"
                                  " · marca los que apruebas, corrige la materia si hace falta y aplica",
                            xalign=0, wrap=True)
        resumen.add_css_class("dim-label")
        self.caja.append(resumen)
        self.caja.append(_resumen_decisiones(plan.acciones))
        for nota in notas:
            self.caja.append(_aviso(nota))

        lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lista.add_css_class("boxed-list")
        for grupo in self.opciones:
            acciones = [a for a in plan.acciones if a.materia_propuesta == grupo]
            if not acciones:
                continue
            fila = Adw.ExpanderRow(title=_texto(grupo))
            fila.add_prefix(Gtk.Image.new_from_icon_name("folder-symbolic"))
            clase = "archy-pill-revisar" if grupo == config.carpeta_dudas else "archy-pill-organizado"
            fila.add_suffix(_pill(str(len(acciones)), clase))
            for a in sorted(acciones, key=lambda a: -a.confianza):
                fila.add_row(self._fila(a))
            fila.set_expanded(len(plan.acciones) <= 15)
            lista.append(fila)
        self.caja.append(lista)

        barra = Gtk.Box(spacing=8)
        self.estado = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        self.estado.add_css_class("dim-label")
        self.estado.add_css_class("caption")
        self.boton = Gtk.Button(valign=Gtk.Align.CENTER)
        self.boton.add_css_class("suggested-action")
        self.boton.connect("clicked", self._al_aplicar)
        barra.append(self.estado)
        barra.append(self.boton)
        self.caja.append(barra)
        self.resultados = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.caja.append(self.resultados)
        self._refrescar()

    def _fila(self, a) -> Adw.ActionRow:
        fila = Adw.ActionRow(title=_texto(a.nombre_original))
        fila.set_title_lines(1)
        fila.set_subtitle_lines(4)
        fila.set_tooltip_text(a.origen)
        aprobar = Gtk.CheckButton(active=a.aprobada, valign=Gtk.Align.CENTER,
                                  tooltip_text=_("Aprobar este movimiento"))
        aprobar.connect("toggled", lambda b, a=a: self._cambiar(a, "aprobada", b.get_active()))
        fila.add_prefix(aprobar)
        if a.puede_renombrar:
            renombrar = Gtk.ToggleButton(icon_name="document-edit-symbolic", active=a.renombrar,
                                         valign=Gtk.Align.CENTER,
                                         tooltip_text=f"Renombrar a {a.nombre_propuesto}")
            renombrar.add_css_class("flat")
            renombrar.connect("toggled", lambda b, a=a: self._cambiar(a, "renombrar", b.get_active()))
            fila.add_suffix(renombrar)
            self.controles.append(renombrar)
        fila.add_suffix(_pill(f"{a.confianza:.2f}", CLASE_DECISION[a.decision]))
        materia = Gtk.DropDown.new_from_strings(self.opciones)
        materia.set_selected(self.opciones.index(a.materia) if a.materia in self.opciones else len(self.opciones) - 1)
        materia.set_valign(Gtk.Align.CENTER)
        materia.set_tooltip_text(_("Cambiar la materia"))
        materia.connect("notify::selected",
                        lambda d, _p, a=a: self._cambiar(a, "materia", self.opciones[d.get_selected()]))
        fila.add_suffix(materia)
        self.controles += [aprobar, materia]
        self.filas.append((a, fila))
        return fila

    def _cambiar(self, accion, campo, valor):
        setattr(accion, campo, valor)
        self._refrescar()

    def _refrescar(self):
        from nucleo.planificador import asignar_destinos
        asignar_destinos(self.plan, self.config, self.ocupadas)
        for a, fila in self.filas:
            partes = [f"→ {a.destino}"]
            if a.materia != a.materia_propuesta:
                partes.append(f"Corregido por ti (Archy proponía {a.materia_propuesta})")
            else:
                partes.append(f"{a.motivo}")
            if a.nota:
                partes.append(a.nota)
            fila.set_subtitle(_texto("\n".join(partes)))
        n = len(self.plan.aprobadas)
        simular = self.ext._simular()
        if n:
            self.boton.set_label(f"Simular {n} cambios" if simular else f"Mover {n} archivos")
        else:
            self.boton.set_label(_("Nada aprobado"))
        self.boton.set_sensitive(n > 0)
        self.estado.set_label(
            _("Modo simulación: no se moverá nada. Para mover de verdad, activa «Modo real» en "
              "Configuración → Extensiones → Archy.") if simular else
            _("Modo real: los archivos aprobados se moverán dentro de Trabajos. Nada se borra y se puede deshacer."))

    def _bloquear(self, bloquear: bool):
        for control in self.controles:
            control.set_sensitive(not bloquear)
        self.boton.set_sensitive(not bloquear and bool(self.plan.aprobadas))

    def _al_aplicar(self, _boton):
        n = len(self.plan.aprobadas)
        simular = self.ext._simular()
        if simular:
            titulo, boton = f"¿Simular {n} cambios?", _("Simular")
            cuerpo = f"Archy mostrará qué pasaría con {n} archivos, sin moverlos."
        else:
            titulo, boton = f"¿Mover {n} archivos?", _("Mover")
            cuerpo = (f"Archy moverá {n} archivos aprobados dentro de Trabajos. No se borra ni se "
                      "sobrescribe nada, y puedes deshacerlo.")
        _confirmar(self.caja, titulo, cuerpo, boton, lambda: self._aplicar(simular))

    def _aplicar(self, simular: bool):
        self._bloquear(True)
        self.estado.set_label(_("Simulando…") if simular else _("Moviendo archivos…"))

        def trabajar():
            try:
                from nucleo.ejecutor import aplicar
                config = self.ext._config()
                op, resultados = aplicar(self.plan.acciones, self.ext._guardian(config), self.ext._bitacora(), simular)
                GLib.idle_add(self._mostrar, op, resultados, simular, None)
            except Exception as error:
                GLib.idle_add(self._mostrar, None, [], simular, str(error))

        threading.Thread(target=trabajar, daemon=True).start()

    def _mostrar(self, op, resultados, simular, error):
        if error:
            self.resultados.append(_aviso(f"No se pudo aplicar el plan: {error}"))
            self._bloquear(False)
            return False
        self.resultados.append(_widget_resultados(resultados, simular))
        if simular:
            self._bloquear(False)
            self._refrescar()
        else:
            self.estado.set_label(_("Plan aplicado. Para otro plan, pide de nuevo que organice la carpeta."))
            self.boton.set_sensitive(False)
            movidos = sum(r.estado == "movido" for r in resultados)
            if op is not None and movidos:
                self.resultados.append(_boton_deshacer(self.ext, op, movidos, self.resultados))
            _actualizar_panel()
        return False


def _widgets_plan(plan, config, ocupadas, notas, ext) -> list:
    return [_PlanUI(plan, config, ocupadas, notas, ext).caja]


def _widgets_deshacer(operacion, movimientos, ext) -> list:
    if operacion is None:
        return _widgets_mensaje(_("No hay cambios que deshacer."))
    caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    etiqueta = Gtk.Label(label=f"Último cambio: {operacion.fecha.replace('T', ' ')} · "
                               f"{_plural(operacion.movidos, 'archivo movido', 'archivos movidos')}",
                         xalign=0, wrap=True)
    caja.append(etiqueta)
    lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lista.add_css_class("boxed-list")
    detalle = Adw.ExpanderRow(title=_("Archivos que regresarían"), subtitle=_("De su lugar actual al original"))
    for m in movimientos:
        if m.estado == "movido":
            detalle.add_row(_fila(m.destino or "", f"← {m.origen}", "edit-undo-symbolic"))
    detalle.set_expanded(operacion.movidos <= 8)
    lista.append(detalle)
    caja.append(lista)
    caja.append(_boton_deshacer(ext, operacion.id, operacion.movidos, caja))
    return [caja]


def _widgets_historial(operaciones, movimientos, bloqueos) -> list:
    if not operaciones and not bloqueos:
        return _widgets_mensaje(_("Todavía no hay nada en la bitácora."))
    lista = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lista.add_css_class("boxed-list")
    for o in operaciones:
        if o.tipo == "deshacer":
            titulo = f"#{o.id} · Deshacer #{o.deshace}"
            detalle = f"{o.movidos} regresados"
        else:
            titulo = f"#{o.id} · {'Simulación' if o.simulacion else 'Aplicar plan'}"
            detalle = f"{o.total} archivos" if o.simulacion else f"{o.movidos} de {o.total} movidos"
        if o.deshecha_por:
            detalle += f" · deshecho en #{o.deshecha_por}"
        fila = Adw.ExpanderRow(title=_texto(titulo), subtitle=_texto(f"{o.fecha.replace('T', ' ')} · {detalle}"))
        fila.add_prefix(Gtk.Image.new_from_icon_name(
            "edit-undo-symbolic" if o.tipo == "deshacer" else
            "view-reveal-symbolic" if o.simulacion else "folder-symbolic"))
        for m in movimientos.get(o.id, [])[:60]:
            destino = f"→ {m.destino} · " if m.destino else ""
            fila.add_row(_fila(m.origen, f"{destino}{m.estado}" + (f" ({m.detalle})" if m.estado in ("omitido", "error") else ""),
                               ICONO_ESTADO.get(m.estado, ICONO_OTROS)))
        lista.append(fila)
    if bloqueos:
        fila = Adw.ExpanderRow(title=_texto(f"Bloqueos del guardián ({len(bloqueos)})"),
                               subtitle=_("Rutas que Archy se negó a tocar"))
        fila.add_prefix(Gtk.Image.new_from_icon_name("security-high-symbolic"))
        for b in bloqueos:
            fila.add_row(_fila(b.ruta, f"{b.fecha.replace('T', ' ')} · {b.motivo}", "action-unavailable-symbolic"))
        lista.append(fila)
    nota = Gtk.Label(label=_("La bitácora guarda rutas y metadatos, nunca el contenido de los archivos."),
                     xalign=0, wrap=True)
    nota.add_css_class("dim-label")
    nota.add_css_class("caption")
    return [lista, nota]


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

PROMPT_ARCHY = """Eres Archy, un agente automatizado (no una persona) que ayuda a un estudiante a organizar su carpeta Trabajos por materia (Seguridad Informática, Minería de Texto, Fundamentos de IA) y tipo de archivo. Tú NO puedes ver los archivos: solo las herramientas de Archy pueden. Nunca pidas al estudiante que pegue el contenido ni que te dé la ubicación.
- "organiza", "clasifica", "escanea" o "revisa" la carpeta -> llama a proponer_plan.
- Cualquier pregunta sobre un archivo ("¿qué es Doc1.docx?", "qué contiene escaneo_red.csv", "¿por qué vdksahdas.py va a Minería?") o un mensaje que sea solo un nombre de archivo ("escaner.py") -> llama a ver_archivo con ese nombre tal como lo escribió. Hazlo SIEMPRE, aunque ya hayas hablado de ese archivo antes. Si pregunta por varios, llama a ver_archivo una vez por cada uno.
- "deshaz", "deshacer", "regresa los archivos" -> llama a deshacer.
- "¿qué hiciste?", "historial", "bitácora" -> llama a historial.
- "mide el clasificador" -> llama a medir_clasificador (si existe).
- Tú no mueves ni borras archivos. El estudiante aprueba, corrige y aplica el plan con los botones de la tarjeta; deshacer también es un botón.
- Después de una herramienta, el estudiante ya ve la tarjeta completa. Contesta en 2 o 3 frases con los números principales; no copies listas.
- La clasificación la hace la herramienta, no tú: no cambies sus materias ni inventes archivos.
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
        def herramienta(nombre, descripcion, funcion, esquema, titulo, icono):
            return Tool(nombre, descripcion, funcion, schema=esquema, title=titulo,
                        restore_func=self._restaurar, tools_group="Archy", icon_name=icono)

        herramientas = [
            herramienta("proponer_plan",
                        "Archy: escanea y clasifica los archivos sin organizar de la carpeta Trabajos y muestra "
                        "un plan (materia, tipo, confianza, motivo y nombre propuesto) que el estudiante aprueba "
                        "y aplica con botones. Úsala cuando pidan organizar, clasificar, escanear o revisar la carpeta.",
                        self._proponer_plan, ESQUEMA_VACIO, _("Plan para Trabajos"), "folder-symbolic"),
            herramienta("ver_archivo",
                        "Archy: abre y explica UN archivo de la carpeta Trabajos (qué contiene, a qué materia "
                        "pertenece y por qué, qué nombre propone). Úsala siempre que pregunten '¿qué es X?', "
                        "'qué contiene X' o '¿por qué X va a tal materia?', o escriban solo un nombre de archivo. "
                        "Acepta el nombre incompleto o sin espacios. Solo lee.",
                        self._ver_archivo, ESQUEMA_VER, _("Ver archivo"), "x-office-document-symbolic"),
            herramienta("deshacer",
                        "Archy: muestra el último cambio que hizo en Trabajos y un botón para regresar los archivos "
                        "a su lugar. Úsala cuando pidan deshacer o regresar los archivos.",
                        self._deshacer, ESQUEMA_VACIO, _("Deshacer"), "edit-undo-symbolic"),
            herramienta("historial",
                        "Archy: muestra la bitácora: qué planes se aplicaron o simularon, qué se deshizo y qué "
                        "bloqueó el guardián. Úsala cuando pregunten qué hizo Archy.",
                        self._historial, ESQUEMA_VACIO, _("Historial"), "document-open-recent-symbolic"),
        ]
        if self._modo_desarrollo():
            herramientas.append(herramienta(
                "medir_clasificador",
                "Solo para el equipo de desarrollo: mide la exactitud del clasificador con el dataset "
                "etiquetado copiado en Trabajos.",
                self._medir_clasificador, ESQUEMA_MEDIR, _("Medir clasificador"), "view-list-symbolic"))
        return herramientas

    def preprocess_history(self, history: list, prompts: list) -> tuple[list, list]:
        """Agrega una pista de qué herramienta usar para el último mensaje del estudiante.

        La pista va en el campo interno "RetrievedContext" del mensaje: la app
        la manda al modelo dentro de <context> antes del mensaje, pero no la
        muestra y no cambia el texto que escribió el estudiante. (En esta ruta
        la app pasa el chat real, no una copia: si se cambia "Message", la app
        lo guarda y lo vuelve a dibujar, como pasó el 20 nov.)
        Ver nucleo/pistas.py: con la pista, Qwen 2.5 3B llamó a la herramienta
        correcta en 14 de 15 turnos; sin ella, en 1 de 5.
        """
        try:
            if not history:
                return history, prompts
            ultimo = history[-1]
            if ultimo.get("User") != "User" or ultimo.get("ToolContext"):
                return history, prompts
            from nucleo.pistas import ETIQUETA, pista_para
            contexto = list(ultimo.get("RetrievedContext") or [])
            if any(ETIQUETA in str(c) for c in contexto):
                return history, prompts
            extensiones = [e for lista in self._config().tipos.values() for e in lista]
            herramientas = [t.name for t in self.get_tools()]
            pista = pista_para(str(ultimo.get("Message") or ""), extensiones, herramientas)
            if pista:
                ultimo["RetrievedContext"] = contexto + [pista]
        except Exception as error:  # nunca romper el chat por una pista
            print("Archy: no se pudo agregar la pista:", error)
        return history, prompts

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

    def _config(self):
        from nucleo.configuracion import cargar_config
        return cargar_config(CONFIG)

    def _guardian(self, config=None):
        from nucleo.guardian import Guardian
        config = config or self._config()
        return Guardian(config.carpeta_raiz, config.lista_negra_extra)

    def _bitacora(self):
        from nucleo.bitacora import Bitacora
        return Bitacora(BITACORA)

    def _simular(self) -> bool:
        """Simulación salvo que se active "Modo real" (o config.yaml diga modo: real)."""
        try:
            if self._config().modo == "real":
                return False
        except Exception:
            pass
        return not self.get_setting("modo_real", False, False)

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
                texto, construir, args, *guardar = trabajo(tarjeta)
            except Exception as error:  # create_io_tool/Tool no atrapan errores
                texto = f"Archy no pudo completar la herramienta: {error}"
                construir, args, guardar = _widgets_mensaje, (texto, "dialog-error-symbolic"), []
            if tool_uuid:
                # Las tarjetas con botones se restauran sin botones (un plan viejo no se aplica).
                construir_r, args_r = guardar[0] if guardar else (construir, args)
                _RESULTADOS[tool_uuid] = (titulo, icono, construir_r, args_r)
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

    def _proponer_plan(self, tool_uuid: str = None, **_ignorados) -> ToolResult:
        def trabajo(tarjeta):
            from nucleo.escaner import escanear
            from nucleo.planificador import crear_plan, resumen_plan
            from nucleo.reporte import AVISO_MODELO, clasificar_archivos
            config, guardian, clasificador, respaldo, etapas, notas = self._preparar()
            escaneo = escanear(guardian, config)
            sueltos = [a for a in escaneo.archivos if a.ubicacion == "suelto"]

            def progreso(i, n):
                if tarjeta is not None:
                    tarjeta.progreso(f"Clasificando {i}/{n} ({etapas})…")

            filas = clasificar_archivos(guardian, config, sueltos, clasificador, respaldo, progreso)
            if any(f.aviso and AVISO_MODELO in f.aviso for f in filas):
                notas.append("Ollama dejó de responder durante la clasificación: el resto se hizo solo con reglas.")
            plan = crear_plan(filas, escaneo.archivos, config)
            texto = resumen_plan(plan, config) + f"\nEtapas usadas: {etapas}." + (" " + " ".join(notas) if notas else "")
            if self._simular():
                texto += "\nModo simulación activo: al aplicar no se moverá nada."
            ocupadas = [a.ruta_relativa for a in escaneo.archivos]
            guardado = (_widgets_mensaje, (f"Plan de {len(plan.acciones)} archivos. Este plan ya no está activo: "
                                           "pide «organiza mi carpeta» para hacer uno nuevo.",))
            return texto, _widgets_plan, (plan, config, ocupadas, notas, self), guardado

        return self._lanzar(_("Plan para Trabajos"), "folder-symbolic", trabajo, tool_uuid)

    def _deshacer(self, tool_uuid: str = None, **_ignorados) -> ToolResult:
        def trabajo(_tarjeta):
            config = self._config()
            bitacora = self._bitacora()
            raiz = str(self._guardian(config).raiz)
            operacion = bitacora.ultima_deshacible(raiz)
            guardado = (_widgets_mensaje, (_("Para deshacer, pide de nuevo «deshacer»."),))
            if operacion is None:
                return "No hay cambios que deshacer.", _widgets_deshacer, (None, [], self), guardado
            texto = (f"El último cambio ({operacion.fecha.replace('T', ' ')}) movió {operacion.movidos} archivos. "
                     "El estudiante puede regresarlos con el botón Deshacer de la tarjeta.")
            return texto, _widgets_deshacer, (operacion, bitacora.movimientos(operacion.id), self), guardado

        return self._lanzar(_("Deshacer"), "edit-undo-symbolic", trabajo, tool_uuid)

    def _historial(self, tool_uuid: str = None, **_ignorados) -> ToolResult:
        def trabajo(_tarjeta):
            bitacora = self._bitacora()
            operaciones = bitacora.operaciones(limite=10)
            movimientos = {o.id: bitacora.movimientos(o.id) for o in operaciones}
            bloqueos = bitacora.bloqueos(limite=10)
            if not operaciones and not bloqueos:
                texto = "La bitácora está vacía: Archy todavía no ha aplicado ni simulado ningún plan."
            else:
                texto = "Últimas operaciones: " + "; ".join(
                    f"#{o.id} {o.fecha.replace('T', ' ')} "
                    + ("deshacer" if o.tipo == "deshacer" else "simulación" if o.simulacion else "aplicar")
                    + f" ({o.movidos} movidos)" + (" [deshecha]" if o.deshecha_por else "")
                    for o in operaciones[:5]) + f". Bloqueos del guardián: {len(bloqueos)}."
            return texto, _widgets_historial, (operaciones, movimientos, bloqueos)

        return self._lanzar(_("Historial"), "document-open-recent-symbolic", trabajo, tool_uuid)

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
                     + f"Leído como {extraccion.metodo}. Inicio del contenido: {extraccion.texto[:300]!r}.")
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
            ExtraSettings.ToggleSetting(
                "modo_real", _("Modo real (mover archivos)"),
                _("Apagado: los planes solo se simulan. Encendido: al aplicar un plan, Archy mueve los "
                  "archivos aprobados dentro de Trabajos (nunca borra y se puede deshacer)."),
                False,
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
