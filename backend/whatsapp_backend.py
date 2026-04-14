from __future__ import annotations

import threading
from typing import Callable

from backend.browser_worker import BrowserRuntimeSettings, BrowserWorker


class WhatsAppBackend:
    """
    Fachada entre la GUI y el BrowserWorker.
    Todos los metodos son thread-safe: envan comandos a la cola del worker
    y bloquean hasta obtener respuesta (con timeout configurable).
    """

    # Timeouts por operacion (segundos).
    # Valores generosos para cubrir recuperaciones post-hibernacion.
    _TIMEOUT_BIND = 120       # Enlazar pestana de WhatsApp (incluye posible reinicio del browser)
    _TIMEOUT_SELECT = 60      # Seleccionar contacto (busqueda en WhatsApp Web)
    _TIMEOUT_SEND = 120       # Enviar mensaje (escritura + envio + verificacion)
    _TIMEOUT_POST_SLEEP = 90  # Recuperacion tras hibernacion (browser puede tardar en restaurarse)

    def __init__(
        self,
        settings_provider: Callable[[], BrowserRuntimeSettings],
        log_fn: Callable[[str], None],
        status_fn: Callable[[str], None],
        sent_log_fn: Callable[[str, str], None],
    ) -> None:
        self._sent_log_fn = sent_log_fn      # Funcion para registrar mensajes enviados en log
        self._selected_contact = ""           # Contacto actualmente seleccionado (solo lectura externa)
        # Serializa el par select_contact+send_message para evitar race condition
        # cuando multiples hilos programan mensajes simultaneamente (ej. post-hibernacion)
        self._delivery_lock = threading.Lock()
        # Crear y arrancar el worker (hilo daemon de automatizacion de browser)
        self.worker = BrowserWorker(settings_provider=settings_provider, log_fn=log_fn, status_fn=status_fn)
        self.worker.start()

    @property
    def selected_contact(self) -> str:
        """Retorna el ultimo contacto seleccionado."""
        return self._selected_contact

    def ensure_browser(self) -> bool:
        """Inicializa la conexion con el browser y WhatsApp Web."""
        try:
            return bool(self.worker.call("ensure", timeout=self._TIMEOUT_BIND))
        except Exception:
            return False

    def bind_whatsapp_tab(self) -> bool:
        """Conecta al browser y enlaza la pestana de WhatsApp Web. Retorna True si listo para envio."""
        try:
            return bool(self.worker.call("bind_whatsapp_tab", timeout=self._TIMEOUT_BIND))
        except Exception:
            return False

    def open_new_chat(self) -> bool:
        """Abre el dialogo de nuevo chat en WhatsApp Web."""
        try:
            return bool(self.worker.call("open_new_chat", timeout=30))
        except Exception:
            return False

    def select_contact(self, contact: str) -> bool:
        """Busca y abre el chat con el contacto indicado. Retorna True si el chat quedo activo."""
        self._selected_contact = contact
        try:
            return bool(self.worker.call("select_contact", timeout=self._TIMEOUT_SELECT, contact=contact))
        except Exception:
            return False

    def send_message(self, message: str, contact: str = "") -> bool:
        """
        Envia el mensaje al contacto indicado (o al ultimo seleccionado si no se indica).
        Registra en log si fue exitoso.

        Nota: siempre pasar 'contact' explicitamente desde _process_scheduled_message
        para evitar race conditions cuando multiples hilos comparten esta instancia.
        """
        # Usar el contacto pasado por parametro; caer en _selected_contact solo como
        # compatibilidad de emergencia, pero en produccion siempre se debe pasar contact.
        effective_contact = contact or self._selected_contact
        if not effective_contact:
            return False
        try:
            sent = bool(
                self.worker.call(
                    "send_message",
                    timeout=self._TIMEOUT_SEND,
                    text=message,
                    contact=effective_contact,
                )
            )
            if sent:
                # Registrar el mensaje enviado en el log de mensajes
                self._sent_log_fn(effective_contact, message)
            return sent
        except Exception:
            return False

    def trigger_post_sleep_recovery(self) -> bool:
        """
        Fuerza reconexion del browser tras detectar que el sistema estuvo en hibernacion.
        Usa timeout extendido porque el browser puede tardar varios segundos en restaurar
        el puerto CDP despues de que el SO regresa de suspension.
        Llamar desde un hilo separado para no bloquear la GUI.
        """
        try:
            return bool(self.worker.call("post_sleep_recover", timeout=self._TIMEOUT_POST_SLEEP))
        except Exception:
            return False

    def shutdown(self, timeout_sec: float = 1.5) -> None:
        """Detiene el worker de forma ordenada y cierra el browser si lo lanzamos nosotros."""
        timeout = max(0.2, float(timeout_sec))
        try:
            self.worker.call("shutdown", timeout=timeout, force=True)
        except Exception:
            pass
        try:
            self.worker.stop()
        except Exception:
            pass
        try:
            self.worker.join(timeout=timeout)
        except Exception:
            pass
        # Si el worker sigue vivo tras el join, matar el proceso del browser directamente
        if self.worker.is_alive():
            try:
                self.worker._kill_process_tree()
            except Exception:
                pass
