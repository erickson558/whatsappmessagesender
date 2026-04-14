from __future__ import annotations

import glob
import os
import sys
import threading
from datetime import datetime
from typing import Callable


def rotate_logs(pattern: str, keep: int = 3) -> None:
    """Elimina los archivos de log mas antiguos, conservando los ultimos 'keep'."""
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for filepath in files[keep:]:
        try:
            os.remove(filepath)
        except OSError:
            pass


class LoggingService:
    def __init__(self, ui_callback: Callable[[str], None] | None = None) -> None:
        # Fix V8.1.4: usar directorio absoluto del ejecutable (modo frozen) o CWD
        # (modo desarrollo). Evita que los logs queden en un directorio inesperado
        # cuando el .exe se lanza desde un path diferente al de la aplicacion.
        _base_dir = (
            os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.getcwd()
        )

        # Rotar logs antes de crear los nuevos (mantiene solo los ultimos 3 pares)
        rotate_logs(os.path.join(_base_dir, "logaplicacion*.txt"))
        rotate_logs(os.path.join(_base_dir, "logmensajes*.txt"))

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.app_log_path = os.path.join(_base_dir, f"logaplicacion{stamp}.txt")
        self.msg_log_path = os.path.join(_base_dir, f"logmensajes{stamp}.txt")
        self._app_file = open(self.app_log_path, "a", encoding="utf-8")
        self._msg_file = open(self.msg_log_path, "a", encoding="utf-8")
        self._ui_callback = ui_callback
        self._lock = threading.Lock()

    def set_ui_callback(self, callback: Callable[[str], None] | None) -> None:
        self._ui_callback = callback

    @staticmethod
    def _format_line(message: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{timestamp} - {message}"

    def log_app(self, message: str) -> None:
        """Escribe una linea en el log de la aplicacion y notifica la UI si hay callback."""
        line = self._format_line(message)
        with self._lock:
            self._app_file.write(f"{line}\n")
            self._app_file.flush()
        # Fix V8.1.4: capturar la referencia al callback antes de chequear para evitar
        # race condition donde otro hilo pone _ui_callback=None entre el 'if' y la llamada.
        cb = self._ui_callback
        if cb:
            cb(line)

    def log_message_sent(self, contact: str, message: str) -> None:
        line = self._format_line(f"Mensaje enviado a {contact}: {message}")
        with self._lock:
            self._msg_file.write(f"{line}\n")
            self._msg_file.flush()

    def close(self) -> None:
        with self._lock:
            try:
                self._app_file.close()
            except OSError:
                pass
            try:
                self._msg_file.close()
            except OSError:
                pass

