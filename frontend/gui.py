from __future__ import annotations

import calendar
import shlex
import threading
import time
import webbrowser
import tkinter as tk
import customtkinter as ctk          # GUI moderna con esquinas redondeadas y dark mode
from dataclasses import dataclass
from datetime import datetime, timedelta
from tkinter import filedialog, ttk
from typing import Callable

from tkcalendar import DateEntry

from backend.browser_worker import BrowserRuntimeSettings
from backend.config_store import ConfigStore, SUPPORTED_BROWSERS
from backend.i18n import Translator, CANONICAL_REPEAT_OPTIONS
from backend.logging_service import LoggingService
from backend.whatsapp_backend import WhatsAppBackend

# URL del botón de donaciones
_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=ZABFRXC2P3JQN"

# === Sistema de diseño visual — Tema WhatsApp Pro ===
_C_PRIMARY    = "#075E54"   # Verde oscuro — botones principales, tabs activos
_C_ACCENT     = "#128C7E"   # Verde teal — botones secundarios, hover
_C_ACTION     = "#25D366"   # Verde vivo — hover de acción, estado OK
_C_BG_MAIN    = "#F0F2F5"   # Fondo principal (gris muy claro)
_C_BG_CARD    = "#FFFFFF"   # Fondo de tarjetas y áreas editables
_C_BG_TOP     = "#E6E8EB"   # Fondo barra superior (diferenciada)
_C_TEXT       = "#111B21"   # Texto principal (casi negro)
_C_TEXT_MUTED = "#667781"   # Texto secundario (gris azulado)
_C_LOG_BG     = "#1E2328"   # Fondo del área de logs (oscuro)
_C_LOG_FG     = "#B2CFD8"   # Texto del log sobre fondo oscuro
_C_EXIT       = "#546475"   # Botón salir (gris oscuro)
_C_EXIT_H     = "#3D4F5C"   # Hover del botón salir

_F_BODY   = ("Segoe UI", 10)          # Texto general
_F_SMALL  = ("Segoe UI", 9)           # Labels pequeños
_F_BTN    = ("Segoe UI", 10, "bold")  # Botones principales
_F_CLOCK  = ("Segoe UI", 14, "bold")  # Reloj digital
_F_MONO   = ("Consolas", 9)           # Área de logs (fuente monoespaciada)

# Tema de color por defecto para widgets CustomTkinter (debe llamarse antes de crear widgets CTk)
ctk.set_default_color_theme("green")

_THEMES: dict = {
    "light": {
        "bg_main": "#F0F2F5", "bg_card": "#FFFFFF", "bg_top": "#E6E8EB", "bg_log": "#1E2328",
        "text": "#111B21", "text_muted": "#667781", "text_log": "#B2CFD8",
        "btn_p": "#075E54", "btn_p_h": "#25D366",
        "btn_s": "#546475", "btn_s_h": "#3D4F5C",
        "btn_t": "#128C7E", "btn_t_h": "#075E54",
        "tab_bg": "#FFFFFF", "tab_fg": "#111B21", "tab_sel": "#075E54", "tab_sel_fg": "#FFFFFF",
        "clock": "#075E54", "toggle_lbl": "\U0001f319 Oscuro",
    },
    "dark": {
        "bg_main": "#1A1A2E", "bg_card": "#16213E", "bg_top": "#0F3460", "bg_log": "#0D1117",
        "text": "#E0E0E0", "text_muted": "#A0AEC0", "text_log": "#7EE787",
        "btn_p": "#25D366", "btn_p_h": "#128C7E",
        "btn_s": "#4A5568", "btn_s_h": "#2D3748",
        "btn_t": "#4299E1", "btn_t_h": "#2B6CB0",
        "tab_bg": "#16213E", "tab_fg": "#E0E0E0", "tab_sel": "#25D366", "tab_sel_fg": "#000000",
        "clock": "#25D366", "toggle_lbl": "☀️ Claro",
    },
}


@dataclass
class MessageGroupWidgets:
    entries_contact: list[tk.Entry]
    entries_message: list[tk.Text]
    entries_date: list[DateEntry]
    listbox_hour: list[tk.Listbox]
    listbox_minute: list[tk.Listbox]
    listbox_ampm: list[tk.Listbox]
    send_vars: list[tk.BooleanVar]
    repeat_vars: list[ttk.Combobox]
    days_vars: list[list[tk.BooleanVar]]


def _theme_children(widget, th: dict, area: str = "main") -> None:
    """Aplica el tema recursivamente a los hijos de un widget segun el area (main o top)."""
    DONATE_COLORS = {"#f5a623", "#f5a623".upper(), "#D4891A", "#d4891a"}
    try:
        for child in widget.winfo_children():
            # Omitir widgets CustomTkinter — se auto-tematizan via ctk.set_appearance_mode()
            if type(child).__name__.startswith("CTk"):
                continue
            try:
                cls = child.winfo_class()
                bg = th["bg_top"] if area == "top" else th["bg_main"]
                if cls in ("Frame", "LabelFrame"):
                    child.configure(bg=bg)
                elif cls == "Label":
                    child.configure(bg=bg, fg=th["text"])
                elif cls == "Button":
                    try:
                        cbg = child.cget("bg")
                    except Exception:
                        cbg = ""
                    if cbg in DONATE_COLORS:
                        pass  # Preservar boton de donacion
                    elif area == "top":
                        child.configure(bg=th["btn_t"], fg="#FFFFFF",
                                        activebackground=th["btn_t_h"])
                    else:
                        child.configure(bg=th["btn_t"], fg="#FFFFFF",
                                        activebackground=th["btn_t_h"],
                                        relief=tk.FLAT, bd=0)
                elif cls == "Text":
                    child.configure(bg=th["bg_log"], fg=th["text_log"])
                elif cls == "Canvas":
                    child.configure(bg=th["bg_main"], highlightthickness=0)
                elif cls == "Listbox":
                    child.configure(bg=th["bg_card"], fg=th["text"],
                                    selectbackground=th["btn_p"],
                                    selectforeground="#FFFFFF")
                elif cls == "Entry":
                    child.configure(bg=th["bg_card"], fg=th["text"],
                                    insertbackground=th["text"])
            except Exception:
                pass
            _theme_children(child, th, area)
    except Exception:
        pass


class WhatsAppSchedulerApp:
    def __init__(self, config_path: str = "config.json") -> None:
        # --- Paso 1: cargar configuracion y logger (antes de crear ventana) ---
        self.config_store = ConfigStore(config_path)
        self.logger = LoggingService()

        # --- Inicializar traductor con el idioma guardado en config ---
        lang = str(self.config_store.get_global("language", "es"))
        self.i18n = Translator(lang)

        # --- Paso 2: crear ventana principal OCULTA mientras se muestra el splash ---
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(self.i18n.t("app_title"))
        self.root.report_callback_exception = self._report_callback_exception

        # Estado inicial de la aplicacion
        self.app_quitting = False
        self.clock_after_id = None
        self.scheduled_after_ids: list[str] = []
        self.scheduled_messages: list[dict] = []
        # Contador de generacion: se incrementa en cada cancel/reschedule para
        # invalidar callbacks pendientes de iteraciones anteriores. Previene
        # doble ejecucion de mensajes cuando after-timers expirados durante
        # hibernacion se disparan DESPUES de que _cancel_all_scheduled_messages
        # ya corrio (Tkinter no garantiza orden entre after(0,...) y timers vencidos).
        self._schedule_generation: int = 0

        self.status_label: tk.Label | None = None
        self.log_text: tk.Text | None = None
        self.clock_label: tk.Label | None = None

        self.browser_choice_var = tk.StringVar(value=self.config_store.get_browser_choice())
        self.browser_path_var = tk.StringVar()

        global_cfg = self.config_store.data.get("global", {})
        self.version = str(global_cfg.get("version", "8.2.1"))
        self._active_theme: str = str(self.config_store.get_global("theme", "light"))
        # Aplicar modo de apariencia a widgets CustomTkinter antes de crearlos
        ctk.set_appearance_mode("dark" if self._active_theme == "dark" else "light")

        # --- Paso 3: mostrar splash screen ---
        splash, pb_splash, lbl_splash = self._create_splash()

        def _step(pct: int, msg: str = "") -> None:
            self._splash_advance(pb_splash, lbl_splash, splash, pct, msg)

        _step(15, self.i18n.t("splash_configuring"))

        # --- Paso 4: configurar geometria de la ventana principal ---
        self._set_window_geometry()
        self.root.minsize(1000, 800)
        self.groups: dict[int, MessageGroupWidgets] = {}
        _step(30, self.i18n.t("splash_building"))

        # --- Paso 5: construir todos los widgets de la UI ---
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.event_generate("<<ExitRequested>>"))
        self.logger.set_ui_callback(self._append_log_line)
        _step(65, self.i18n.t("splash_engine"))

        # --- Paso 6: crear el backend (arranca hilo del BrowserWorker) ---
        self.backend = WhatsAppBackend(
            settings_provider=self._runtime_settings,
            log_fn=self.log_message,
            status_fn=self.update_status,
            sent_log_fn=self.logger.log_message_sent,
        )
        _step(85, self.i18n.t("splash_services"))

        # --- Paso 7: servicios finales ---
        self._refresh_browser_path_label()
        self.update_status(self.i18n.t("status_initialized"))
        self._start_clock()
        self._start_sleep_watchdog()
        _step(100, self.i18n.t("splash_ready"))

        # --- Paso 8: cerrar splash y mostrar la ventana principal ---
        splash.after(350, splash.destroy)
        self.root.after(420, self.root.deiconify)

        # Conectar WhatsApp Web en paralelo (no bloquea la GUI).
        # after(450) asegura que la ventana ya esta visible antes de iniciar la conexion,
        # evitando que bind_whatsapp_tab compita con el renderizado inicial de la ventana.
        self.root.after(450, lambda: threading.Thread(target=self.backend.bind_whatsapp_tab, daemon=True).start())

    # =========================================================================
    # SPLASH SCREEN
    # =========================================================================

    def _create_splash(self) -> tuple:
        """Crea y muestra el splash screen centrado en pantalla."""
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)

        W, H = 440, 230
        sw = splash.winfo_screenwidth()
        sh = splash.winfo_screenheight()
        x = sw // 2 - W // 2
        y = sh // 2 - H // 2
        splash.geometry(f"{W}x{H}+{x}+{y}")
        splash.configure(bg="#ffffff")

        frm = tk.Frame(splash, bg="#ffffff")
        frm.pack(expand=True, fill="both", padx=24, pady=18)

        tk.Label(
            frm,
            text=self.i18n.t("app_title"),
            font=("Helvetica", 13, "bold"),
            bg="#ffffff",
            fg="#075e54",
        ).pack(pady=(4, 2))

        tk.Label(
            frm,
            text=self.i18n.t("version_label", v=self.version),
            font=("Helvetica", 9),
            bg="#ffffff",
            fg="#aaaaaa",
        ).pack(pady=(0, 10))

        pb = ttk.Progressbar(frm, orient="horizontal", mode="determinate", length=370)
        pb.pack(pady=(0, 8))

        lbl_status = tk.Label(frm, text="Iniciando...", font=("Helvetica", 9), bg="#ffffff", fg="#555555")
        lbl_status.pack()

        splash.update()
        return splash, pb, lbl_status

    @staticmethod
    def _splash_advance(pb: ttk.Progressbar, lbl: tk.Label, splash: tk.Toplevel, target_pct: int, msg: str = "") -> None:
        """Anima la barra de progreso del splash de su valor actual hasta 'target_pct'."""
        current = int(pb["value"])
        for v in range(current, target_pct + 1):
            pb["value"] = v
            if v == target_pct and msg:
                lbl.config(text=msg)
            try:
                splash.update_idletasks()
            except Exception:
                break

    # =========================================================================

    def _report_callback_exception(self, exc, value, tb) -> None:
        if self.app_quitting:
            return
        import traceback
        traceback.print_exception(exc, value, tb)

    def _set_window_geometry(self) -> None:
        geometry = str(self.config_store.get_global("window_geometry", "1250x900"))
        base_geometry = geometry.split("+", 1)[0] if "+" in geometry else geometry
        state = str(self.config_store.get_global("window_state", "normal"))
        x = self.config_store.get_global("window_x")
        y = self.config_store.get_global("window_y")

        if x is not None and y is not None:
            try:
                self.root.geometry(f"{base_geometry}+{int(x)}+{int(y)}")
            except Exception:
                self.root.geometry(base_geometry)
        else:
            self.root.geometry(geometry)

        if state == "zoomed":
            try:
                self.root.state("zoomed")
            except Exception:
                pass

    def _ui_call(self, fn: Callable, *args, **kwargs) -> None:
        if self.app_quitting:
            return
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda: (None if self.app_quitting else fn(*args, **kwargs)))
            except tk.TclError:
                pass
        else:
            try:
                fn(*args, **kwargs)
            except tk.TclError:
                pass

    def _append_log_line(self, line: str) -> None:
        def _do() -> None:
            if self.log_text is not None and self.log_text.winfo_exists():
                self.log_text.insert(tk.END, f"{line}\n")
                self.log_text.see(tk.END)
            else:
                print(line)
        self._ui_call(_do)

    def log_message(self, message: str) -> None:
        self.logger.log_app(message)

    def update_status(self, text: str) -> None:
        def _do() -> None:
            if self.status_label is not None and self.status_label.winfo_exists():
                self.status_label.config(text=f"Estado: {text}")
        self._ui_call(_do)
        self.log_message(text)

    def _runtime_settings(self) -> BrowserRuntimeSettings:
        raw_extra_args = self.config_store.get_global(
            "browser_extra_args",
            self.config_store.get_global("opera_extra_args", []),
        )
        if isinstance(raw_extra_args, str):
            browser_extra_args = tuple(part for part in shlex.split(raw_extra_args) if part.strip())
        elif isinstance(raw_extra_args, (list, tuple)):
            browser_extra_args = tuple(str(item).strip() for item in raw_extra_args if str(item).strip())
        else:
            browser_extra_args = ()

        return BrowserRuntimeSettings(
            browser=self.browser_choice_var.get(),
            browser_paths=self.config_store.get_browser_paths(),
            remote_port=int(self.config_store.get_global("remote_debugging_port", 9222)),
            debug_port_timeout=int(self.config_store.get_global("debug_port_timeout", 60)),
            cdp_timeout=int(self.config_store.get_global("cdp_timeout", 90000)),
            cdp_retries=int(self.config_store.get_global("cdp_retries", 3)),
            extra_wait=int(self.config_store.get_global("extra_wait", 5)),
            keepalive_interval_sec=int(self.config_store.get_global("keepalive_interval_sec", 60)),
            relaunch_on_disconnect=self.config_store.get_global("relaunch_on_disconnect", True),
            user_data_dir=str(self.config_store.get_global("user_data_dir", "whats_profile")),
            browser_extra_args=browser_extra_args,
        )

    def _build_ui(self) -> None:
        # Construir la barra de menús antes de cualquier otro widget
        self._build_menubar()
        # Aplicar fondo del tema a la ventana principal
        self.root.configure(bg=_C_BG_MAIN)

        # Etiqueta de versión — discreta, esquina inferior izquierda
        version_label = tk.Label(
            self.root,
            text=self.i18n.t("version_label", v=self.version),
            font=_F_SMALL,
            bg=_C_BG_MAIN,
            fg=_C_TEXT_MUTED,
        )
        version_label.pack(side=tk.BOTTOM, pady=2)

        self._build_top_controls()

        # Reloj digital — grande y en verde primario para que destaque
        self.clock_label = tk.Label(
            self.root,
            font=_F_CLOCK,
            bg=_C_BG_MAIN,
            fg=_C_PRIMARY,
        )
        self.clock_label.pack(side=tk.BOTTOM, pady=4)

        # Barra de estado — fondo blanco, borde sutil, con padding lateral
        self.status_label = tk.Label(
            self.root,
            text=self.i18n.t("status_ready"),
            anchor="w",
            bg=_C_BG_CARD,
            fg=_C_TEXT,
            font=_F_BODY,
            padx=10,
            pady=5,
            relief=tk.FLAT,
        )
        self.status_label.pack(fill="x")

        # Marco central que contiene el canvas scrolleable con los grupos
        mid = tk.Frame(self.root, bg=_C_BG_MAIN)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._mid_frame = mid

        # Canvas sin borde visible y fondo del tema
        canvas = tk.Canvas(mid, bg=_C_BG_MAIN, highlightthickness=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll = tk.Scrollbar(mid, orient=tk.VERTICAL, command=canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=vscroll.set)

        # Frame interno del canvas con fondo del tema
        main_frame = tk.Frame(canvas, bg=_C_BG_MAIN)
        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        main_frame.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        # Área de logs con fondo oscuro para alto contraste (terminal style)
        log_frame = tk.Frame(self.root, bg=_C_LOG_BG)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False)
        self._log_frame = log_frame
        self.log_text = tk.Text(
            log_frame,
            height=8,
            bg=_C_LOG_BG,
            fg=_C_LOG_FG,
            font=_F_MONO,
            relief=tk.FLAT,
            insertbackground=_C_LOG_FG,
            padx=8,
            pady=4,
            selectbackground=_C_PRIMARY,
            selectforeground="#FFFFFF",
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Notebook con los 4 grupos de mensajes (tabs estilizados por _apply_theme)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._main_notebook = notebook

        for group_id in range(1, 5):
            # Cada pestaña con fondo del tema
            frame = tk.Frame(notebook, bg=_C_BG_MAIN)
            notebook.add(frame, text=self.i18n.t("group_tab", n=group_id))
            num_messages = int(self.config_store.get_global(f"num_messages_group{group_id}", 4))
            pre_config = self.config_store.get_group_messages(group_id)
            self.groups[group_id] = self._create_message_blocks(frame, num_messages, group_id, pre_config)

        # Botón principal: Programar mensajes — CTkButton con esquinas redondeadas
        btn_schedule = ctk.CTkButton(
            self.root,
            text=self.i18n.t("btn_schedule"),
            command=self.schedule_all_messages,
            fg_color=_C_PRIMARY,
            hover_color=_C_ACTION,
            text_color="#FFFFFF",
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
            corner_radius=8,
            height=42,
            width=230,
            cursor="hand2",
        )
        btn_schedule.pack(side=tk.TOP, pady=(8, 3))
        self._btn_schedule = btn_schedule

        # Botón secundario: Salir — tono gris oscuro, menos prominente
        btn_exit = ctk.CTkButton(
            self.root,
            text=self.i18n.t("btn_exit"),
            command=lambda: self.root.event_generate("<<ExitRequested>>"),
            fg_color=_C_EXIT,
            hover_color=_C_EXIT_H,
            text_color="#FFFFFF",
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
            corner_radius=8,
            height=42,
            width=230,
            cursor="hand2",
        )
        btn_exit.pack(side=tk.TOP, pady=(0, 8))
        self._btn_exit = btn_exit

        # Botón de donaciones "Cómprame una cerveza" — ámbar, esquinas redondeadas
        btn_donate = ctk.CTkButton(
            self.root,
            text=self.i18n.t("btn_donate"),
            command=lambda: webbrowser.open(_DONATE_URL),
            fg_color="#F5A623",
            hover_color="#D4891A",
            text_color="#FFFFFF",
            font=ctk.CTkFont("Segoe UI", 9),
            corner_radius=6,
            height=30,
            width=190,
            cursor="hand2",
        )
        btn_donate.pack(side=tk.BOTTOM, pady=(0, 4))

        self.root.bind_all("<Alt-r>", lambda _: self._reset_default_paths())
        self.root.bind_all("<Alt-g>", lambda _: self.save_messages_config())
        self.root.bind_all("<Alt-p>", lambda _: self.schedule_all_messages())
        self.root.bind_all("<Alt-s>", lambda _: self.root.event_generate("<<ExitRequested>>"))
        self.root.bind("<<ExitRequested>>", self._on_exit_requested)

        # Aplicar estilos ttk al final (notebook tabs, scrollbars, combobox)
        self._apply_theme()

    # =========================================================================
    # TEMA VISUAL
    # =========================================================================

    def _toggle_theme(self) -> None:
        """Alterna entre tema claro y oscuro, actualiza widgets tk y CTk, y guarda la preferencia."""
        new_theme = "dark" if self._active_theme == "light" else "light"
        # Actualizar modo de apariencia en CustomTkinter (afecta todos los CTkButton, CTkFrame, etc.)
        ctk.set_appearance_mode("dark" if new_theme == "dark" else "light")
        self._apply_theme(new_theme)

    def _apply_theme(self, theme_name: str | None = None) -> None:
        """Aplica el tema visual completo (light/dark) a todos los widgets de la aplicacion."""
        if theme_name is not None:
            self._active_theme = theme_name
            self.config_store.set_global("theme", theme_name)
        th = _THEMES.get(self._active_theme, _THEMES["light"])

        # Actualizar boton de tema con el label del nuevo estado
        if hasattr(self, "_theme_btn"):
            self._theme_btn.configure(text=th["toggle_lbl"],
                                      bg=th["btn_t"], activebackground=th["btn_t_h"])

        # Ventana raiz
        self.root.configure(bg=th["bg_main"])

        # Barra de estado
        if self.status_label:
            self.status_label.configure(bg=th["bg_card"], fg=th["text"])

        # Reloj
        if self.clock_label:
            self.clock_label.configure(bg=th["bg_main"], fg=th["clock"])

        # Area de logs
        if hasattr(self, "_log_frame"):
            self._log_frame.configure(bg=th["bg_log"])
        if self.log_text:
            self.log_text.configure(bg=th["bg_log"], fg=th["text_log"],
                                    insertbackground=th["text_log"],
                                    selectbackground=th["btn_p"])

        # Botones principales (CTkButton usa fg_color/hover_color en vez de bg/activebackground)
        if hasattr(self, "_btn_schedule"):
            self._btn_schedule.configure(fg_color=th["btn_p"], hover_color=th["btn_p_h"])
        if hasattr(self, "_btn_exit"):
            self._btn_exit.configure(fg_color=th["btn_s"], hover_color=th["btn_s_h"])

        # Barra superior y sus hijos
        if hasattr(self, "_top_frame"):
            self._top_frame.configure(bg=th["bg_top"])
            _theme_children(self._top_frame, th, area="top")

        # Frame central y canvas
        if hasattr(self, "_mid_frame"):
            self._mid_frame.configure(bg=th["bg_main"])
            _theme_children(self._mid_frame, th, area="main")

        # Tabs del Notebook y contenido de grupos de mensajes
        if hasattr(self, "_main_notebook"):
            for tab_frame in self._main_notebook.winfo_children():
                try:
                    tab_frame.configure(bg=th["bg_main"])
                except Exception:
                    pass
                _theme_children(tab_frame, th, area="main")

        # Estilos ttk: Notebook tabs, Scrollbar, Combobox
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=th["bg_main"], borderwidth=0)
        style.configure("TNotebook.Tab", background=th["tab_bg"], foreground=th["tab_fg"],
                        font=_F_BODY, padding=[16, 7])
        style.map("TNotebook.Tab",
                  background=[("selected", th["tab_sel"]), ("active", th["btn_t"])],
                  foreground=[("selected", th["tab_sel_fg"]), ("active", "#FFFFFF")])
        style.configure("TScrollbar", background=th["bg_main"],
                        troughcolor=th["bg_card"], relief="flat", arrowsize=13)
        style.map("TScrollbar", background=[("active", th["btn_t"])])
        style.configure("TCombobox", fieldbackground=th["bg_card"], foreground=th["text"],
                        background=th["bg_top"], font=_F_BODY,
                        selectbackground=th["btn_p"], selectforeground="#FFFFFF")
        style.map("TCombobox",
                  fieldbackground=[("readonly", th["bg_card"])],
                  foreground=[("readonly", th["text"])])

    # =========================================================================
    # BARRA DE MENÚS
    # =========================================================================

    def _build_menubar(self) -> None:
        """Construye la barra de menús principal de la aplicación."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # --- Menú Ayuda / Help / Ajuda (según idioma activo) ---
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=self.i18n.t("menu_help"), menu=help_menu)

        # Opción: Cómprame una cerveza (abre el link de donación en el navegador)
        help_menu.add_command(
            label=self.i18n.t("btn_donate"),
            command=lambda: webbrowser.open(_DONATE_URL),
        )
        help_menu.add_separator()

        # Opción: Acerca de / About / Sobre (abre el diálogo de información)
        help_menu.add_command(
            label=self.i18n.t("menu_about"),
            command=self._show_about,
        )

    def _show_about(self) -> None:
        """Muestra un diálogo modal con información de la aplicación (nombre, versión, autor, copyright)."""
        year = datetime.now().year

        # Crear ventana modal centrada sobre la ventana principal
        about_win = tk.Toplevel(self.root)
        about_win.title(self.i18n.t("menu_about"))
        about_win.resizable(False, False)
        about_win.transient(self.root)  # Hijo de la ventana principal
        about_win.grab_set()            # Bloquea interacción con la ventana principal

        # Calcular posición centrada sobre la ventana principal
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() // 2 - 175
        y = self.root.winfo_y() + self.root.winfo_height() // 2 - 115
        about_win.geometry(f"350x230+{x}+{y}")

        # Nombre de la aplicación (título grande)
        tk.Label(
            about_win,
            text="WhatsApp Message Sender",
            font=("Helvetica", 15, "bold"),
            pady=14,
        ).pack()

        # Versión actual
        tk.Label(
            about_win,
            text=f"Versión {self.version}",
            font=("Helvetica", 11),
        ).pack()

        # Autor
        tk.Label(
            about_win,
            text="\nCreado por Synyster Rick",
            font=("Helvetica", 10),
        ).pack()

        # Copyright año actual
        tk.Label(
            about_win,
            text=f"© {year} Derechos Reservados",
            font=("Helvetica", 10),
            fg="#555555",
        ).pack()

        # Botón para cerrar el diálogo
        tk.Button(
            about_win,
            text="OK",
            command=about_win.destroy,
            width=10,
            pady=4,
        ).pack(pady=14)

    def _build_top_controls(self) -> None:
        # Barra superior diferenciada visualmente del cuerpo principal
        top = tk.Frame(self.root, bg=_C_BG_TOP, padx=6, pady=6)
        top.pack(side=tk.TOP, fill=tk.X)
        self._top_frame = top

        # Label "Navegador:" con el color del tema
        tk.Label(top, text=self.i18n.t("lbl_browser"), bg=_C_BG_TOP, fg=_C_TEXT, font=_F_BODY).grid(row=0, column=0, padx=(4, 2))
        browser_combo = ttk.Combobox(
            top, values=list(SUPPORTED_BROWSERS), state="readonly", width=12,
            textvariable=self.browser_choice_var,
        )
        browser_combo.grid(row=0, column=1, padx=4)
        browser_combo.bind("<<ComboboxSelected>>", self._on_browser_select)

        # Configuración compartida de estilo para los botones de la barra superior
        _top_btn = dict(
            bg=_C_ACCENT, fg="#FFFFFF", font=_F_SMALL, relief=tk.FLAT,
            activebackground=_C_PRIMARY, activeforeground="#FFFFFF",
            cursor="hand2", padx=8, pady=4, bd=0,
        )
        # Botón: seleccionar ruta del navegador
        btn_path = tk.Button(top, text=self.i18n.t("btn_browser_path"), command=self._select_browser_path, **_top_btn)
        btn_path.grid(row=0, column=2, padx=4)

        # Botón: restaurar rutas por defecto
        btn_reset = tk.Button(top, text=self.i18n.t("btn_restore_paths"), command=self._reset_default_paths, **_top_btn)
        btn_reset.grid(row=0, column=3, padx=4)

        # Botón: guardar configuración
        btn_save = tk.Button(top, text=self.i18n.t("btn_save_config"), command=self.save_messages_config, **_top_btn)
        btn_save.grid(row=0, column=4, padx=4)

        # Selector de idioma con label discreto
        tk.Label(top, text=self.i18n.t("lbl_language"), bg=_C_BG_TOP, fg=_C_TEXT, font=_F_BODY).grid(row=0, column=5, padx=(14, 2))
        self.lang_var = tk.StringVar(value=self.i18n.lang)
        lang_combo = ttk.Combobox(
            top,
            values=Translator.supported_languages(),
            state="readonly",
            width=5,
            textvariable=self.lang_var,
        )
        lang_combo.grid(row=0, column=6, padx=4)
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_select)

        # Boton de cambio de tema (claro/oscuro)
        self._theme_btn = tk.Button(
            top,
            text=_THEMES[self._active_theme]["toggle_lbl"],
            command=self._toggle_theme,
            bg=_C_ACCENT, fg="#FFFFFF", font=_F_SMALL, relief=tk.FLAT,
            activebackground=_C_PRIMARY, activeforeground="#FFFFFF",
            cursor="hand2", padx=8, pady=4, bd=0,
        )
        self._theme_btn.grid(row=0, column=7, padx=(8, 4))

        # Etiqueta con la ruta actual del navegador (texto pequeño y discreto)
        self.browser_path_label = tk.Label(
            top, textvariable=self.browser_path_var, anchor="w",
            bg=_C_BG_TOP, fg=_C_TEXT_MUTED, font=_F_SMALL,
        )
        self.browser_path_label.grid(row=1, column=0, columnspan=7, sticky="we", padx=4, pady=(3, 0))

    def _on_language_select(self, _event=None) -> None:
        """Guarda la seleccion de idioma en config. El cambio aplica al reiniciar la app."""
        new_lang = self.lang_var.get()
        self.config_store.set_global("language", new_lang)
        self.update_status(self.i18n.t("lang_restart_notice"))

    def _on_browser_select(self, _event=None) -> None:
        selected = self.browser_choice_var.get()
        self.config_store.set_browser_choice(selected)
        self._refresh_browser_path_label()
        self.update_status(self.i18n.t("status_browser_sel", browser=selected))

    def _refresh_browser_path_label(self) -> None:
        browser = self.browser_choice_var.get()
        path = self.config_store.get_browser_path(browser)
        display_path = path or self.i18n.t("path_not_configured")
        self.browser_path_var.set(self.i18n.t("browser_path_display", browser=browser, path=display_path))

    def _select_browser_path(self) -> None:
        browser = self.browser_choice_var.get()
        selected = filedialog.askopenfilename(
            title=f"{self.i18n.t('btn_browser_path')} — {browser}",
            filetypes=[("Executable", "*.exe")],
        )
        if not selected:
            return
        self.config_store.set_browser_path(browser, selected)
        self._refresh_browser_path_label()
        self.update_status(self.i18n.t("status_path_updated", browser=browser))

    def _reset_default_paths(self) -> None:
        self.config_store.reset_default_browser_paths()
        self._refresh_browser_path_label()
        self.update_status(self.i18n.t("status_paths_restored"))

    @staticmethod
    def _safe_date_value(raw_value) -> datetime:
        if isinstance(raw_value, datetime):
            return raw_value
        if raw_value is None:
            return datetime.now()
        value = str(raw_value).strip()
        if not value:
            return datetime.now()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return datetime.now()

    @staticmethod
    def _bind_listbox_keyboard(listbox: tk.Listbox) -> None:
        def on_key(event):
            key = event.keysym
            if key in ("Up", "Down", "Prior", "Next", "Home", "End"):
                try:
                    current = listbox.curselection()
                    if not current:
                        listbox.selection_clear(0, tk.END)
                        listbox.selection_set(0)
                        listbox.see(0)
                        return "break"
                    idx = current[0]
                    if key == "Up" and idx > 0:
                        idx -= 1
                    elif key == "Down" and idx < listbox.size() - 1:
                        idx += 1
                    elif key == "Prior":
                        idx = max(0, idx - 5)
                    elif key == "Next":
                        idx = min(listbox.size() - 1, idx + 5)
                    elif key == "Home":
                        idx = 0
                    elif key == "End":
                        idx = listbox.size() - 1
                    listbox.selection_clear(0, tk.END)
                    listbox.selection_set(idx)
                    listbox.see(idx)
                    return "break"
                except Exception:
                    return "break"

            char = event.char
            if not char:
                return None
            token = char.strip()
            if not token:
                return None

            buffer = getattr(listbox, "_typebuf", "")
            last = getattr(listbox, "_typebuf_time", 0)
            now = time.time()
            if now - last > 0.9:
                buffer = ""
            buffer += token
            listbox._typebuf = buffer
            listbox._typebuf_time = now

            for idx in range(listbox.size()):
                value = str(listbox.get(idx))
                if value.lower().startswith(buffer.lower()):
                    listbox.selection_clear(0, tk.END)
                    listbox.selection_set(idx)
                    listbox.see(idx)
                    return "break"
            return None

        listbox.bind("<Key>", on_key)

    def _create_message_blocks(
        self,
        frame: tk.Frame,
        num_msgs: int,
        group_id: int,
        pre_config: list[dict] | None = None,
    ) -> MessageGroupWidgets:
        entries_contact: list[tk.Entry] = []
        entries_message: list[tk.Text] = []
        entries_date: list[DateEntry] = []
        listbox_hour: list[tk.Listbox] = []
        listbox_minute: list[tk.Listbox] = []
        listbox_ampm: list[tk.Listbox] = []
        send_vars: list[tk.BooleanVar] = []
        repeat_vars: list[ttk.Combobox] = []
        days_vars_all: list[list[tk.BooleanVar]] = []

        hours = [str(i) for i in range(1, 13)]
        minutes = [f"{i:02d}" for i in range(60)]
        ampm_options = ["AM", "PM"]
        repeat_display_options = self.i18n.repeat_options()
        day_names = self.i18n.days()

        for i in range(num_msgs):
            pre = pre_config[i] if pre_config and i < len(pre_config) else {}

            sub = tk.Frame(frame, relief=tk.GROOVE, borderwidth=2, takefocus=True)
            sub.grid(row=i // 2, column=i % 2, padx=10, pady=10, sticky="nsew")

            header = tk.Frame(sub, takefocus=True)
            header.pack(fill="x", padx=5, pady=2)
            tk.Label(
                header,
                text=self.i18n.t("msg_block_title", n=i + 1),
                font=("Helvetica", 14),
                takefocus=True,
            ).pack(side="left")
            var_send = tk.BooleanVar(value=bool(pre.get("send", False)))
            send_vars.append(var_send)
            tk.Checkbutton(header, text=self.i18n.t("chk_send"), variable=var_send, takefocus=True).pack(side="right")

            tk.Label(sub, text=self.i18n.t("lbl_contact"), takefocus=True).pack(anchor="w", padx=5)
            entry_contact = tk.Entry(sub, width=40, takefocus=True)
            entry_contact.insert(0, pre.get("contact", ""))
            entry_contact.pack(padx=5, pady=2)
            entries_contact.append(entry_contact)

            tk.Label(sub, text=self.i18n.t("lbl_message"), takefocus=True).pack(anchor="w", padx=5)
            text_message = tk.Text(sub, height=3, width=50, takefocus=True)
            text_message.insert(tk.END, pre.get("message", ""))
            text_message.pack(padx=5, pady=2)
            entries_message.append(text_message)

            tk.Label(sub, text=self.i18n.t("lbl_send_date"), takefocus=True).pack(anchor="w", padx=5)
            date_frame = tk.Frame(sub)
            date_frame.pack(padx=5, pady=2, fill=tk.X)
            date_entry = DateEntry(date_frame, date_pattern="yyyy-mm-dd", takefocus=True)
            safe_date = self._safe_date_value(pre.get("date"))
            try:
                date_entry.set_date(safe_date)
            except Exception:
                date_entry.set_date(datetime.now())
            date_entry.pack(side=tk.LEFT)
            tk.Button(
                date_frame,
                text=self.i18n.t("btn_set_today"),
                command=lambda de=date_entry: de.set_date(datetime.now()),
            ).pack(side=tk.LEFT, padx=5)
            entries_date.append(date_entry)

            time_frame = tk.Frame(sub, takefocus=True)
            time_frame.pack(padx=5, pady=2, fill=tk.X)

            tk.Label(time_frame, text=self.i18n.t("lbl_hour"), takefocus=True).grid(row=0, column=0, padx=5)
            frame_hour = tk.Frame(time_frame)
            frame_hour.grid(row=1, column=0, padx=5)
            lb_hour = tk.Listbox(frame_hour, height=4, exportselection=False, selectbackground="blue", takefocus=True)
            for hour in hours:
                lb_hour.insert(tk.END, hour)
            lb_hour.pack(side="left", fill="y")
            sb_hour = tk.Scrollbar(frame_hour, orient="vertical", command=lb_hour.yview)
            lb_hour.configure(yscrollcommand=sb_hour.set)
            sb_hour.pack(side="right", fill="y")
            listbox_hour.append(lb_hour)
            self._bind_listbox_keyboard(lb_hour)

            tk.Label(time_frame, text=self.i18n.t("lbl_minute"), takefocus=True).grid(row=0, column=1, padx=5)
            frame_min = tk.Frame(time_frame)
            frame_min.grid(row=1, column=1, padx=5)
            lb_min = tk.Listbox(frame_min, height=4, exportselection=False, selectbackground="blue", takefocus=True)
            for minute in minutes:
                lb_min.insert(tk.END, minute)
            lb_min.pack(side="left", fill="y")
            sb_min = tk.Scrollbar(frame_min, orient="vertical", command=lb_min.yview)
            lb_min.configure(yscrollcommand=sb_min.set)
            sb_min.pack(side="right", fill="y")
            listbox_minute.append(lb_min)
            self._bind_listbox_keyboard(lb_min)

            tk.Label(time_frame, text=self.i18n.t("lbl_ampm"), takefocus=True).grid(row=0, column=2, padx=5)
            lb_ampm = tk.Listbox(time_frame, height=2, exportselection=False, selectbackground="blue", takefocus=True)
            for ampm in ampm_options:
                lb_ampm.insert(tk.END, ampm)
            lb_ampm.grid(row=1, column=2, padx=5)
            listbox_ampm.append(lb_ampm)
            self._bind_listbox_keyboard(lb_ampm)

            if pre.get("hour", ""):
                try:
                    idx_hour = hours.index(str(pre["hour"]))
                    lb_hour.selection_set(idx_hour)
                    lb_hour.see(idx_hour)
                except Exception:
                    pass
            if pre.get("minute", "") != "":
                try:
                    idx_minute = minutes.index(str(pre["minute"]).zfill(2))
                    lb_min.selection_set(idx_minute)
                    lb_min.see(idx_minute)
                except Exception:
                    pass
            if pre.get("ampm", ""):
                try:
                    idx_ampm = ampm_options.index(str(pre["ampm"]).upper())
                    lb_ampm.selection_set(idx_ampm)
                    lb_ampm.see(idx_ampm)
                except Exception:
                    pass

            tk.Label(sub, text=self.i18n.t("lbl_repeat"), takefocus=True).pack(anchor="w", padx=5)
            combo_repeat = ttk.Combobox(sub, values=repeat_display_options, state="readonly", width=15)
            # Cargar el valor canónico guardado y convertirlo a etiqueta de pantalla
            canonical_repeat = pre.get("repeat", "Ninguno")
            combo_repeat.set(self.i18n.canonical_to_display(canonical_repeat))
            combo_repeat.pack(side=tk.LEFT, padx=5, pady=2)
            repeat_vars.append(combo_repeat)

            tk.Button(
                sub,
                text=self.i18n.t("btn_stop_repeat"),
                command=lambda grp=group_id, idx=i, cb=combo_repeat: self.stop_repetition(grp, idx, cb),
            ).pack(side=tk.LEFT, padx=5, pady=2)

            tk.Label(sub, text=self.i18n.t("lbl_days"), takefocus=True).pack(anchor="w", padx=5)
            days_frame = tk.Frame(sub)
            days_frame.pack(padx=5, pady=2, fill=tk.X)
            current_days_vars: list[tk.BooleanVar] = []
            pre_days = pre.get("days", [])
            for day_idx, day_name in enumerate(day_names):
                var = tk.BooleanVar(value=(day_idx in pre_days))
                tk.Checkbutton(days_frame, text=day_name, variable=var).pack(side=tk.LEFT)
                current_days_vars.append(var)
            days_vars_all.append(current_days_vars)

        return MessageGroupWidgets(
            entries_contact=entries_contact,
            entries_message=entries_message,
            entries_date=entries_date,
            listbox_hour=listbox_hour,
            listbox_minute=listbox_minute,
            listbox_ampm=listbox_ampm,
            send_vars=send_vars,
            repeat_vars=repeat_vars,
            days_vars=days_vars_all,
        )

    def stop_repetition(self, group: int, index: int, combobox: ttk.Combobox) -> None:
        # Mostrar etiqueta traducida de "sin repeticion"
        combobox.set(self.i18n.canonical_to_display("Ninguno"))
        for msg in self.scheduled_messages:
            if isinstance(msg, dict) and not msg.get("is_group"):
                if msg.get("group") == group and msg.get("index") == index:
                    msg["repeat"] = "Ninguno"
            for item in msg.get("items", []):
                if item.get("group") == group and item.get("index") == index:
                    item["repeat"] = "Ninguno"
        self.update_status(self.i18n.t("status_repeat_stopped", group=group, n=index + 1))

    @staticmethod
    def _add_months(source: datetime, months: int) -> datetime:
        """Suma 'months' meses a 'source' respetando los limites del mes destino."""
        month = source.month - 1 + months
        year = source.year + month // 12
        month = month % 12 + 1
        day = min(source.day, calendar.monthrange(year, month)[1])
        return datetime(year, month, day, source.hour, source.minute, source.second)

    @staticmethod
    def _advance_to_next_occurrence(dt: datetime, repeat: str, reference: datetime) -> datetime:
        """
        Dado un datetime 'dt' en el pasado, lo avanza al primer momento futuro
        segun el modo de repeticion indicado (valores canonicos en espanol).
        """
        from math import ceil

        if repeat == "Ninguno" or dt > reference:
            return dt

        if repeat == "Cada minuto":
            diff_sec = (reference - dt).total_seconds()
            minutes_needed = int(ceil(diff_sec / 60)) + 1
            return dt + timedelta(minutes=minutes_needed)

        elif repeat == "Cada hora":
            diff_sec = (reference - dt).total_seconds()
            hours_needed = int(ceil(diff_sec / 3600)) + 1
            return dt + timedelta(hours=hours_needed)

        elif repeat == "Diariamente":
            diff_days = (reference.date() - dt.date()).days + 1
            return dt + timedelta(days=diff_days)

        elif repeat == "Semanalmente":
            diff_days = (reference.date() - dt.date()).days + 1
            weeks_needed = int(ceil(diff_days / 7))
            return dt + timedelta(weeks=max(1, weeks_needed))

        elif repeat == "Mensualmente":
            result = dt
            while result <= reference:
                month = result.month % 12 + 1
                year = result.year + (1 if result.month == 12 else 0)
                day = min(result.day, calendar.monthrange(year, month)[1])
                result = result.replace(year=year, month=month, day=day)
            return result

        return dt

    def _schedule_message(self, msg: dict) -> None:
        # Para containers de grupo, sincronizar el datetime con el item mas proximo.
        # Solo se consideran items pendientes: items con repeat o con fecha futura.
        # Los items sin repeat con fecha pasada ya fueron enviados y no deben
        # adelantar la programacion del contenedor (evita disparo inmediato erroneo).
        if msg.get("is_group") and msg.get("items"):
            _now_ref = datetime.now()
            item_dts = [
                item["datetime"]
                for item in msg["items"]
                if isinstance(item.get("datetime"), datetime)
                and (item.get("repeat", "Ninguno") != "Ninguno" or item["datetime"] > _now_ref)
            ]
            if item_dts:
                msg["datetime"] = min(item_dts)

        target_dt = msg.get("datetime") if isinstance(msg.get("datetime"), datetime) else datetime.now() + timedelta(seconds=2)
        delay_ms = max(1000, int((target_dt - datetime.now()).total_seconds() * 1000))

        # Capturar la generacion actual: si _cancel_all_scheduled_messages incrementa
        # la generacion antes de que este callback se ejecute, el hilo no se lanza.
        gen = self._schedule_generation

        def _start() -> None:
            # Verificar que este callback siga vigente antes de lanzar el hilo.
            # Si la generacion cambio (reschedule o cancel posterior), ignorar.
            if not self.app_quitting and self._schedule_generation == gen:
                threading.Thread(target=self._process_scheduled_message, args=(msg,), daemon=True).start()

        try:
            after_id = self.root.after(delay_ms, _start)
            self.scheduled_after_ids.append(after_id)
        except (tk.TclError, RuntimeError):
            # RuntimeError: main thread is not in main loop — ocurre cuando _schedule_message
            # es llamado desde un hilo de fondo (p.ej. _retry_message_delivery desde Thread-N)
            # o cuando el event loop ya cerro. Se ignora para no crashear el hilo.
            pass

    def _cancel_all_scheduled_messages(self) -> None:
        # Incrementar la generacion invalida todos los callbacks pendientes que
        # aun no han disparado. Los que ya dispararon (pero aun no han lanzado
        # su hilo) verifican la generacion y se convierten en no-op.
        self._schedule_generation += 1
        for after_id in self.scheduled_after_ids:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        self.scheduled_after_ids.clear()

    def _schedule_messages_group(self, group_name: str, widgets: MessageGroupWidgets, group_id: int) -> list[dict]:
        msgs: list[dict] = []
        now = datetime.now()
        now_min = now.replace(second=0, microsecond=0)

        for idx in range(len(widgets.entries_contact)):
            if not widgets.send_vars[idx].get():
                continue

            contact = widgets.entries_contact[idx].get().strip()
            message_text = widgets.entries_message[idx].get("1.0", tk.END).strip()
            if not contact or not message_text:
                continue

            date_str = widgets.entries_date[idx].get()
            hour_sel = widgets.listbox_hour[idx].curselection()
            minute_sel = widgets.listbox_minute[idx].curselection()
            ampm_sel = widgets.listbox_ampm[idx].curselection()

            if not hour_sel or not minute_sel or not ampm_sel:
                self.update_status(self.i18n.t("status_no_time", n=idx + 1, group=group_name))
                return []

            hour_val = int(widgets.listbox_hour[idx].get(hour_sel[0]))
            minute_val = int(widgets.listbox_minute[idx].get(minute_sel[0]))
            ampm_val = widgets.listbox_ampm[idx].get(ampm_sel[0])

            if ampm_val.upper() == "PM" and hour_val != 12:
                hour_val += 12
            elif ampm_val.upper() == "AM" and hour_val == 12:
                hour_val = 0

            try:
                scheduled_date = datetime.strptime(date_str, "%Y-%m-%d")
                scheduled_datetime = scheduled_date.replace(hour=hour_val, minute=minute_val)
            except ValueError:
                self.update_status(self.i18n.t("status_bad_date", n=idx + 1, group=group_name))
                return []

            # Convertir el valor mostrado en el combobox al valor canónico (español) para
            # guardar internamente. Siempre se compara y almacena en canónico.
            repeat_display = widgets.repeat_vars[idx].get()
            repeat_value = self.i18n.display_to_canonical(repeat_display)
            if repeat_value not in CANONICAL_REPEAT_OPTIONS:
                repeat_value = "Ninguno"
            allowed_days = [day_index for day_index, var in enumerate(widgets.days_vars[idx]) if var.get()]

            if scheduled_datetime < now_min:
                if repeat_value == "Ninguno":
                    self.update_status(self.i18n.t("status_past_skip", n=idx + 1, group=group_name))
                    continue
                else:
                    scheduled_datetime = self._advance_to_next_occurrence(
                        scheduled_datetime, repeat_value, now_min
                    )
                    if scheduled_datetime < now_min:
                        self.update_status(self.i18n.t("status_past_skip", n=idx + 1, group=group_name))
                        continue
                    self.update_status(
                        self.i18n.t(
                            "status_past_reschedule",
                            n=idx + 1,
                            group=group_name,
                            repeat=repeat_value,
                            dt=scheduled_datetime.strftime("%Y-%m-%d %H:%M"),
                        )
                    )

            msgs.append(
                {
                    "group": group_id,
                    "index": idx,
                    "contact": contact,
                    "message": message_text,
                    "datetime": scheduled_datetime,
                    "sent": False,
                    "repeat": repeat_value,
                    "days": allowed_days,
                    "last_sent": None,
                }
            )

        return msgs

    def schedule_all_messages(self) -> None:
        self._cancel_all_scheduled_messages()
        self.scheduled_messages = []

        all_msgs: list[dict] = []
        for group_id in range(1, 5):
            group_msgs = self._schedule_messages_group(
                self.i18n.t("group_tab", n=group_id), self.groups[group_id], group_id
            )
            all_msgs.extend(group_msgs)

        grouped: dict[tuple[datetime, str], list[dict]] = {}
        for msg in all_msgs:
            key = (msg["datetime"], msg["contact"])
            grouped.setdefault(key, []).append(msg)

        for (scheduled_at, contact), items in grouped.items():
            self.scheduled_messages.append(
                {
                    "is_group": True,
                    "datetime": scheduled_at,
                    "contact": contact,
                    "items": items,
                }
            )

        for msg in self.scheduled_messages:
            self._schedule_message(msg)

        self.update_status(self.i18n.t("status_scheduled"))

    def _reprogram_repeat(self, msg: dict) -> None:
        repeat = msg.get("repeat")
        if repeat == "Cada minuto":
            msg["datetime"] = max(datetime.now() + timedelta(seconds=1), msg["datetime"] + timedelta(minutes=1))
            self._schedule_message(msg)
        elif repeat == "Cada hora":
            msg["datetime"] = max(datetime.now() + timedelta(seconds=1), msg["datetime"] + timedelta(hours=1))
            self._schedule_message(msg)
        elif repeat == "Diariamente":
            msg["datetime"] = max(datetime.now() + timedelta(seconds=1), msg["datetime"] + timedelta(days=1))
            self._schedule_message(msg)
        elif repeat == "Semanalmente":
            msg["datetime"] = max(datetime.now() + timedelta(seconds=1), msg["datetime"] + timedelta(weeks=1))
            self._schedule_message(msg)
        elif repeat == "Mensualmente":
            msg["datetime"] = max(datetime.now() + timedelta(seconds=1), self._add_months(msg["datetime"], 1))
            self._schedule_message(msg)

    def _retry_message_delivery(self, msg: dict, reason: str, delay_seconds: int = 45, max_attempts: int = 20) -> bool:
        retries = int(msg.get("_delivery_retries", 0) or 0)
        if retries >= max_attempts:
            self.update_status(self.i18n.t("status_exhausted", reason=reason, max=max_attempts))
            # FIX V8.5.0: mensajes con repeticion (o grupos con items repetitivos) no
            # deben abandonarse permanentemente al agotar retries. Los reiniciamos con
            # un cooldown de 5 min para no generar spam, luego el ciclo normal sigue.
            # Mensajes de un solo disparo (repeat==Ninguno, not is_group) se descartan.
            repeat = msg.get("repeat", "Ninguno")
            is_group = msg.get("is_group", False)
            has_repeating_items = is_group and any(
                item.get("repeat", "Ninguno") != "Ninguno"
                for item in (msg.get("items") or [])
            )
            if repeat not in (None, "Ninguno") or has_repeating_items:
                msg["_delivery_retries"] = 0
                cooldown_sec = 300  # 5 minutos antes de volver a intentar
                msg["datetime"] = datetime.now() + timedelta(seconds=cooldown_sec)
                self.log_message(
                    f"[RETRY] Reintentos agotados para '{msg.get('contact', '')}'. "
                    f"Reprogramando en {cooldown_sec}s (no se abandona por ser repetitivo)."
                )
                self._schedule_message(msg)
            return False
        msg["_delivery_retries"] = retries + 1
        msg["datetime"] = datetime.now() + timedelta(seconds=max(5, delay_seconds))
        self.update_status(
            self.i18n.t(
                "status_retry",
                reason=reason,
                n=msg["_delivery_retries"],
                max=max_attempts,
                secs=max(5, delay_seconds),
            )
        )
        self._schedule_message(msg)
        return True

    @staticmethod
    def _clear_delivery_retries(msg: dict) -> None:
        if "_delivery_retries" in msg:
            msg["_delivery_retries"] = 0

    def _process_scheduled_message(self, msg: dict) -> None:
        if not self.backend.bind_whatsapp_tab():
            self._retry_message_delivery(msg, "Error: no fue posible preparar WhatsApp")
            return

        now = datetime.now()

        if msg.get("is_group"):
            contact = msg["contact"]
            items = list(msg.get("items") or [])
            if not items:
                return

            runnable = []
            for item in items:
                days = item.get("days") or []
                if days and datetime.now().weekday() not in days:
                    delta = 1
                    while (datetime.now() + timedelta(days=delta)).weekday() not in days:
                        delta += 1
                    new_time = datetime.now() + timedelta(days=delta)
                    item["datetime"] = new_time
                    self.update_status(self.i18n.t("status_day_skip", new_time=new_time))
                    self._schedule_message(item)
                else:
                    # Saltar items sin repeticion que ya fueron enviados (tienen last_sent).
                    # Pueden aparecer en runnable tras hibernacion si el grupo fue
                    # reprogramado por otros items con repeticion. Evita reenvio duplicado.
                    if item.get("repeat", "Ninguno") == "Ninguno" and item.get("last_sent") is not None:
                        continue
                    item_dt = item.get("datetime")
                    if isinstance(item_dt, datetime) and item_dt > datetime.now() + timedelta(seconds=30):
                        self._schedule_message(item)
                    else:
                        runnable.append(item)

            if not runnable:
                return

            with self.backend._delivery_lock:
                if not self.backend.select_contact(contact):
                    self._retry_message_delivery(msg, self.i18n.t("status_chat_fail", contact=contact))
                    return

                for item in runnable:
                    if self.backend.send_message(item["message"], contact):
                        self.update_status(self.i18n.t("status_msg_sent", contact=contact))
                        item["last_sent"] = now
                        self._clear_delivery_retries(item)
                        self._reprogram_repeat(item)
                    else:
                        if not self._retry_message_delivery(item, self.i18n.t("status_send_err", contact=contact)):
                            self.update_status(self.i18n.t("status_send_err", contact=contact))
            return

        last_sent = msg.get("last_sent")
        repeat = msg.get("repeat")

        if repeat == "Cada minuto" and last_sent and (
            last_sent.year, last_sent.month, last_sent.day, last_sent.hour, last_sent.minute,
        ) == (now.year, now.month, now.day, now.hour, now.minute):
            msg["datetime"] = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            self._schedule_message(msg)
            return

        if repeat == "Cada hora" and last_sent and (
            last_sent.year, last_sent.month, last_sent.day, last_sent.hour,
        ) == (now.year, now.month, now.day, now.hour):
            msg["datetime"] = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            self._schedule_message(msg)
            return

        if repeat == "Diariamente" and last_sent and last_sent.date() == now.date():
            msg["datetime"] = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            self._schedule_message(msg)
            return

        if repeat == "Semanalmente" and last_sent and last_sent.isocalendar()[1] == now.isocalendar()[1] and last_sent.year == now.year:
            msg["datetime"] = msg["datetime"] + timedelta(weeks=1)
            self._schedule_message(msg)
            return

        if repeat == "Mensualmente" and last_sent and (last_sent.year, last_sent.month) == (now.year, now.month):
            msg["datetime"] = self._add_months(now.replace(second=0, microsecond=0), 1)
            self._schedule_message(msg)
            return

        if msg.get("days"):
            if datetime.now().weekday() not in msg["days"]:
                delta = 1
                while (datetime.now() + timedelta(days=delta)).weekday() not in msg["days"]:
                    delta += 1
                new_time = datetime.now() + timedelta(days=delta)
                msg["datetime"] = new_time
                self.update_status(self.i18n.t("status_day_skip", new_time=new_time))
                self._schedule_message(msg)
                return

        contact = msg["contact"]
        with self.backend._delivery_lock:
            if self.backend.select_contact(contact):
                if self.backend.send_message(msg["message"], contact):
                    self.update_status(self.i18n.t("status_msg_sent", contact=contact))
                    msg["last_sent"] = now
                    self._clear_delivery_retries(msg)
                    self._reprogram_repeat(msg)
                else:
                    if not self._retry_message_delivery(msg, self.i18n.t("status_send_err", contact=contact)):
                        self.update_status(self.i18n.t("status_send_err", contact=contact))
            else:
                if not self._retry_message_delivery(msg, self.i18n.t("status_chat_fail", contact=contact)):
                    self.update_status(self.i18n.t("status_chat_fail", contact=contact))

    def save_messages_config(self) -> None:
        for group_id in range(1, 5):
            widgets = self.groups[group_id]
            payload = []
            for idx in range(len(widgets.entries_contact)):
                days_selected = [day for day, var in enumerate(widgets.days_vars[idx]) if var.get()]
                # Convertir etiqueta de pantalla → valor canónico para guardar en config.json
                repeat_display = widgets.repeat_vars[idx].get()
                repeat_canonical = self.i18n.display_to_canonical(repeat_display)
                payload.append(
                    {
                        "contact": widgets.entries_contact[idx].get().strip(),
                        "message": widgets.entries_message[idx].get("1.0", tk.END).strip(),
                        "date": widgets.entries_date[idx].get(),
                        "hour": widgets.listbox_hour[idx].get(widgets.listbox_hour[idx].curselection()[0])
                        if widgets.listbox_hour[idx].curselection()
                        else "",
                        "minute": widgets.listbox_minute[idx].get(widgets.listbox_minute[idx].curselection()[0])
                        if widgets.listbox_minute[idx].curselection()
                        else "",
                        "ampm": widgets.listbox_ampm[idx].get(widgets.listbox_ampm[idx].curselection()[0])
                        if widgets.listbox_ampm[idx].curselection()
                        else "",
                        "repeat": repeat_canonical,
                        "send": bool(widgets.send_vars[idx].get()),
                        "days": days_selected,
                    }
                )
            self.config_store.set_group_messages(group_id, payload)

        self.config_store.set_browser_choice(self.browser_choice_var.get())
        self.update_status(self.i18n.t("status_config_saved"))

    def _start_clock(self) -> None:
        def _tick() -> None:
            if self.app_quitting:
                return
            if self.clock_label is not None and self.clock_label.winfo_exists():
                self.clock_label.config(text="Hora actual: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.clock_after_id = self.root.after(1000, _tick)
        _tick()

    def _start_sleep_watchdog(self) -> None:
        """
        Hilo daemon que detecta retorno de hibernacion del sistema.
        Duerme 4s en bucle; si entre dos iteraciones pasaron mas de 30s, el SO
        estuvo suspendido y se dispara la reconexion del navegador.
        """
        def _watchdog() -> None:
            last_check = time.time()
            while not self.app_quitting:
                time.sleep(4)
                now = time.time()
                elapsed = now - last_check
                last_check = now
                if elapsed > 30 and not self.app_quitting:
                    self._ui_call(self._on_system_wake, elapsed)

        threading.Thread(target=_watchdog, daemon=True, name="SleepWatchdog").start()

    def _on_system_wake(self, sleep_duration_sec: float) -> None:
        """Llamado en el hilo GUI cuando se detecta que el sistema deserto de hibernacion."""
        self.log_message(
            f"[WAKE] Sistema desperto tras ~{sleep_duration_sec:.0f}s de suspension. "
            "Iniciando reconexion del navegador..."
        )
        self.update_status(self.i18n.t("status_sleep_wake"))

        threading.Thread(
            target=self.backend.trigger_post_sleep_recovery,
            daemon=True,
            name="PostSleepRecovery",
        ).start()

        self._reschedule_past_due_repeating_messages()

    def _reschedule_past_due_repeating_messages(self) -> None:
        """
        Tras despertar de hibernacion, reprograma mensajes con repeticion que quedaron
        con datetime en el pasado para envio casi inmediato (ahora + 10s).
        Mensajes sin repeticion NO se reenvian (era intencional no enviarlos).

        FIX V8.2.1:
        - Se verifica last_sent para calcular si la proxima ocurrencia ya paso o no.
          Si el mensaje fue enviado hace poco y la proxima ocurrencia es futura, se
          respeta esa fecha en lugar de reprogramar para now+10s.
        - Solo items con repeat != "Ninguno" se reprograman; items sin repeat y con
          last_sent ya establecido se ignoran para evitar reenvios duplicados.
        """
        now = datetime.now()
        rescheduled = 0

        def _next_after_sent(last_sent: datetime, repeat: str) -> datetime | None:
            """Calcula la proxima ocurrencia de repeticion tras last_sent. None si no aplica."""
            if repeat == "Cada minuto":
                return last_sent + timedelta(minutes=1)
            if repeat == "Cada hora":
                return last_sent + timedelta(hours=1)
            if repeat == "Diariamente":
                return last_sent + timedelta(days=1)
            if repeat == "Semanalmente":
                return last_sent + timedelta(weeks=1)
            if repeat == "Mensualmente":
                return self._add_months(last_sent, 1)
            return None

        for msg in list(self.scheduled_messages):
            msg_dt = msg.get("datetime")
            if not isinstance(msg_dt, datetime) or msg_dt >= now:
                continue

            if msg.get("is_group"):
                group_rescheduled = 0
                for item in list(msg.get("items", [])):
                    repeat = item.get("repeat", "Ninguno")
                    item_dt = item.get("datetime")
                    if repeat == "Ninguno" or not isinstance(item_dt, datetime) or item_dt >= now:
                        continue
                    # Calcular proxima ocurrencia usando last_sent si esta disponible
                    last_sent = item.get("last_sent")
                    if last_sent and isinstance(last_sent, datetime):
                        next_dt = _next_after_sent(last_sent, repeat)
                        if next_dt and next_dt > now:
                            # La proxima ocurrencia es futura: respetar esa fecha
                            item["datetime"] = next_dt
                            rescheduled += 1
                            group_rescheduled += 1
                            continue
                    # La proxima ocurrencia ya paso: enviar casi de inmediato
                    item["datetime"] = now + timedelta(seconds=10)
                    rescheduled += 1
                    group_rescheduled += 1
                if group_rescheduled > 0:
                    msg["datetime"] = now + timedelta(seconds=10)
            else:
                repeat = msg.get("repeat", "Ninguno")
                if repeat == "Ninguno":
                    continue
                if not isinstance(msg_dt, datetime) or msg_dt >= now:
                    continue
                # Calcular proxima ocurrencia usando last_sent si esta disponible
                last_sent = msg.get("last_sent")
                if last_sent and isinstance(last_sent, datetime):
                    next_dt = _next_after_sent(last_sent, repeat)
                    if next_dt and next_dt > now:
                        msg["datetime"] = next_dt
                        rescheduled += 1
                        continue
                msg["datetime"] = now + timedelta(seconds=10)
                rescheduled += 1

        if rescheduled > 0:
            self.log_message(self.i18n.t("status_wake_rescheduled", n=rescheduled))
            self._cancel_all_scheduled_messages()
            for msg in list(self.scheduled_messages):
                self._schedule_message(msg)

    def _save_window_placement(self) -> None:
        try:
            state = self.root.state()
            self.config_store.set_global("window_state", "zoomed" if state == "zoomed" else "normal")
            self.root.update_idletasks()
            self.config_store.set_global("window_geometry", self.root.geometry())
            if state == "normal":
                self.config_store.set_global("window_x", self.root.winfo_x())
                self.config_store.set_global("window_y", self.root.winfo_y())
        except Exception:
            pass

    def _on_exit_requested(self, _event=None) -> None:
        if self.app_quitting:
            return
        self.app_quitting = True

        try:
            if self.clock_after_id is not None:
                self.root.after_cancel(self.clock_after_id)
                self.clock_after_id = None
        except Exception:
            pass

        self._cancel_all_scheduled_messages()
        self._save_window_placement()

        def force_close_ui() -> None:
            try:
                self.root.quit()
            except Exception:
                pass
            try:
                self.root.destroy()
            except Exception:
                pass

        try:
            self.root.after(0, force_close_ui)
        except Exception:
            force_close_ui()

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            self.backend.shutdown(timeout_sec=1.0)
            self.logger.close()


def main() -> None:
    app = WhatsAppSchedulerApp()
    app.run()
