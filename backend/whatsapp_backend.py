from __future__ import annotations

from typing import Callable

from backend.browser_worker import BrowserRuntimeSettings, BrowserWorker


class WhatsAppBackend:
    def __init__(
        self,
        settings_provider: Callable[[], BrowserRuntimeSettings],
        log_fn: Callable[[str], None],
        status_fn: Callable[[str], None],
        sent_log_fn: Callable[[str, str], None],
    ) -> None:
        self._sent_log_fn = sent_log_fn
        self._selected_contact = ""
        self.worker = BrowserWorker(settings_provider=settings_provider, log_fn=log_fn, status_fn=status_fn)
        self.worker.start()

    @property
    def selected_contact(self) -> str:
        return self._selected_contact

    def ensure_browser(self) -> bool:
        try:
            return bool(self.worker.call("ensure"))
        except Exception:
            return False

    def bind_whatsapp_tab(self) -> bool:
        try:
            return bool(self.worker.call("bind_whatsapp_tab"))
        except Exception:
            return False

    def open_new_chat(self) -> bool:
        try:
            return bool(self.worker.call("open_new_chat"))
        except Exception:
            return False

    def select_contact(self, contact: str) -> bool:
        self._selected_contact = contact
        try:
            return bool(self.worker.call("select_contact", contact=contact))
        except Exception:
            return False

    def send_message(self, message: str) -> bool:
        if not self._selected_contact:
            return False
        try:
            sent = bool(
                self.worker.call(
                    "send_message",
                    text=message,
                    contact=self._selected_contact,
                )
            )
            if sent:
                self._sent_log_fn(self._selected_contact, message)
            return sent
        except Exception:
            return False

    def shutdown(self, timeout_sec: float = 1.5) -> None:
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
        if self.worker.is_alive():
            try:
                self.worker._kill_process_tree()
            except Exception:
                pass
