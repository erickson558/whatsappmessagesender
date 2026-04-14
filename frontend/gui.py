from __future__ import annotations

import calendar
import shlex
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timedelta
from tkinter import filedialog, ttk
from typing import Callable

from tkcalendar import DateEntry

from backend.browser_worker import BrowserRuntimeSettings
from backend.config_store import ConfigStore, SUPPORTED_BROWSERS
from backend.logging_service import LoggingService
from backend.whatsapp_backend import WhatsAppBackend


DAY_NAMES = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
REPEAT_OPTIONS = ["Ninguno", "Cada minuto", "Cada hora", "Diariamente", "Semanalmente", "Mensualmente"]


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


class WhatsAppSchedulerApp:
    def __init__(self, config_path: str = "config.json") -> None:
        # --- Paso 1: cargar configuracion y logger (antes de crear ventana) ---
        self.config_store = ConfigStore(config_path)
        self.logger = LoggingService()

        # --- Paso 2: crear ventana principal OCULTA mientras se muestra el splash ---
        self.root = tk.Tk()
        self.root.withdraw()  # Ocultar hasta que el splash termine
        self.root.title("Programador de Mensajes WhatsApp")
        self.root.report_callback_exception = self._report_callback_exception

        # Estado inicial de la aplicacion
        self.app_quitting = False
        self.clock_after_id = None
        self.scheduled_after_ids: list[str] = []
        self.scheduled_messages: list[dict] = []

        self.status_label: tk.Label | None = None
        self.log_text: tk.Text | None = None
        self.clock_label: tk.Label | None = None

        self.browser_choice_var = tk.StringVar(value=self.config_store.get_browser_choice())
        self.browser_path_var = tk.StringVar()

        global_cfg = self.config_store.data.get("global", {})
        self.version = str(global_cfg.get("version", "8.1.4"))

        # --- Paso 3: mostrar splash screen ---
        splash, pb_splash, lbl_splash = self._create_splash()

        def _step(pct: int, msg: str = "") -> None:
            """Avanza la barra del splash suavemente hasta 'pct' y actualiza el texto."""
            self._splash_advance(pb_splash, lbl_splash, splash, pct, msg)

        _step(15, "Configurando ventana...")

        # --- Paso 4: configurar geometria de la ventana principal ---
        self._set_window_geometry()
        self.root.minsize(1000, 800)
        self.groups: dict[int, MessageGroupWidgets] = {}
        _step(30, "Construyendo interfaz grafica...")

        # --- Paso 5: construir todos los widgets de la UI (operacion mas pesada) ---
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.root.event_generate("<<ExitRequested>>"))
        self.logger.set_ui_callback(self._append_log_line)
        _step(65, "Iniciando motor de WhatsApp...")

        # --- Paso 6: crear el backend (arranca hilo del BrowserWorker) ---
        self.backend = WhatsAppBackend(
            settings_provider=self._runtime_settings,
            log_fn=self.log_message,
            status_fn=self.update_status,
            sent_log_fn=self.logger.log_message_sent,
        )
        _step(85, "Arrancando servicios internos...")

        # --- Paso 7: servicios finales ---
        self._refresh_browser_path_label()
        self.update_status("Aplicacion inicializada")
        self._start_clock()
        # Arrancar el vigilante de hibernacion del sistema (hilo daemon)
        self._start_sleep_watchdog()
        _step(100, "Listo!")

        # --- Paso 8: cerrar splash y mostrar la ventana principal ---
        # Destruir el splash primero (350ms) y luego mostrar la ventana principal (420ms)
        # El escalonamiento garantiza que el splash desaparezca antes de que la GUI aparezca,
        # evitando parpadeo visual o solapamiento entre ambas ventanas.
        splash.after(350, splash.destroy)
        self.root.after(420, self.root.deiconify)

        # Conectar WhatsApp Web en paralelo (no bloquea la GUI)
        threading.Thread(target=self.backend.bind_whatsapp_tab, daemon=True).start()

    # =========================================================================
    # SPLASH SCREEN
    # =========================================================================

    def _create_splash(self) -> tuple:
        """
        Crea y muestra la ventana de bienvenida (splash screen) centrada en pantalla.
        Es un Toplevel sin bordes que aparece mientras la app se inicializa.
        Retorna (splash_window, progressbar, label_status) para ser controlados
        desde __init__ a medida que avanzan las etapas de carga.
        """
        splash = tk.Toplevel(self.root)
        splash.overrideredirect(True)          # Sin barra de titulo ni botones
        splash.attributes("-topmost", True)    # Siempre visible sobre otras ventanas

        W, H = 440, 230
        sw = splash.winfo_screenwidth()
        sh = splash.winfo_screenheight()
        x = sw // 2 - W // 2
        y = sh // 2 - H // 2
        splash.geometry(f"{W}x{H}+{x}+{y}")
        splash.configure(bg="#ffffff")

        # Marco interior con padding
        frm = tk.Frame(splash, bg="#ffffff")
        frm.pack(expand=True, fill="both", padx=24, pady=18)

        # Titulo principal (color verde WhatsApp)
        tk.Label(
            frm,
            text="Programador de Mensajes WhatsApp",
            font=("Helvetica", 13, "bold"),
            bg="#ffffff",
            fg="#075e54",
        ).pack(pady=(4, 2))

        # Subtitulo con numero de version
        tk.Label(
            frm,
            text=f"Version {self.version}",
            font=("Helvetica", 9),
            bg="#ffffff",
            fg="#aaaaaa",
        ).pack(pady=(0, 10))

        # Barra de progreso determinada (se avanza manualmente)
        pb = ttk.Progressbar(
            frm,
            orient="horizontal",
            mode="determinate",
            length=370,
        )
        pb.pack(pady=(0, 8))

        # Etiqueta de estado que cambia en cada etapa
        lbl_status = tk.Label(
            frm,
            text="Iniciando...",
            font=("Helvetica", 9),
            bg="#ffffff",
            fg="#555555",
        )
        lbl_status.pack()

        # Forzar renderizado inicial antes de continuar
        splash.update()
        return splash, pb, lbl_status

    @staticmethod
    def _splash_advance(
        pb: ttk.Progressbar,
        lbl: tk.Label,
        splash: tk.Toplevel,
        target_pct: int,
        msg: str = "",
    ) -> None:
        """
        Anima la barra de progreso del splash desde su valor actual hasta 'target_pct'.
        Cada paso incrementa 1% con una pausa de 8ms para dar sensacion de suavidad.
        Al llegar al final actualiza el texto de estado con 'msg'.
        """
        current = int(pb["value"])
        for v in range(current, target_pct + 1):
            pb["value"] = v
            # Actualizar el texto solo al llegar al objetivo
            if v == target_pct and msg:
                lbl.config(text=msg)
            try:
                splash.update_idletasks()
            except Exception:
                break
            time.sleep(0.008)  # 8ms por paso → ~0.6s para 75 pasos

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
        version_label = tk.Label(self.root, text=f"Version: {self.version}", font=("Helvetica", 10))
        version_label.pack(side=tk.BOTTOM, pady=2)

        self._build_top_controls()

        self.clock_label = tk.Label(self.root, font=("Helvetica", 12))
        self.clock_label.pack(side=tk.BOTTOM, pady=5)

        self.status_label = tk.Label(self.root, text="Estado: listo", anchor="w")
        self.status_label.pack(fill="x")

        mid = tk.Frame(self.root)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(mid)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll = tk.Scrollbar(mid, orient=tk.VERTICAL, command=canvas.yview)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=vscroll.set)

        main_frame = tk.Frame(canvas)
        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        main_frame.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))

        log_frame = tk.Frame(self.root)
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False)
        self.log_text = tk.Text(log_frame, height=10)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        notebook = ttk.Notebook(main_frame)
        notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        for group_id in range(1, 5):
            frame = tk.Frame(notebook)
            notebook.add(frame, text=f"Grupo {group_id}")
            num_messages = int(self.config_store.get_global(f"num_messages_group{group_id}", 4))
            pre_config = self.config_store.get_group_messages(group_id)
            self.groups[group_id] = self._create_message_blocks(frame, num_messages, group_id, pre_config)

        btn_schedule = tk.Button(self.root, text="Programar mensajes", command=self.schedule_all_messages, underline=10)
        btn_schedule.pack(side=tk.TOP, pady=5)
        btn_exit = tk.Button(self.root, text="Salir", command=lambda: self.root.event_generate("<<ExitRequested>>"), underline=0)
        btn_exit.pack(side=tk.TOP, pady=5)

        self.root.bind_all("<Alt-r>", lambda _: self._reset_default_paths())
        self.root.bind_all("<Alt-g>", lambda _: self.save_messages_config())
        self.root.bind_all("<Alt-p>", lambda _: self.schedule_all_messages())
        self.root.bind_all("<Alt-s>", lambda _: self.root.event_generate("<<ExitRequested>>"))
        self.root.bind("<<ExitRequested>>", self._on_exit_requested)

    def _build_top_controls(self) -> None:
        top = tk.Frame(self.root)
        top.pack(side=tk.TOP, fill=tk.X, pady=5)

        tk.Label(top, text="Navegador:").grid(row=0, column=0, padx=5)
        browser_combo = ttk.Combobox(top, values=list(SUPPORTED_BROWSERS), state="readonly", width=12, textvariable=self.browser_choice_var)
        browser_combo.grid(row=0, column=1, padx=5)
        browser_combo.bind("<<ComboboxSelected>>", self._on_browser_select)

        btn_path = tk.Button(top, text="Ruta navegador", command=self._select_browser_path)
        btn_path.grid(row=0, column=2, padx=5)

        btn_reset = tk.Button(top, text="Restaurar rutas", command=self._reset_default_paths)
        btn_reset.grid(row=0, column=3, padx=5)

        btn_save = tk.Button(top, text="Guardar configuracion", command=self.save_messages_config)
        btn_save.grid(row=0, column=4, padx=5)

        self.browser_path_label = tk.Label(top, textvariable=self.browser_path_var, anchor="w")
        self.browser_path_label.grid(row=1, column=0, columnspan=5, sticky="we", padx=5, pady=(4, 0))

    def _on_browser_select(self, _event=None) -> None:
        selected = self.browser_choice_var.get()
        self.config_store.set_browser_choice(selected)
        self._refresh_browser_path_label()
        self.update_status(f"Navegador seleccionado: {selected}")

    def _refresh_browser_path_label(self) -> None:
        browser = self.browser_choice_var.get()
        path = self.config_store.get_browser_path(browser)
        self.browser_path_var.set(f"Ruta {browser}: {path or '(sin configurar)'}")

    def _select_browser_path(self) -> None:
        browser = self.browser_choice_var.get()
        selected = filedialog.askopenfilename(title=f"Seleccionar ejecutable de {browser}", filetypes=[("Executable", "*.exe")])
        if not selected:
            return
        self.config_store.set_browser_path(browser, selected)
        self._refresh_browser_path_label()
        self.update_status(f"Ruta de {browser} actualizada")

    def _reset_default_paths(self) -> None:
        self.config_store.reset_default_browser_paths()
        self._refresh_browser_path_label()
        self.update_status("Rutas de navegadores restauradas a valores por defecto")

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

        for i in range(num_msgs):
            pre = pre_config[i] if pre_config and i < len(pre_config) else {}

            sub = tk.Frame(frame, relief=tk.GROOVE, borderwidth=2, takefocus=True)
            sub.grid(row=i // 2, column=i % 2, padx=10, pady=10, sticky="nsew")

            header = tk.Frame(sub, takefocus=True)
            header.pack(fill="x", padx=5, pady=2)
            tk.Label(header, text=f"Mensaje {i + 1}", font=("Helvetica", 14), takefocus=True).pack(side="left")
            var_send = tk.BooleanVar(value=bool(pre.get("send", False)))
            send_vars.append(var_send)
            tk.Checkbutton(header, text="Enviar", variable=var_send, takefocus=True).pack(side="right")

            tk.Label(sub, text="Contacto:", takefocus=True).pack(anchor="w", padx=5)
            entry_contact = tk.Entry(sub, width=40, takefocus=True)
            entry_contact.insert(0, pre.get("contact", ""))
            entry_contact.pack(padx=5, pady=2)
            entries_contact.append(entry_contact)

            tk.Label(sub, text="Mensaje:", takefocus=True).pack(anchor="w", padx=5)
            text_message = tk.Text(sub, height=3, width=50, takefocus=True)
            text_message.insert(tk.END, pre.get("message", ""))
            text_message.pack(padx=5, pady=2)
            entries_message.append(text_message)

            tk.Label(sub, text="Fecha de envio:", takefocus=True).pack(anchor="w", padx=5)
            date_frame = tk.Frame(sub)
            date_frame.pack(padx=5, pady=2, fill=tk.X)
            date_entry = DateEntry(date_frame, date_pattern="yyyy-mm-dd", takefocus=True)
            safe_date = self._safe_date_value(pre.get("date"))
            try:
                date_entry.set_date(safe_date)
            except Exception:
                date_entry.set_date(datetime.now())
            date_entry.pack(side=tk.LEFT)
            tk.Button(date_frame, text="Set hoy", command=lambda de=date_entry: de.set_date(datetime.now())).pack(side=tk.LEFT, padx=5)
            entries_date.append(date_entry)

            time_frame = tk.Frame(sub, takefocus=True)
            time_frame.pack(padx=5, pady=2, fill=tk.X)

            tk.Label(time_frame, text="Hora:", takefocus=True).grid(row=0, column=0, padx=5)
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

            tk.Label(time_frame, text="Minuto:", takefocus=True).grid(row=0, column=1, padx=5)
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

            tk.Label(time_frame, text="AM/PM:", takefocus=True).grid(row=0, column=2, padx=5)
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

            tk.Label(sub, text="Repetir:", takefocus=True).pack(anchor="w", padx=5)
            combo_repeat = ttk.Combobox(sub, values=REPEAT_OPTIONS, state="readonly", width=15)
            combo_repeat.set(pre.get("repeat", "Ninguno"))
            combo_repeat.pack(side=tk.LEFT, padx=5, pady=2)
            repeat_vars.append(combo_repeat)

            tk.Button(
                sub,
                text="Detener repeticion",
                command=lambda grp=group_id, idx=i, cb=combo_repeat: self.stop_repetition(grp, idx, cb),
            ).pack(side=tk.LEFT, padx=5, pady=2)

            tk.Label(sub, text="Dias:", takefocus=True).pack(anchor="w", padx=5)
            days_frame = tk.Frame(sub)
            days_frame.pack(padx=5, pady=2, fill=tk.X)
            current_days_vars: list[tk.BooleanVar] = []
            pre_days = pre.get("days", [])
            for day_idx, day_name in enumerate(DAY_NAMES):
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
        combobox.set("Ninguno")
        for msg in self.scheduled_messages:
            if isinstance(msg, dict) and not msg.get("is_group"):
                if msg.get("group") == group and msg.get("index") == index:
                    msg["repeat"] = "Ninguno"
            for item in msg.get("items", []):
                if item.get("group") == group and item.get("index") == index:
                    item["repeat"] = "Ninguno"
        self.update_status(f"Repeticion detenida para Grupo {group}, bloque {index + 1}")

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
        segun el modo de repeticion indicado. Usado al reprogramar mensajes
        despues de hibernacion o tras re-abrir la programacion.
        Si 'repeat' es 'Ninguno', retorna 'dt' sin modificar.
        """
        from math import ceil

        if repeat == "Ninguno" or dt > reference:
            return dt

        if repeat == "Cada minuto":
            # Calcular cuantos minutos hay que avanzar para quedar en el futuro
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
            # Avanzar mes a mes hasta pasar 'reference'
            result = dt
            while result <= reference:
                month = result.month % 12 + 1
                year = result.year + (1 if result.month == 12 else 0)
                day = min(result.day, calendar.monthrange(year, month)[1])
                result = result.replace(year=year, month=month, day=day)
            return result

        return dt

    def _schedule_message(self, msg: dict) -> None:
        # Fix V8.1.4: para containers de grupo, sincronizar el datetime del container
        # al item mas proximo. Sin esto, containers con datetime en el pasado
        # se disparan en 1s (max(1000, negative_ms)=1000) aunque los items sean futuros,
        # causando envios prematuros tras hibernacion.
        if msg.get("is_group") and msg.get("items"):
            item_dts = [
                item["datetime"]
                for item in msg["items"]
                if isinstance(item.get("datetime"), datetime)
            ]
            if item_dts:
                # Alinear el container con el item mas proximo pendiente
                msg["datetime"] = min(item_dts)

        target_dt = msg.get("datetime") if isinstance(msg.get("datetime"), datetime) else datetime.now() + timedelta(seconds=2)
        delay_ms = max(1000, int((target_dt - datetime.now()).total_seconds() * 1000))

        def _start() -> None:
            if not self.app_quitting:
                threading.Thread(target=self._process_scheduled_message, args=(msg,), daemon=True).start()

        try:
            after_id = self.root.after(delay_ms, _start)
            self.scheduled_after_ids.append(after_id)
        except tk.TclError:
            pass

    def _cancel_all_scheduled_messages(self) -> None:
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
                self.update_status(f"Error: seleccione hora/minuto/AM-PM para mensaje {idx + 1} del {group_name}")
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
                self.update_status(f"Error: fecha/hora invalida en mensaje {idx + 1} del {group_name}")
                return []

            # IMPORTANTE: leer repeat_value y allowed_days ANTES del bloque de fecha
            # para que esten disponibles tanto en la logica de avance como en el dict final.
            repeat_value = widgets.repeat_vars[idx].get()
            repeat_value = repeat_value if repeat_value in REPEAT_OPTIONS else "Ninguno"
            allowed_days = [day_index for day_index, var in enumerate(widgets.days_vars[idx]) if var.get()]

            if scheduled_datetime < now_min:
                if repeat_value == "Ninguno":
                    # Sin repeticion: un mensaje en el pasado no se puede enviar ya
                    self.update_status(f"Mensaje {idx + 1} del {group_name} esta en el pasado y no se programa")
                    continue
                else:
                    # Con repeticion: avanzar al proximo ciclo futuro en lugar de descartar
                    scheduled_datetime = self._advance_to_next_occurrence(
                        scheduled_datetime, repeat_value, now_min
                    )
                    if scheduled_datetime < now_min:
                        # Fallo el calculo: descartar de todas formas
                        self.update_status(f"Mensaje {idx + 1} del {group_name} esta en el pasado y no se programa")
                        continue
                    self.update_status(
                        f"Mensaje {idx + 1} del {group_name}: fecha pasada con repeticion '{repeat_value}'. "
                        f"Reprogramado para {scheduled_datetime.strftime('%Y-%m-%d %H:%M')}"
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
            group_msgs = self._schedule_messages_group(f"Grupo {group_id}", self.groups[group_id], group_id)
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

        self.update_status("Mensajes programados")

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
            self.update_status(f"{reason}. Se agotaron reintentos ({max_attempts}).")
            return False
        msg["_delivery_retries"] = retries + 1
        msg["datetime"] = datetime.now() + timedelta(seconds=max(5, delay_seconds))
        self.update_status(
            f"{reason}. Reintento {msg['_delivery_retries']}/{max_attempts} en {max(5, delay_seconds)} segundos."
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
                    # Dia no permitido: reprogramar al proximo dia habilitado
                    delta = 1
                    while (datetime.now() + timedelta(days=delta)).weekday() not in days:
                        delta += 1
                    new_time = datetime.now() + timedelta(days=delta)
                    item["datetime"] = new_time
                    self.update_status(f"Hoy no es dia permitido. Reprogramado para {new_time}")
                    self._schedule_message(item)
                else:
                    # Fix V8.1.4: verificar si el item ya es debido (tolerancia 30s).
                    # Necesario cuando items de un grupo tienen repeat distinto y sus
                    # datetimes divergen tras _reprogram_repeat. El container se dispara
                    # al datetime del item mas proximo, pero items futuros no deben enviarse.
                    item_dt = item.get("datetime")
                    if isinstance(item_dt, datetime) and item_dt > datetime.now() + timedelta(seconds=30):
                        # Item aun no es debido: reprogramar standalone para su hora exacta
                        self._schedule_message(item)
                    else:
                        runnable.append(item)

            if not runnable:
                return

            # Bug fix V8.1.3: adquirir _delivery_lock antes de select+send para serializar
            # hilos concurrentes y evitar que _selected_contact sea sobreescrito entre llamadas.
            # El contacto se pasa explicitamente a send_message en lugar de depender del
            # estado compartido self.backend._selected_contact.
            with self.backend._delivery_lock:
                if not self.backend.select_contact(contact):
                    self._retry_message_delivery(msg, f"No se pudo abrir chat con {contact}")
                    return

                for item in runnable:
                    if self.backend.send_message(item["message"], contact):
                        self.update_status(f"Mensaje enviado a {contact}")
                        item["last_sent"] = now
                        self._clear_delivery_retries(item)
                        self._reprogram_repeat(item)
                    else:
                        if not self._retry_message_delivery(item, f"Error enviando mensaje a {contact}"):
                            self.update_status(f"Error enviando mensaje a {contact}")
            return

        last_sent = msg.get("last_sent")
        repeat = msg.get("repeat")

        if repeat == "Cada minuto" and last_sent and (
            last_sent.year,
            last_sent.month,
            last_sent.day,
            last_sent.hour,
            last_sent.minute,
        ) == (now.year, now.month, now.day, now.hour, now.minute):
            msg["datetime"] = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            self._schedule_message(msg)
            return

        if repeat == "Cada hora" and last_sent and (
            last_sent.year,
            last_sent.month,
            last_sent.day,
            last_sent.hour,
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
                self.update_status(f"Hoy no es dia permitido. Reprogramado para {new_time}")
                self._schedule_message(msg)
                return

        contact = msg["contact"]
        # Bug fix V8.1.3: mismo lock que el path de grupos para serializar select+send.
        with self.backend._delivery_lock:
            if self.backend.select_contact(contact):
                if self.backend.send_message(msg["message"], contact):
                    self.update_status(f"Mensaje enviado a {contact}")
                    msg["last_sent"] = now
                    self._clear_delivery_retries(msg)
                    self._reprogram_repeat(msg)
                else:
                    if not self._retry_message_delivery(msg, f"Error enviando mensaje a {contact}"):
                        self.update_status(f"Error enviando mensaje a {contact}")
            else:
                if not self._retry_message_delivery(msg, f"No se pudo abrir chat con {contact}"):
                    self.update_status(f"No se pudo abrir chat con {contact}")

    def save_messages_config(self) -> None:
        for group_id in range(1, 5):
            widgets = self.groups[group_id]
            payload = []
            for idx in range(len(widgets.entries_contact)):
                days_selected = [day for day, var in enumerate(widgets.days_vars[idx]) if var.get()]
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
                        "repeat": widgets.repeat_vars[idx].get(),
                        "send": bool(widgets.send_vars[idx].get()),
                        "days": days_selected,
                    }
                )
            self.config_store.set_group_messages(group_id, payload)

        self.config_store.set_browser_choice(self.browser_choice_var.get())
        self.update_status("Configuracion guardada")

    def _start_clock(self) -> None:
        """Actualiza el reloj en la GUI cada segundo usando root.after (hilo principal)."""
        def _tick() -> None:
            if self.app_quitting:
                return
            if self.clock_label is not None and self.clock_label.winfo_exists():
                self.clock_label.config(text="Hora actual: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.clock_after_id = self.root.after(1000, _tick)

        _tick()

    def _start_sleep_watchdog(self) -> None:
        """
        Inicia un hilo daemon que detecta cuando el sistema regresa de hibernacion.
        Principio: el hilo duerme 4 segundos en un bucle. Si entre dos iteraciones
        pasaron mas de 30 segundos de reloj real, el SO estuvo suspendido.
        Al detectarlo, dispara la reconexion del browser y la reprogramacion de
        mensajes que pudieron haber quedado pendientes durante el sueno.
        """
        def _watchdog() -> None:
            last_check = time.time()
            while not self.app_quitting:
                time.sleep(4)  # Intervalo de revision: 4 segundos
                now = time.time()
                elapsed = now - last_check
                last_check = now
                # Si pasaron mas de 30s (esperabamos ~4s), el sistema durmio
                if elapsed > 30 and not self.app_quitting:
                    # Notificar al hilo principal de la GUI de forma segura
                    self._ui_call(self._on_system_wake, elapsed)

        threading.Thread(target=_watchdog, daemon=True, name="SleepWatchdog").start()

    def _on_system_wake(self, sleep_duration_sec: float) -> None:
        """
        Llamado (en el hilo de la GUI) cuando se detecta que el sistema
        deserto de hibernacion o suspension.
        Acciones:
        1. Registrar evento en el log.
        2. Disparar reconexion forzada del browser en un hilo separado.
        3. Reprogramar mensajes que quedaron con fecha/hora en el pasado.
        """
        self.log_message(
            f"[WAKE] Sistema desperto tras ~{sleep_duration_sec:.0f}s de suspension. "
            "Iniciando reconexion del navegador..."
        )
        self.update_status("Sistema desperto de hibernacion. Reconectando WhatsApp...")

        # Reconexion del browser en hilo separado para no congelar la GUI
        threading.Thread(
            target=self.backend.trigger_post_sleep_recovery,
            daemon=True,
            name="PostSleepRecovery",
        ).start()

        # Reprogramar mensajes pasados que tienen modo de repeticion
        self._reschedule_past_due_repeating_messages()

    def _reschedule_past_due_repeating_messages(self) -> None:
        """
        Tras despertar de hibernacion, revisa los mensajes programados.
        Si un mensaje con repeticion tiene su datetime en el pasado, lo adelanta
        al 'ahora + 10 segundos' para que se envie pronto sin perderse.
        Los mensajes sin repeticion NO se reenvian (ya era intencional que no se enviaran).
        Se itera sobre un snapshot (copia) de la lista para evitar problemas de
        concurrencia si hilos de fondo modifican dicts durante la iteracion.
        """
        now = datetime.now()
        rescheduled = 0

        # Snapshot de la lista: evita RuntimeError si hilos de fondo modifican la lista
        # mientras iteramos. Los dicts internos se modifican in-place (es intencional).
        for msg in list(self.scheduled_messages):
            msg_dt = msg.get("datetime")
            if not isinstance(msg_dt, datetime) or msg_dt >= now:
                continue  # No esta en el pasado, no tocar

            if msg.get("is_group"):
                # Grupo: revisar cada item individualmente
                group_rescheduled = 0
                for item in list(msg.get("items", [])):
                    repeat = item.get("repeat", "Ninguno")
                    item_dt = item.get("datetime")
                    if repeat != "Ninguno" and isinstance(item_dt, datetime) and item_dt < now:
                        item["datetime"] = now + timedelta(seconds=10)
                        rescheduled += 1
                        group_rescheduled += 1
                # Bug fix V8.1.3: solo actualizar el container si al menos un item
                # fue reprogramado. Antes siempre se actualizaba si el container tenia
                # datetime en el pasado, lo que causaba envios inesperados post-hibernacion
                # a contactos cuyos items aun no eran debidos (datetime futuro).
                if group_rescheduled > 0:
                    msg["datetime"] = now + timedelta(seconds=10)
            else:
                # Mensaje individual con repeticion
                repeat = msg.get("repeat", "Ninguno")
                if repeat != "Ninguno":
                    msg["datetime"] = now + timedelta(seconds=10)
                    rescheduled += 1

        if rescheduled > 0:
            self.log_message(
                f"[WAKE] {rescheduled} mensaje(s) con repeticion reprogramados "
                "para envio inmediato post-hibernacion."
            )
            # Cancelar los after() previos y reprogramar todos desde el snapshot
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
