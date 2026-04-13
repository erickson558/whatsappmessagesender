from __future__ import annotations

import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Dict, Optional

import requests
from playwright._impl._errors import TargetClosedError


def _subprocess_no_window_kwargs() -> Dict[str, object]:
    if os.name != "nt":
        return {}
    kwargs: Dict[str, object] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = 0
        kwargs["startupinfo"] = startup_info
    except Exception:
        pass
    return kwargs


def _normalize_like(text: str) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9\s@.+#'_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokens(text: str) -> list[str]:
    normalized = _normalize_like(text)
    return [token for token in normalized.split() if token]


def _coverage_score(needle: str, candidate: str) -> float:
    needle_tokens = _tokens(needle)
    candidate_tokens = _tokens(candidate)
    if not needle_tokens or not candidate_tokens:
        return 0.0
    hits = sum(1 for token in needle_tokens if token in candidate_tokens)
    return hits / len(needle_tokens)


def _like_match(needle: str, candidate: str) -> bool:
    needle_tokens = _tokens(needle)
    candidate_tokens = _tokens(candidate)
    return all(token in candidate_tokens for token in needle_tokens) if needle_tokens else False


def _pids_by_name_win(name: str) -> set[int]:
    try:
        ps_script = (
            f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue "
            "| Select-Object -ExpandProperty Id) -join ','"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=6,
            **_subprocess_no_window_kwargs(),
        )
        return {int(x) for x in (out.stdout or "").strip().split(",") if x.strip().isdigit()}
    except Exception:
        return set()


def _existing_pids(browser_exe: str) -> set[int]:
    if os.name != "nt":
        try:
            out = subprocess.run(["pgrep", "-f", browser_exe], capture_output=True, text=True, timeout=6)
            return {int(x) for x in (out.stdout or "").split() if x.isdigit()}
        except Exception:
            return set()
    base = os.path.basename(browser_exe).lower()
    if "opera" in base:
        return _pids_by_name_win("opera")
    if "brave" in base:
        return _pids_by_name_win("brave")
    if "msedge" in base or "edge" in base:
        return _pids_by_name_win("msedge")
    if "chrome" in base:
        return _pids_by_name_win("chrome")
    return _pids_by_name_win(base.replace(".exe", ""))


@dataclass
class BrowserRuntimeSettings:
    browser: str
    browser_paths: Dict[str, str]
    remote_port: int = 9222
    debug_port_timeout: int = 60
    cdp_timeout: int = 90000
    cdp_retries: int = 3
    extra_wait: int = 5
    keepalive_interval_sec: int = 60
    relaunch_on_disconnect: bool = True
    user_data_dir: str = ""
    browser_extra_args: tuple[str, ...] = ()


class BrowserWorker(threading.Thread):
    def __init__(
        self,
        settings_provider: Callable[[], BrowserRuntimeSettings],
        log_fn: Callable[[str], None],
        status_fn: Callable[[str], None],
    ) -> None:
        super().__init__(daemon=True)
        self._settings_provider = settings_provider
        self.log = log_fn
        self.status = status_fn

        self.req_q: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        self.browser_process = None
        self.browser_exec: Optional[str] = None
        self._baseline_pids: set[int] = set()
        self._we_started = False
        self._opened_pages = []

        # --- Configuracion del navegador y conexion CDP ---
        self.browser_choice = "Opera"
        self.browser_paths: Dict[str, str] = {}
        self.remote_port = 9222
        self.debug_port_timeout = 60        # Segundos que se espera el puerto CDP al lanzar browser
        self.cdp_timeout = 90000            # Timeout CDP en ms para connect_over_cdp
        self.cdp_retries = 3                # Reintentos de conexion CDP
        self.extra_wait = 5                 # Segundos extra tras lanzar el browser antes de conectar
        self.keepalive_interval_sec = 60    # Intervalo entre pings de keepalive (0 = deshabilitado)
        self.relaunch_on_disconnect = True  # Relanzar browser si se pierde la conexion
        self.user_data_dir = ""             # Directorio del perfil del browser
        self.browser_extra_args: tuple[str, ...] = ()  # Argumentos extra al lanzar el browser

        # --- Estado interno del worker ---
        self._last_keepalive_at = 0.0       # Timestamp del ultimo keepalive exitoso
        self._launched_pids: set[int] = set()  # PIDs de procesos que nosotros lanzamos
        self._active_browser_choice: Optional[str] = None  # Navegador actualmente conectado
        self._shutdown_done = False         # Flag para evitar shutdown doble

        # --- Timeout rapido para detectar browser ya en ejecucion (segundos) ---
        # En modo normal: 2s. Se eleva temporalmente a ~12s tras hibernacion.
        self._quick_cdp_check_timeout: int = 2

        # --- Deteccion de hibernacion del sistema ---
        # Guardamos el tiempo real del ultimo ciclo del worker para detectar saltos.
        self._last_loop_time: float = time.time()

        self._refresh_settings()

    def _refresh_settings(self) -> None:
        config = self._settings_provider()
        self.browser_choice = config.browser
        self.browser_paths = dict(config.browser_paths or {})
        self.remote_port = int(config.remote_port)
        self.debug_port_timeout = int(config.debug_port_timeout)
        self.cdp_timeout = int(config.cdp_timeout)
        self.cdp_retries = int(config.cdp_retries)
        self.extra_wait = int(config.extra_wait)
        self.keepalive_interval_sec = max(0, int(getattr(config, "keepalive_interval_sec", 60) or 0))
        relaunch_raw = getattr(config, "relaunch_on_disconnect", True)
        if isinstance(relaunch_raw, str):
            self.relaunch_on_disconnect = relaunch_raw.strip().lower() not in ("0", "false", "no", "off")
        else:
            self.relaunch_on_disconnect = bool(relaunch_raw)
        self.user_data_dir = str(getattr(config, "user_data_dir", "") or "").strip()
        raw_extra_args = getattr(config, "browser_extra_args", ()) or ()
        self.browser_extra_args = tuple(str(arg).strip() for arg in raw_extra_args if str(arg).strip())

    def _resolve_user_data_dir(self) -> str:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        raw_value = self.user_data_dir.strip()
        if raw_value:
            expanded = os.path.expandvars(os.path.expanduser(raw_value))
            if os.path.isabs(expanded):
                return os.path.abspath(expanded)
            return os.path.abspath(os.path.join(base_dir, expanded))
        return os.path.abspath(os.path.join(base_dir, "whats_profile", self.browser_choice.lower()))

    def _build_browser_launch_args(self, exec_path: str, profile_dir: str) -> list[str]:
        args = [
            exec_path,
            f"--remote-debugging-port={self.remote_port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        args.extend(self.browser_extra_args)
        return args

    @staticmethod
    def _is_port_available(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", int(port)))
                return True
            except OSError:
                return False

    def _resolve_launch_port(self) -> int:
        preferred = int(self.remote_port)
        if self._is_port_available(preferred):
            return preferred
        for candidate in range(preferred + 1, preferred + 31):
            if self._is_port_available(candidate):
                self.log(f"Puerto CDP {preferred} ocupado. Se usara {candidate}.")
                return candidate
        return preferred

    def run(self) -> None:
        """
        Bucle principal del worker. Lee comandos de la cola y los ejecuta.
        Cuando la cola esta vacia, ejecuta el keepalive y la deteccion de hibernacion.
        Se ejecuta en un hilo daemon separado del hilo principal de la GUI.
        """
        # Inicializar referencia de tiempo para la deteccion de saltos (hibernacion)
        self._last_loop_time = time.time()

        while not self._stop_event.is_set():
            try:
                # Esperar un comando en la cola con timeout de 0.2s
                cmd, kwargs, done, out = self.req_q.get(timeout=0.2)
            except queue.Empty:
                # Cola vacia: ejecutar keepalive (y deteccion de hibernacion)
                self._maybe_keepalive()
                continue
            try:
                # Ejecutar el comando con recuperacion automatica ante desconexiones
                out["result"] = self._exec_with_recovery(cmd, kwargs)
            except Exception as error:
                out["error"] = str(error)
            finally:
                # Notificar al llamante que el comando termino (exitoso o con error)
                done.set()
        self._shutdown()

    def _maybe_keepalive(self) -> None:
        """
        Ejecuta un ping periodico para verificar que la conexion CDP sigue viva.
        Tambien detecta saltos de tiempo causados por hibernacion del sistema:
        si entre dos llamadas consecutivas pasaron mas de 30s (cuando solo deberian
        pasar ~0.2s), asumimos que el sistema durmio y disparamos reconexion forzada.
        """
        interval = int(self.keepalive_interval_sec)
        now = time.time()

        # --- Deteccion de hibernacion / suspension del sistema ---
        # El worker llama a _maybe_keepalive cada ~0.2s (timeout de req_q.get).
        # Si entre llamadas paso mas de 30s, el SO estuvo suspendido.
        elapsed_since_last_loop = now - self._last_loop_time
        self._last_loop_time = now

        if elapsed_since_last_loop > 30 and self._last_loop_time > 0:
            self.log(
                f"[SLEEP] Salto de tiempo detectado: {elapsed_since_last_loop:.1f}s "
                "entre ciclos (esperado ~0.2s). Posible hibernacion del sistema."
            )
            self._last_keepalive_at = now  # Reiniciar referencia de keepalive
            if not self._stop_event.is_set():
                # Usar timeout extendido para dar tiempo al browser de restaurarse
                self._quick_cdp_check_timeout = 12
                self._post_sleep_recover()
                self._quick_cdp_check_timeout = 2  # Restaurar timeout normal
            return

        # --- Keepalive normal ---
        if interval <= 0:
            return
        if now - self._last_keepalive_at < interval:
            return
        self._last_keepalive_at = now

        # Si no hay browser ni pagina activa, no hay nada que verificar
        if self.browser is None and self.page is None:
            return
        if self.page is None:
            return

        try:
            # Verificar que el contexto y la pagina siguen vivos evaluando JS simple
            if not self._is_context_alive() or not self._is_page_alive():
                raise RuntimeError("context/page no disponible")
            self.page.evaluate("() => document.readyState")
        except Exception as error:
            self.log(f"[KEEPALIVE] Conexion CDP inestable: {error}")
            if self.relaunch_on_disconnect and not self._stop_event.is_set():
                self._hard_recover("keepalive")

    def call(self, cmd: str, timeout: Optional[float] = None, **kwargs):
        done = threading.Event()
        out: Dict[str, object] = {}
        self.req_q.put((cmd, kwargs, done, out))
        if not done.wait(timeout=timeout):
            raise TimeoutError(f"Tiempo de espera agotado en comando '{cmd}'.")
        if "error" in out:
            raise RuntimeError(str(out["error"]))
        return out.get("result")

    def stop(self) -> None:
        self._stop_event.set()

    def _exec_cmd(self, cmd: str, kwargs: Dict[str, object]):
        """Despacha el comando recibido en la cola al metodo correspondiente."""
        if cmd == "ensure":
            # Inicializar/verificar conexion con el browser y WhatsApp Web
            return self._ensure_browser()
        if cmd == "bind_whatsapp_tab":
            # Conectar o encontrar la pestana de WhatsApp Web
            return self._bind_whatsapp_tab()
        if cmd == "open_new_chat":
            # Abrir el dialogo de nuevo chat en WhatsApp Web
            return self._open_new_chat()
        if cmd == "select_contact":
            # Buscar y seleccionar un contacto por nombre
            return self._select_contact(str(kwargs["contact"]))
        if cmd == "send_message":
            # Escribir y enviar el mensaje al contacto activo
            return self._send_message(str(kwargs["text"]), str(kwargs["contact"]))
        if cmd == "post_sleep_recover":
            # Recuperacion forzada tras hibernacion del sistema (timeout extendido)
            self._quick_cdp_check_timeout = 12
            try:
                self._post_sleep_recover()
            finally:
                self._quick_cdp_check_timeout = 2
            return True
        if cmd == "shutdown":
            # Detener el worker y cerrar el browser si lo lanzamos nosotros
            self._stop_event.set()
            self._shutdown(force=True)
            return True
        raise RuntimeError(f"Comando desconocido: {cmd}")

    def _exec_with_recovery(self, cmd: str, kwargs: Dict[str, object]):
        try:
            return self._exec_cmd(cmd, kwargs)
        except TargetClosedError as error:
            self.log(f"[RECOVER] Target cerrado en '{cmd}': {error}")
            if self._hard_recover(f"TargetClosedError en {cmd}"):
                return self._exec_cmd(cmd, kwargs)
            raise
        except Exception as error:
            lowered = str(error).lower()
            if "disconnected" in lowered or "closed" in lowered or "connection" in lowered:
                self.log(f"[RECOVER] Desconexion en '{cmd}': {error}")
                if self._hard_recover(f"Desconexion en {cmd}"):
                    return self._exec_cmd(cmd, kwargs)
            raise

    def _is_context_alive(self) -> bool:
        try:
            return self.context is not None and len(self.context.pages) >= 0
        except Exception:
            return False

    def _is_page_alive(self) -> bool:
        try:
            return self.page is not None and not self.page.is_closed()
        except Exception:
            return False

    def _wait_for_debug_port(self, timeout: Optional[int] = None) -> bool:
        limit = timeout or self.debug_port_timeout
        url = f"http://127.0.0.1:{self.remote_port}/json/version"
        start = time.time()
        while time.time() - start < limit:
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _capture_launched_pids(self, exec_path: str) -> None:
        launched: set[int] = set()
        try:
            post = _existing_pids(exec_path)
            launched.update(pid for pid in post if pid not in self._baseline_pids)
        except Exception:
            pass
        try:
            if self.browser_process and self.browser_process.pid:
                launched.add(int(self.browser_process.pid))
        except Exception:
            pass
        self._launched_pids = {pid for pid in launched if isinstance(pid, int) and pid > 0}

    def _launch_browser_proc(self) -> bool:
        """
        Lanza el proceso del navegador con debugging remoto habilitado.
        IMPORTANTE: Antes de lanzar uno nuevo, verifica si el navegador ya esta
        corriendo (puede pasar tras hibernacion donde el puerto tarda en responder).
        Si ya hay instancias del browser, espera con el timeout completo antes de
        intentar lanzar un proceso nuevo, evitando perder la sesion de WhatsApp.
        """
        exec_path = str(self.browser_paths.get(self.browser_choice, "")).strip()
        self.browser_exec = exec_path
        if not exec_path:
            self.status(f"No hay ruta configurada para {self.browser_choice}.")
            return False
        if not os.path.exists(exec_path):
            self.status(f"La ruta configurada no existe para {self.browser_choice}: {exec_path}")
            return False

        # --- NUEVO: Verificar si el browser ya esta corriendo (post-hibernacion) ---
        # Si detectamos PIDs activos del browser, esperamos que su puerto CDP
        # se restaure antes de lanzar una instancia nueva (que usaria otro puerto
        # o perfil, perdiendo la sesion de WhatsApp).
        existing_pids = _existing_pids(exec_path)
        if existing_pids:
            self.log(
                f"Se detectaron {len(existing_pids)} instancia(s) de {self.browser_choice} en ejecucion. "
                f"Esperando restauracion del puerto CDP {self.remote_port} "
                f"(timeout: {self.debug_port_timeout}s, tipico tras hibernacion)..."
            )
            if self._wait_for_debug_port(self.debug_port_timeout):
                # Puerto restaurado: conectar a la instancia existente en lugar de lanzar nueva
                self.log(f"Puerto CDP {self.remote_port} restaurado. Reconectando a instancia existente.")
                return True  # _ensure_browser_connection se encarga del connect_over_cdp
            # Si aun no responde, continuamos e intentamos lanzar nuevo browser
            self.log(
                f"El navegador existente no respondio al puerto CDP en {self.debug_port_timeout}s. "
                "Se intentara lanzar una nueva instancia."
            )

        # --- Lanzar nuevo proceso del navegador ---
        launch_port = self._resolve_launch_port()
        self.remote_port = launch_port
        profile_dir = self._resolve_user_data_dir()
        try:
            os.makedirs(profile_dir, exist_ok=True)
        except Exception as error:
            self.log(f"No se pudo preparar el perfil '{profile_dir}': {error}")
            return False

        launch_args = self._build_browser_launch_args(exec_path, profile_dir)
        self._baseline_pids = _existing_pids(exec_path)
        self._launched_pids.clear()
        self.status(f"Lanzando {self.browser_choice}: {exec_path}")
        self.log(f"Perfil de navegador: {profile_dir}")
        try:
            self.browser_process = subprocess.Popen(launch_args, shell=False)
            self._we_started = True
        except Exception as error:
            self.log(f"Fallo al iniciar {self.browser_choice}: {error}")
            return False

        # Esperar a que el puerto CDP este disponible con timeout completo
        if not self._wait_for_debug_port(self.debug_port_timeout):
            self._capture_launched_pids(exec_path)
            self.log(
                f"No se detecto CDP en puerto {self.remote_port}. "
                f"Cierra instancias abiertas de {self.browser_choice} o cambia el puerto."
            )
            self._kill_process_tree()
            return False

        self._capture_launched_pids(exec_path)
        return True

    def _connect_over_cdp(self) -> bool:
        from playwright.sync_api import sync_playwright

        if self.playwright is None:
            self.playwright = sync_playwright().start()

        self.browser = None
        for attempt in range(self.cdp_retries):
            try:
                self.browser = self.playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{self.remote_port}",
                    timeout=self.cdp_timeout,
                )
                self.log(f"Conexion CDP establecida (intento {attempt + 1}).")
                break
            except Exception as error:
                self.log(f"Intento CDP {attempt + 1}/{self.cdp_retries} fallido: {error}")
                time.sleep(2)

        if self.browser is None:
            return False

        try:
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        except Exception:
            try:
                self.context = self.browser.new_context()
            except Exception:
                self.context = None
                return False
        return True

    def _find_existing_whatsapp_tab(self) -> bool:
        if not self.browser:
            return False
        for context in self.browser.contexts:
            for page in context.pages:
                try:
                    if "web.whatsapp.com" in (page.url or ""):
                        self.context = context
                        self.page = page
                        self.log("Pestana existente de WhatsApp encontrada en el navegador seleccionado.")
                        return True
                except Exception:
                    continue
        return False

    def _bind_whatsapp_tab(self) -> bool:
        if not self._ensure_browser_connection():
            return False

        if self._find_existing_whatsapp_tab():
            if self._ensure_whatsapp_loaded(total_timeout=90000):
                return True
            self.log("Pestana de WhatsApp detectada, pero no quedo lista para envio (posible QR pendiente).")
            return False

        try:
            if self.context is None:
                self.context = self.browser.contexts[0] if self.browser and self.browser.contexts else self.browser.new_context()
            self.page = self.context.new_page()
            self._opened_pages.append(self.page)
            self.page.goto("https://web.whatsapp.com/", timeout=60000)
            self.log("No habia una pestana de WhatsApp; se abrio una nueva.")
            if self._ensure_whatsapp_loaded(total_timeout=90000):
                return True
            self.log("La nueva pestana de WhatsApp no quedo lista (posible QR pendiente o carga incompleta).")
            return False
        except Exception as error:
            self.log(f"No se pudo abrir/usar una pestana de WhatsApp: {error}")
            return False

    def _reset_connection_handles(self) -> None:
        """
        Libera todos los handles CDP de Playwright (page, context, browser).
        Se llama antes de reconectar para evitar usar referencias obsoletas.
        No lanza excepcion aunque alguno de los cierres falle.
        """
        # Descartar referencia a la pagina activa (puede estar cerrada/obsoleta)
        try:
            if self.page:
                self.page = None
        except Exception:
            pass
        # Descartar el contexto del browser
        try:
            if self.context:
                self.context = None
        except Exception:
            pass
        # Intentar cerrar el objeto browser de Playwright (no el proceso)
        try:
            if self.browser:
                try:
                    self.browser.close()
                except Exception:
                    pass
                self.browser = None
        except Exception:
            pass

    def _ensure_browser_connection(self) -> bool:
        """
        Garantiza que haya una conexion CDP activa con el navegador.
        1. Si ya hay conexion viva -> retorna True de inmediato.
        2. Si hay un browser corriendo en el puerto -> conecta via CDP.
        3. Si no hay browser corriendo -> lo lanza y conecta.
        El timeout rapido de deteccion ('_quick_cdp_check_timeout') se eleva a
        12s post-hibernacion para dar tiempo al browser de restaurar el puerto.
        """
        self._refresh_settings()

        # Detectar cambio de navegador seleccionado por el usuario
        if self._active_browser_choice and self._active_browser_choice != self.browser_choice:
            self.log(
                f"Cambio de navegador detectado ({self._active_browser_choice} -> {self.browser_choice}). Reiniciando conexion."
            )
            self._reset_connection_handles()

        # Si ya tenemos conexion viva, no hacemos nada
        if self.browser is not None and self._is_context_alive():
            self._active_browser_choice = self.browser_choice
            return True

        # Intentar conectar a un browser ya en ejecucion (quick check configurable)
        attached_to_existing = False
        quick_timeout = int(self._quick_cdp_check_timeout)
        if self._wait_for_debug_port(timeout=quick_timeout):
            attached_to_existing = self._connect_over_cdp()
            if attached_to_existing:
                self.log(f"Conectado a instancia ya abierta en puerto CDP {self.remote_port}.")

        if not attached_to_existing:
            # Lanzar nuevo browser (internamente verifica si ya hay uno corriendo)
            if not self._launch_browser_proc():
                return False
            time.sleep(self.extra_wait)
            if not self._connect_over_cdp():
                return False

        self._active_browser_choice = self.browser_choice
        return True

    def _hard_recover(self, reason: str = "") -> bool:
        """
        Recuperacion total: resetea todos los handles, reconecta el navegador
        y vuelve a enlazar la pestana de WhatsApp Web.
        Se llama cuando se detecta una desconexion CDP (TargetClosedError, etc.).
        """
        self.log(f"Iniciando recuperacion de navegador. Motivo: {reason or 'desconocido'}")
        self._reset_connection_handles()
        if not self._ensure_browser_connection():
            return False
        return self._bind_whatsapp_tab()

    def _post_sleep_recover(self) -> None:
        """
        Recuperacion especial tras detectar que el sistema estuvo en hibernacion.
        Usa un timeout extendido (_quick_cdp_check_timeout = 12s) porque el
        navegador puede tardar varios segundos en restaurar su puerto CDP despues
        de que el SO regresa de suspension.
        No lanza excepcion: registra el resultado en el log y actualiza el estado.
        """
        self.log(
            "[SLEEP-RECOVER] Iniciando recuperacion post-hibernacion "
            f"(timeout deteccion CDP: {self._quick_cdp_check_timeout}s)..."
        )
        self.status("Sistema despertando de hibernacion. Reconectando navegador...")
        try:
            # Forzar cierre de handles obsoletos (la conexion TCP se rompio al hibernar)
            self._reset_connection_handles()
            # Reconectar browser y WhatsApp Web
            if self._ensure_browser_connection():
                if self._bind_whatsapp_tab():
                    self.log("[SLEEP-RECOVER] Reconexion post-hibernacion exitosa.")
                    self.status("Reconexion post-hibernacion exitosa. WhatsApp listo.")
                else:
                    self.log("[SLEEP-RECOVER] Browser reconectado, pero WhatsApp no quedo listo (posible QR).")
                    self.status("Reconexion post-hibernacion: WhatsApp requiere escanear QR.")
            else:
                self.log("[SLEEP-RECOVER] No se pudo reconectar el navegador tras hibernacion.")
                self.status("Error de reconexion post-hibernacion. Verifique el navegador.")
        except Exception as error:
            self.log(f"[SLEEP-RECOVER] Error inesperado durante recuperacion: {error}")

    def _wait_app_ready(self, total_timeout_ms: int = 90000) -> bool:
        page = self.page
        if page is None:
            return False

        start = time.time()
        while (time.time() - start) * 1000 < total_timeout_ms:
            try:
                for state in ("load", "domcontentloaded", "networkidle"):
                    try:
                        page.wait_for_load_state(state, timeout=2500)
                    except Exception:
                        pass
                grid_ok = False
                try:
                    grid_ok = page.get_by_role("grid").first.is_visible(timeout=700)
                except Exception:
                    pass
                search_ok = False
                for selector in (
                    '[aria-label="Search input textbox"]',
                    "[data-testid='chat-list-search'] div[contenteditable='true']",
                ):
                    try:
                        if page.locator(selector).first.is_visible(timeout=700):
                            search_ok = True
                            break
                    except Exception:
                        continue
                if not search_ok:
                    try:
                        name_re = re.compile(r"(Buscar|Search|Buscar o empezar|Search or start)", re.I)
                        search_ok = page.get_by_role("textbox", name=name_re).first.is_visible(timeout=700)
                    except Exception:
                        pass

                composer_ok = False
                for selector in (
                    "footer [data-testid='conversation-compose-box-input'][contenteditable='true']",
                    "footer div[contenteditable='true'][data-lexical-editor='true']",
                    "footer div[role='textbox'][contenteditable='true'][aria-multiline='true']",
                    "footer div[contenteditable='true']",
                ):
                    try:
                        if page.locator(selector).last.is_visible(timeout=500):
                            composer_ok = True
                            break
                    except Exception:
                        continue

                new_chat_ok = False
                try:
                    new_chat_ok = page.get_by_role(
                        "button",
                        name=re.compile(r"Nuevo chat|New chat|Nueva conversacion", re.I),
                    ).first.is_visible(timeout=500)
                except Exception:
                    pass

                if (grid_ok and search_ok) or composer_ok or (grid_ok and new_chat_ok):
                    return True
            except Exception:
                pass
            try:
                page.wait_for_timeout(350)
            except Exception:
                time.sleep(0.35)
        return False

    def _looks_like_login_required(self) -> bool:
        if self.page is None:
            return False
        page = self.page
        try:
            if page.get_by_text(re.compile(r"(Escanea|Scan).*(codigo|code)", re.I)).first.is_visible(timeout=400):
                return True
        except Exception:
            pass
        for selector in (
            "canvas[aria-label*='Scan']",
            "canvas[data-ref]",
            "[data-testid='qrcode']",
        ):
            try:
                if page.locator(selector).first.is_visible(timeout=300):
                    return True
            except Exception:
                continue
        return False

    def _ensure_whatsapp_loaded(self, total_timeout: int = 90000) -> bool:
        if self.page is None:
            return False
        try:
            self.page.wait_for_load_state("load", timeout=min(15000, total_timeout))
        except Exception:
            pass
        ready = self._wait_app_ready(total_timeout_ms=total_timeout)
        if not ready and self._looks_like_login_required():
            self.status("WhatsApp Web requiere escanear QR para habilitar envios.")
        return ready

    def _ensure_browser(self) -> bool:
        if not self._bind_whatsapp_tab():
            self.status("No fue posible preparar WhatsApp Web.")
            return False
        return True

    def _dismiss_overlays(self) -> None:
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(120)
        except Exception:
            pass

    def _close_attach_menu(self) -> None:
        if self.page is None:
            return
        try:
            menu = self.page.locator("[data-testid='attach-menu'], [role='menu']").first
            if menu.is_visible(timeout=300):
                self.page.keyboard.press("Escape")
                self.page.wait_for_timeout(120)
        except Exception:
            pass

    def _get_header_name(self) -> str:
        page = self.page
        if page is None:
            return ""
        for selector in (
            "header [data-testid='conversation-info-header'] span[title]",
            "header span[title]",
        ):
            try:
                node = page.locator(selector).first
                if node.is_visible(timeout=500):
                    return (node.get_attribute("title") or node.inner_text(timeout=300) or "").strip()
            except Exception:
                continue
        try:
            heading = page.get_by_role("heading").first
            if heading.is_visible(timeout=500):
                return (heading.inner_text(timeout=300) or "").strip()
        except Exception:
            pass
        return ""

    def _get_active_chat_from_composer(self) -> str:
        page = self.page
        if page is None:
            return ""
        for selector in (
            "footer div[aria-label^='Type to']",
            "footer div[aria-label^='Type a message to']",
            "footer div[aria-label^='Escribe a']",
            "footer [data-testid='conversation-compose-box-input'][contenteditable='true']",
            "footer div[contenteditable='true'][data-lexical-editor='true']",
            "footer div[role='textbox'][contenteditable='true'][aria-multiline='true']",
            "footer div[contenteditable='true']",
        ):
            try:
                node = page.locator(selector).last
                if node.is_visible(timeout=500):
                    label = node.get_attribute("aria-label") or ""
                    if label:
                        match = re.search(
                            r"(?:Type(?: a message)? to|Escribe a)\s+(.+?)(?:\.)?$",
                            label,
                            flags=re.I,
                        )
                        if match:
                            return match.group(1).strip()
            except Exception:
                continue
        return self._get_header_name()

    def _is_in_chat(self, contact: str) -> bool:
        active = self._get_active_chat_from_composer()
        return _like_match(contact, active)

    def _focus_global_search(self):
        page = self.page
        if page is None:
            return None
        for selector in (
            '[aria-label="Search input textbox"]',
            "[data-testid='chat-list-search'] div[contenteditable='true']",
        ):
            try:
                root = page.locator(selector).first
                root.wait_for(state="visible", timeout=4000)
                root.click(force=True)
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                return root
            except Exception:
                continue
        try:
            name_re = re.compile(r"(Buscar|Search|Search or start|Buscar o empezar)", re.I)
            root = page.get_by_role("textbox", name=name_re).first
            root.click(force=True)
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            return root
        except Exception:
            return None

    def _clear_global_search(self) -> None:
        page = self.page
        if page is None:
            return
        for selector in (
            '[aria-label="Search input textbox"]',
            "[data-testid='chat-list-search'] div[contenteditable='true']",
        ):
            try:
                root = page.locator(selector).first
                if root.is_visible(timeout=250):
                    root.click(force=True)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Delete")
                    try:
                        page.evaluate("el => el.blur()", root)
                    except Exception:
                        pass
                    return
            except Exception:
                continue

    def _type_search_variants(self, contact: str) -> None:
        page = self.page
        if page is None:
            return
        variants = [contact]
        tokens = _tokens(contact)
        if tokens:
            variants.append(" ".join(tokens))
            variants.append("".join(tokens))
        for variant in variants:
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.type(variant, delay=10)
            page.wait_for_timeout(550)
            try:
                if page.get_by_role("gridcell").first.is_visible(timeout=350):
                    return
            except Exception:
                pass
            try:
                if page.locator("[data-testid='cell-frame-container']").first.is_visible(timeout=350):
                    return
            except Exception:
                pass

    def _collect_candidates(self):
        page = self.page
        candidates = []
        if page is None:
            return candidates

        def clean_name(raw: str) -> str:
            value = (raw or "").strip().split("\n", 1)[0]
            value = re.sub(r"\s+\d{1,2}:\d{2}\s*(am|pm|a\.m\.|p\.m\.)?$", "", value, flags=re.I)
            return value.strip()

        try:
            for idx, node in enumerate(page.get_by_role("gridcell").all()):
                try:
                    raw = node.get_attribute("aria-label") or node.inner_text(timeout=200) or ""
                except Exception:
                    raw = ""
                name = clean_name(raw)
                if name:
                    candidates.append(("gridcell", name, node, idx))
        except Exception:
            pass

        try:
            for idx, node in enumerate(page.locator("[data-testid='cell-frame-container']").all()):
                try:
                    name_node = node.locator("span[title]").first
                    raw = name_node.get_attribute("title") or name_node.inner_text(timeout=200) or ""
                except Exception:
                    try:
                        raw = node.get_attribute("aria-label") or node.inner_text(timeout=200) or ""
                    except Exception:
                        raw = ""
                name = clean_name(raw)
                if name:
                    candidates.append(("cell", name, node, 1000 + idx))
        except Exception:
            pass

        try:
            for idx, node in enumerate(page.locator("span[title]").all()):
                try:
                    raw = node.get_attribute("title") or node.inner_text(timeout=200) or ""
                except Exception:
                    raw = ""
                name = clean_name(raw)
                if name:
                    candidates.append(("span", name, node, 2000 + idx))
        except Exception:
            pass
        return candidates

    def _rank_candidates(self, contact: str, candidates):
        tokens = _tokens(contact)
        first = tokens[0] if tokens else ""
        ranked = []
        for kind, name, node, idx in candidates:
            coverage = _coverage_score(contact, name)
            starts = 1.0 if first and _normalize_like(name).startswith(first) else 0.0
            length_penalty = abs(len(_normalize_like(name)) - len(_normalize_like(contact)))
            score = coverage * 5.0 + starts * 1.5 + max(0, 3 - length_penalty * 0.2) + max(0, 1.0 - idx * 0.01)
            ranked.append((score, kind, name, node, idx))
        ranked.sort(key=lambda item: (-item[0], item[4]))
        return ranked

    def _wait_header(self, contact: str, timeout_ms: int = 9000) -> bool:
        end_time = time.time() + (timeout_ms / 1000.0)
        while time.time() < end_time:
            if self._is_in_chat(contact):
                return True
            self.page.wait_for_timeout(140)
        return False

    def _select_contact(self, contact: str) -> bool:
        if not self._ensure_browser():
            return False
        page = self.page
        if page is None:
            return False

        if self._is_in_chat(contact):
            self.log(f"Contacto '{contact}' ya estaba activo.")
            return True

        try:
            search = self._focus_global_search()
            if search is None:
                if not self._open_new_chat():
                    return False
                search = self._focus_global_search()
                if search is None:
                    self.status("No se pudo abrir el cuadro de busqueda.")
                    return False

            self._type_search_variants(contact)
            ranked = self._rank_candidates(contact, self._collect_candidates())

            if not ranked:
                try:
                    page.keyboard.press("ArrowDown")
                    page.wait_for_timeout(100)
                    page.keyboard.press("Enter")
                except Exception:
                    pass
            else:
                for attempt, (score, kind, name, node, idx) in enumerate(ranked[:4], start=1):
                    self.log(f"[LIKE] intento {attempt}: '{name}' (score={score:.2f}, idx={idx})")
                    try:
                        node.scroll_into_view_if_needed(timeout=1200)
                    except Exception:
                        pass
                    try:
                        target = node
                        if kind == "span":
                            try:
                                target = node.locator(
                                    "xpath=ancestor::*[@data-testid='cell-frame-container' or @role='gridcell'][1]"
                                ).first
                            except Exception:
                                target = node
                        target.click(timeout=3000, force=True)
                    except Exception:
                        try:
                            node.click(timeout=3000, force=True)
                        except Exception:
                            continue
                    if self._wait_header(contact, timeout_ms=9000):
                        self.log(f"Contacto seleccionado por coincidencia LIKE: {name}")
                        return True

            self._clear_global_search()
            if self._wait_header(contact, timeout_ms=9000):
                self.log(f"Contacto seleccionado por fallback de teclado: {contact}")
                return True
            raise TimeoutError("No se pudo confirmar apertura del chat objetivo.")
        except Exception as error:
            self.status(f"Error al seleccionar contacto: {contact}")
            self.log(f"Error al seleccionar '{contact}': {error}")
            return False

    def _open_new_chat(self) -> bool:
        if not self._ensure_browser():
            return False
        page = self.page
        try:
            button = page.get_by_role("button", name=re.compile(r"Nuevo chat|New chat|Nueva conversacion", re.I)).first
            button.click(timeout=5000, force=True)
            page.wait_for_timeout(250)
            return True
        except Exception:
            pass
        try:
            button = page.locator("button[data-testid='chat-list-new-chat'], span[data-icon='new-chat-outline']").first
            button.click(timeout=5000, force=True)
            page.wait_for_timeout(250)
            return True
        except Exception:
            pass
        try:
            page.keyboard.down("Control")
            page.keyboard.press("KeyN")
            page.keyboard.up("Control")
            page.wait_for_timeout(250)
            return True
        except Exception:
            return False

    def _ensure_chat_target(self, contact: str, attempts: int = 3) -> bool:
        if not contact:
            return False
        for idx in range(attempts):
            if self._is_in_chat(contact):
                return True
            self.log(
                f"[ensure_chat_target] actual='{self._get_active_chat_from_composer()}', objetivo='{contact}', reintento {idx + 1}/{attempts}"
            )
            if not self._select_contact(contact):
                time.sleep(0.2)
        return self._is_in_chat(contact)

    def _get_composer_for_contact(self):
        page = self.page
        last_error = None
        for selector in (
            "footer div[aria-label^='Type to']",
            "footer div[aria-label^='Type a message to']",
            "footer div[aria-label^='Escribe a']",
            "footer [data-testid='conversation-compose-box-input'][contenteditable='true']",
            "footer div[contenteditable='true'][data-lexical-editor='true']",
            "footer div[role='textbox'][contenteditable='true'][aria-multiline='true']",
            "footer div[contenteditable='true']",
        ):
            try:
                container = page.locator(selector).last
                if container.is_visible(timeout=900):
                    try:
                        paragraph = container.locator("p.selectable-text.copyable-text, p").last
                        if paragraph.is_visible(timeout=250):
                            return paragraph, container
                    except Exception:
                        pass
                    return container, container
            except Exception as error:
                last_error = error
        raise RuntimeError(f"No se encontro el compositor del chat: {last_error}")

    def _prime_composer(self, node) -> None:
        page = self.page
        self._close_attach_menu()
        try:
            node.scroll_into_view_if_needed(timeout=1200)
        except Exception:
            pass
        try:
            page.evaluate("(el) => el.focus()", node)
        except Exception:
            pass
        try:
            node.click(force=True)
        except Exception:
            pass
        try:
            page.keyboard.press("Space")
            page.keyboard.press("Backspace")
        except Exception:
            pass
        self._close_attach_menu()

    def _count_outgoing_messages(self) -> int:
        page = self.page
        if page is None:
            return 0
        for selector in (
            "div.message-out",
            "[data-testid='msg-container'].message-out",
        ):
            try:
                return int(page.locator(selector).count())
            except Exception:
                continue
        return 0

    def _wait_outgoing_increment(self, base_count: int, timeout_ms: int = 6000) -> bool:
        page = self.page
        if page is None:
            return False
        end = time.time() + timeout_ms / 1000.0
        while time.time() < end:
            try:
                if self._count_outgoing_messages() > base_count:
                    return True
            except Exception:
                pass
            try:
                page.wait_for_timeout(200)
            except Exception:
                time.sleep(0.2)
        return False

    def _verify_message_sent(self, text: str, timeout_ms: int = 9000) -> bool:
        page = self.page
        end = time.time() + timeout_ms / 1000.0
        normalize = lambda value: re.sub(r"\s+", " ", re.sub(r"\r\n|\r", "\n", value)).strip()
        text = normalize(text)
        while time.time() < end:
            for selector in (
                "div.message-out span.selectable-text",
                "div.message-out [data-testid='msg-text'] span",
                "div.message-out [data-lexical-text='true']",
            ):
                try:
                    nodes = page.locator(selector).all()
                except Exception:
                    nodes = []
                for node in nodes:
                    try:
                        if not node.is_visible():
                            continue
                        candidate = normalize(node.inner_text())
                        if candidate == text:
                            return True
                        if len(text) >= 6 and (text in candidate or candidate in text):
                            return True
                    except Exception:
                        continue
            page.wait_for_timeout(200)
        return False

    @staticmethod
    def _normalized_text(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"\r\n|\r", "\n", value or "")).strip()

    def _read_composer_text(self, node, container) -> str:
        for target in (node, container):
            try:
                value = target.inner_text(timeout=300)
                normalized = self._normalized_text(value)
                if normalized:
                    return normalized
            except Exception:
                continue
        return ""

    def _wait_composer_cleared(self, node, container, timeout_ms: int = 3000) -> bool:
        page = self.page
        if page is None:
            return False
        end = time.time() + timeout_ms / 1000.0
        while time.time() < end:
            try:
                current = self._read_composer_text(node, container)
                if not current:
                    return True
            except Exception:
                pass
            try:
                page.wait_for_timeout(150)
            except Exception:
                time.sleep(0.15)
        return False

    def _send_message(self, text: str, contact: str) -> bool:
        if not contact:
            self.status("No se indico contacto objetivo para el envio.")
            return False

        if not self._ensure_chat_target(contact, attempts=3):
            self.status(f"No se pudo asegurar el chat de {contact}.")
            self.log(f"ABORT envio: chat activo '{self._get_active_chat_from_composer()}', objetivo '{contact}'.")
            return False

        page = self.page
        normalized_text = re.sub(r"\r\n|\r", "\n", text).strip()

        try:
            node, container = self._get_composer_for_contact()
            self._clear_global_search()
            self._prime_composer(node)
            outgoing_before = self._count_outgoing_messages()
            pre_send_text = self._read_composer_text(node, container)

            wrote = False
            try:
                page.keyboard.insert_text(normalized_text)
                wrote = True
            except Exception:
                pass
            if not wrote:
                try:
                    node.fill(normalized_text)
                    wrote = True
                except Exception:
                    pass
            if not wrote:
                try:
                    page.keyboard.type(normalized_text, delay=14)
                    wrote = True
                except Exception:
                    pass
            if not wrote:
                try:
                    page.evaluate("document.execCommand('insertText', false, arguments[0])", normalized_text)
                    wrote = True
                except Exception:
                    pass

            if not wrote:
                raise RuntimeError("No se pudo escribir el mensaje en el compositor.")

            sent = False
            try:
                send_btn = page.get_by_role("button", name=re.compile(r"Enviar|Send", re.I)).first
                if send_btn.is_visible(timeout=900):
                    send_btn.click(timeout=1500)
                    sent = True
            except Exception:
                pass
            if not sent:
                try:
                    for selector in (
                        "footer div[aria-label^='Type to']",
                        "footer div[aria-label^='Type a message to']",
                        "footer div[aria-label^='Escribe a']",
                    ):
                        try:
                            page.locator(selector).last.press("Enter")
                            sent = True
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
            if not sent:
                try:
                    node.press("Enter")
                except Exception:
                    try:
                        container.press("Enter")
                    except Exception:
                        page.keyboard.press("Enter")

            if self._verify_message_sent(normalized_text, timeout_ms=9000):
                self.log(f"Mensaje enviado a '{contact}'.")
                return True

            if self._wait_outgoing_increment(outgoing_before, timeout_ms=6000):
                self.log(f"Mensaje enviado a '{contact}' (verificacion por incremento de mensajes salientes).")
                return True

            # Fallback anti-duplicados: si accion de envio fue ejecutada y el compositor quedo vacio, no reintentar.
            post_send_text = self._read_composer_text(node, container)
            if sent and not post_send_text and (pre_send_text or normalized_text):
                self.log(
                    f"Mensaje enviado a '{contact}' (confirmacion por compositor vacio; se evita reintento duplicado)."
                )
                return True

            self.status("No se verifico el envio en pantalla.")
            return False
        except Exception as error:
            self.status("Error al enviar mensaje.")
            self.log(f"Error al enviar a '{contact}': {error}")
            return False

    def _close_our_pages(self) -> None:
        for page in list(self._opened_pages):
            try:
                page.close()
            except Exception:
                pass
        self._opened_pages.clear()

    def _kill_process_tree(self) -> None:
        target_pids = set(self._launched_pids)
        try:
            if self.browser_process and self.browser_process.pid:
                target_pids.add(int(self.browser_process.pid))
        except Exception:
            pass
        if not target_pids and not self.browser_process:
            return
        try:
            if os.name == "nt":
                for pid in sorted(target_pids, reverse=True):
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        **_subprocess_no_window_kwargs(),
                    )
            else:
                for pid in sorted(target_pids, reverse=True):
                    try:
                        os.kill(pid, 15)
                    except Exception:
                        pass
                if self.browser_process:
                    self.browser_process.terminate()
        except Exception:
            pass
        finally:
            self.browser_process = None
            self._we_started = False
            self._launched_pids.clear()

    def _shutdown(self, force: bool = False) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True

        if force:
            self._kill_process_tree()
            self._opened_pages.clear()
        else:
            try:
                self._close_our_pages()
            except Exception:
                pass
            try:
                if self.context:
                    self.context.close()
            except Exception:
                pass
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                pass

        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass

        if not force:
            self._kill_process_tree()
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
