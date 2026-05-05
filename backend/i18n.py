from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# Catálogo Español (idioma canónico / valores internos del sistema)
# ---------------------------------------------------------------------------
_ES: Dict[str, object] = {
    "app_title":              "Programador de Mensajes WhatsApp",
    "version_label":          "Version: {v}",
    "status_ready":           "Estado: listo",
    # splash
    "splash_configuring":     "Configurando ventana...",
    "splash_building":        "Construyendo interfaz grafica...",
    "splash_engine":          "Iniciando motor de WhatsApp...",
    "splash_services":        "Arrancando servicios internos...",
    "splash_ready":           "Listo!",
    # barra superior
    "lbl_browser":            "Navegador:",
    "btn_browser_path":       "Ruta navegador",
    "btn_restore_paths":      "Restaurar rutas",
    "btn_save_config":        "Guardar configuracion",
    "browser_path_display":   "Ruta {browser}: {path}",
    "path_not_configured":    "(sin configurar)",
    "lbl_language":           "Idioma:",
    # botones principales
    "btn_schedule":           "Programar mensajes",
    "btn_exit":               "Salir",
    "btn_donate":             "Comprame una cerveza",
    # bloque de mensaje
    "msg_block_title":        "Mensaje {n}",
    "lbl_contact":            "Contacto:",
    "lbl_message":            "Mensaje:",
    "lbl_send_date":          "Fecha de envio:",
    "lbl_hour":               "Hora:",
    "lbl_minute":             "Minuto:",
    "lbl_ampm":               "AM/PM:",
    "lbl_repeat":             "Repetir:",
    "lbl_days":               "Dias:",
    "chk_send":               "Enviar",
    "btn_stop_repeat":        "Detener repeticion",
    "btn_set_today":          "Set hoy",
    "group_tab":              "Grupo {n}",
    # nombres de dias
    "days":                   ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"],
    # opciones de repeticion (etiquetas de pantalla)
    "repeat_none":            "Ninguno",
    "repeat_minute":          "Cada minuto",
    "repeat_hour":            "Cada hora",
    "repeat_daily":           "Diariamente",
    "repeat_weekly":          "Semanalmente",
    "repeat_monthly":         "Mensualmente",
    # mensajes de estado
    "status_initialized":     "Aplicacion inicializada",
    "status_browser_sel":     "Navegador seleccionado: {browser}",
    "status_path_updated":    "Ruta de {browser} actualizada",
    "status_paths_restored":  "Rutas de navegadores restauradas a valores por defecto",
    "status_config_saved":    "Configuracion guardada",
    "status_scheduled":       "Mensajes programados",
    "status_repeat_stopped":  "Repeticion detenida para Grupo {group}, bloque {n}",
    "status_past_skip":       "Mensaje {n} del {group} esta en el pasado y no se programa",
    "status_past_reschedule": "Mensaje {n} del {group}: fecha pasada con repeticion '{repeat}'. Reprogramado para {dt}",
    "status_no_time":         "Error: seleccione hora/minuto/AM-PM para mensaje {n} del {group}",
    "status_bad_date":        "Error: fecha/hora invalida en mensaje {n} del {group}",
    "status_day_skip":        "Hoy no es dia permitido. Reprogramado para {new_time}",
    "status_msg_sent":        "Mensaje enviado a {contact}",
    "status_chat_fail":       "No se pudo abrir chat con {contact}",
    "status_send_err":        "Error enviando mensaje a {contact}",
    "status_retry":           "{reason}. Reintento {n}/{max} en {secs} segundos.",
    "status_exhausted":       "{reason}. Se agotaron reintentos ({max}).",
    "status_sleep_wake":      "Sistema desperto de hibernacion. Reconectando WhatsApp...",
    "status_wake_rescheduled":"[WAKE] {n} mensaje(s) con repeticion reprogramados para envio inmediato post-hibernacion.",
    "lang_restart_notice":    "Reinicia la aplicacion para aplicar el nuevo idioma.",
}

# ---------------------------------------------------------------------------
# Catálogo Inglés
# ---------------------------------------------------------------------------
_EN: Dict[str, object] = {
    "app_title":              "WhatsApp Message Scheduler",
    "version_label":          "Version: {v}",
    "status_ready":           "Status: ready",
    "splash_configuring":     "Configuring window...",
    "splash_building":        "Building graphical interface...",
    "splash_engine":          "Starting WhatsApp engine...",
    "splash_services":        "Starting internal services...",
    "splash_ready":           "Ready!",
    "lbl_browser":            "Browser:",
    "btn_browser_path":       "Browser path",
    "btn_restore_paths":      "Restore paths",
    "btn_save_config":        "Save configuration",
    "browser_path_display":   "{browser} path: {path}",
    "path_not_configured":    "(not configured)",
    "lbl_language":           "Language:",
    "btn_schedule":           "Schedule messages",
    "btn_exit":               "Exit",
    "btn_donate":             "Buy me a beer",
    "msg_block_title":        "Message {n}",
    "lbl_contact":            "Contact:",
    "lbl_message":            "Message:",
    "lbl_send_date":          "Send date:",
    "lbl_hour":               "Hour:",
    "lbl_minute":             "Minute:",
    "lbl_ampm":               "AM/PM:",
    "lbl_repeat":             "Repeat:",
    "lbl_days":               "Days:",
    "chk_send":               "Send",
    "btn_stop_repeat":        "Stop repetition",
    "btn_set_today":          "Set today",
    "group_tab":              "Group {n}",
    "days":                   ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "repeat_none":            "None",
    "repeat_minute":          "Every minute",
    "repeat_hour":            "Every hour",
    "repeat_daily":           "Daily",
    "repeat_weekly":          "Weekly",
    "repeat_monthly":         "Monthly",
    "status_initialized":     "Application initialized",
    "status_browser_sel":     "Selected browser: {browser}",
    "status_path_updated":    "{browser} path updated",
    "status_paths_restored":  "Browser paths restored to defaults",
    "status_config_saved":    "Configuration saved",
    "status_scheduled":       "Messages scheduled",
    "status_repeat_stopped":  "Repetition stopped for Group {group}, block {n}",
    "status_past_skip":       "Message {n} of {group} is in the past and won't be scheduled",
    "status_past_reschedule": "Message {n} of {group}: past date with repeat '{repeat}'. Rescheduled for {dt}",
    "status_no_time":         "Error: select hour/minute/AM-PM for message {n} of {group}",
    "status_bad_date":        "Error: invalid date/time for message {n} of {group}",
    "status_day_skip":        "Today is not an allowed day. Rescheduled for {new_time}",
    "status_msg_sent":        "Message sent to {contact}",
    "status_chat_fail":       "Could not open chat with {contact}",
    "status_send_err":        "Error sending message to {contact}",
    "status_retry":           "{reason}. Retry {n}/{max} in {secs} seconds.",
    "status_exhausted":       "{reason}. Retries exhausted ({max}).",
    "status_sleep_wake":      "System woke from hibernation. Reconnecting WhatsApp...",
    "status_wake_rescheduled":"[WAKE] {n} message(s) with repetition rescheduled for immediate post-hibernation delivery.",
    "lang_restart_notice":    "Restart the application to apply the new language.",
}

_CATALOGS: Dict[str, Dict[str, object]] = {"es": _ES, "en": _EN}

# Valores canónicos de repetición (en español, usados internamente y en config.json).
# La UI puede mostrar versiones traducidas, pero al guardar/comparar siempre se usa esta lista.
_CANONICAL_TO_KEY: Dict[str, str] = {
    "Ninguno":      "repeat_none",
    "Cada minuto":  "repeat_minute",
    "Cada hora":    "repeat_hour",
    "Diariamente":  "repeat_daily",
    "Semanalmente": "repeat_weekly",
    "Mensualmente": "repeat_monthly",
}

# Lista de valores canónicos (importable por la GUI para validaciones)
CANONICAL_REPEAT_OPTIONS: List[str] = list(_CANONICAL_TO_KEY.keys())


class Translator:
    """Proveedor de cadenas traducidas. Llama a t("clave") para obtener la traducción."""

    def __init__(self, lang: str = "es") -> None:
        self._lang = lang if lang in _CATALOGS else "es"

    # ------------------------------------------------------------------
    @property
    def lang(self) -> str:
        return self._lang

    @lang.setter
    def lang(self, value: str) -> None:
        self._lang = value if value in _CATALOGS else "es"

    # ------------------------------------------------------------------
    def t(self, key: str, **kwargs) -> str:
        """Retorna la cadena traducida para 'key'. Acepta kwargs para formateo."""
        catalog = _CATALOGS.get(self._lang, _ES)
        val = catalog.get(key)
        if val is None:
            val = _ES.get(key, key)
        if not isinstance(val, str):
            val = str(val)
        if kwargs:
            try:
                val = val.format(**kwargs)
            except (KeyError, ValueError):
                pass
        return val

    def days(self) -> List[str]:
        """Retorna los nombres de días traducidos."""
        catalog = _CATALOGS.get(self._lang, _ES)
        result = catalog.get("days") or _ES["days"]
        return list(result)  # type: ignore[arg-type]

    def repeat_options(self) -> List[str]:
        """Retorna las opciones de repetición traducidas (para mostrar en combobox)."""
        return [
            self.t("repeat_none"),
            self.t("repeat_minute"),
            self.t("repeat_hour"),
            self.t("repeat_daily"),
            self.t("repeat_weekly"),
            self.t("repeat_monthly"),
        ]

    def canonical_to_display(self, canonical: str) -> str:
        """Convierte un valor canónico (español) al texto traducido para mostrar en la UI."""
        key = _CANONICAL_TO_KEY.get(canonical)
        return self.t(key) if key else canonical

    def display_to_canonical(self, display: str) -> str:
        """Convierte el texto de pantalla (posiblemente traducido) al valor canónico español."""
        for canonical, key in _CANONICAL_TO_KEY.items():
            if display == self.t(key):
                return canonical
        # Si no coincide ninguna traducción, retornar tal cual (ya puede ser canónico)
        return display

    @staticmethod
    def supported_languages() -> List[str]:
        return list(_CATALOGS.keys())
