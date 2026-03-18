from __future__ import annotations

import glob
import os
import threading
from datetime import datetime
from typing import Callable


def rotate_logs(pattern: str, keep: int = 3) -> None:
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for filepath in files[keep:]:
        try:
            os.remove(filepath)
        except OSError:
            pass


class LoggingService:
    def __init__(self, ui_callback: Callable[[str], None] | None = None) -> None:
        rotate_logs("logaplicacion*.txt")
        rotate_logs("logmensajes*.txt")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.app_log_path = f"logaplicacion{stamp}.txt"
        self.msg_log_path = f"logmensajes{stamp}.txt"
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
        line = self._format_line(message)
        with self._lock:
            self._app_file.write(f"{line}\n")
            self._app_file.flush()
        if self._ui_callback:
            self._ui_callback(line)

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

