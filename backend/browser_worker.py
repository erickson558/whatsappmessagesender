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
    """Devuelve kwargs para suprimir ventana de consola en subprocesos Windows.

    En sistemas que no son Windows devuelve un dict vacio porque la flag
    CREATE_NO_WINDOW y STARTUPINFO solo existen en el modulo subprocess de Win32.
    """
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
    """Normaliza texto para comparacion sin tildes, en minusculas y sin caracteres especiales.

    Aplica descomposicion NFKD para separar diacriticos, luego los elimina,
    convierte a minusculas y sustituye todo lo que no sea alfanumerico o
    separador por espacio, colapsando multiples espacios.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9\s@.+#'_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _tokens(text: str) -> list[str]:
    """Tokeniza texto normalizado; cada token es una palabra sin espacios."""
    normalized = _normalize_like(text)
    return [token for token in normalized.split() if token]


def _coverage_score(needle: str, candidate: str) -> float:
    """Porcentaje de tokens de needle que aparecen en candidate (0.0-1.0).

    Retorna 0.0 si alguna de las dos cadenas no produce tokens.
    Util para ordenar candidatos de busqueda por relevancia sin exigir match exacto.
    """
    needle_tokens = _tokens(needle)
    candidate_tokens = _tokens(candidate)
    if not needle_tokens or not candidate_tokens:
        return 0.0
    hits = sum(1 for token in needle_tokens if token in candidate_tokens)
    return hits / len(needle_tokens)


def _like_match(needle: str, candidate: str) -> bool:
    """True si TODOS los tokens de needle estan presentes en candidate (match exacto por tokens).

    Usado para verificar que el chat actualmente abierto en WA Web corresponde
    al contacto objetivo antes de escribir un mensaje.
    """
    needle_tokens = _tokens(needle)
    candidate_tokens = _tokens(candidate)
    return all(token in candidate_tokens for token in needle_tokens) if needle_tokens else False


def _pids_by_name_win(name: str) -> set[int]:
    """Retorna PIDs de procesos Windows por nombre usando PowerShell.

    Usa Get-Process en lugar de tasklist porque devuelve directamente enteros
    y maneja correctamente procesos con multiples instancias del mismo nombre.
    """
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
    """Retorna PIDs activos del proceso del browser (cross-platform).

    En Windows resuelve el nombre del proceso segun el ejecutable (opera, brave,
    msedge, chrome). En Linux/Mac usa pgrep -f. Se usa para capturar una linea
    base de PIDs antes de lanzar el browser y para detectar instancias zombie.
    """
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
    """Parametros de conexion y comportamiento del BrowserWorker.

    Instanciada por la GUI y pasada al worker via settings_provider.
    Todos los campos tienen valores por defecto seguros para que la GUI
    solo deba especificar los campos que difieren del comportamiento estandar.
    """

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

        # --- Proteccion contra recuperacion post-sleep doble ---
        # El worker (_maybe_keepalive) y el watchdog de la GUI pueden detectar
        # la hibernacion casi al mismo tiempo. Este flag evita que _post_sleep_recover
        # se ejecute dos veces en PARALELO.
        self._recovering_from_sleep: bool = False
        # Cooldown para evitar doble recuperacion SECUENCIAL: si la recuperacion
        # se ejecuto hace menos de 30s, ignorar la segunda llamada.
        self._last_sleep_recover_at: float = 0.0

        self._refresh_settings()

    def _refresh_settings(self) -> None:
        """Actualiza parametros del worker desde el ConfigStore (permite cambios en caliente sin reiniciar).

        Se invoca al inicio del constructor y antes de cada conexion CDP, de modo
        que el usuario pueda cambiar browser, puerto o timeouts sin reiniciar el worker.
        """
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
        """Resuelve el directorio del perfil del browser; relativo al .exe o al CWD segun el modo de ejecucion.

        Si user_data_dir esta vacio, crea el subdirectorio whats_profile/<browser>
        junto al ejecutable (modo frozen/PyInstaller) o junto al CWD (modo desarrollo).
        Rutas absolutas configuradas por el usuario se usan tal cual.
        """
        base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
        raw_value = self.user_data_dir.strip()
        if raw_value:
            expanded = os.path.expandvars(os.path.expanduser(raw_value))
            if os.path.isabs(expanded):
                return os.path.abspath(expanded)
            return os.path.abspath(os.path.join(base_dir, expanded))
        return os.path.abspath(os.path.join(base_dir, "whats_profile", self.browser_choice.lower()))

    def _build_browser_launch_args(self, exec_path: str, profile_dir: str) -> list[str]:
        """Construye los argumentos CLI para lanzar el browser con debugging remoto habilitado."""
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
        """True si el puerto TCP esta libre para bind (no ocupado por otro proceso)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", int(port)))
                return True
            except OSError:
                return False

    def _resolve_launch_port(self) -> int:
        """Devuelve el puerto CDP a usar; busca uno libre si el preferido esta ocupado.

        Busca hasta 30 puertos consecutivos a partir del puerto configurado.
        Si ningun candidato esta libre, retorna el puerto preferido de todas formas
        para que el proceso falle con un error descriptivo del sistema operativo.
        """
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
                cmd, kwargs, done, out = self.req_q.get(timeout=0.2)
            except queue.Empty:
                self._maybe_keepalive()
                continue
            try:
                out["result"] = self._exec_with_recovery(cmd, kwargs)
            except Exception as error:
                out["error"] = str(error)
            finally:
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

        # Fix V8.1.4: eliminado 'and self._last_loop_time > 0' (dead code: _last_loop_time
        # se asigna 'now' en la linea anterior, siempre > 0 al llegar aqui).
        if elapsed_since_last_loop > 30:
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

        # Si no hay pagina activa, no hay nada que verificar
        if self.page is None:
            return

        try:
            # Verificar que el contexto y la pagina siguen vivos evaluando JS simple
            if not self._is_context_alive() or not self._is_page_alive():
                raise RuntimeError("context/page no disponible")
            self.page.evaluate("() => document.readyState")
            # FIX V8.5.0: tras dias de ejecucion, WhatsApp puede mostrar QR o
            # "telefono desconectado" aunque CDP siga vivo. El keepalive estaba
            # "ciego" a este estado y los mensajes agotaban retries sin recuperarse.
            if self._looks_like_login_required():
                raise RuntimeError("WhatsApp Web requiere reautenticacion (QR detectado en keepalive)")
        except Exception as error:
            self.log(f"[KEEPALIVE] Conexion CDP inestable: {error}")
            if self.relaunch_on_disconnect and not self._stop_event.is_set():
                self._hard_recover("keepalive")

    def call(self, cmd: str, timeout: Optional[float] = None, **kwargs):
        """Envia un comando al worker via cola y bloquea hasta recibir respuesta o timeout.

        Lanza TimeoutError si el worker no responde antes del limite.
        Lanza RuntimeError con el mensaje del error si el comando fallo en el worker.
        Puede llamarse desde cualquier hilo (tipicamente el hilo de la GUI).
        """
        done = threading.Event()
        out: Dict[str, object] = {}
        self.req_q.put((cmd, kwargs, done, out))
        if not done.wait(timeout=timeout):
            raise TimeoutError(f"Tiempo de espera agotado en comando '{cmd}'.")
        if "error" in out:
            raise RuntimeError(str(out["error"]))
        return out.get("result")

    def stop(self) -> None:
        """Senala al worker que debe detenerse en el proximo ciclo del bucle principal."""
        self._stop_event.set()

    def _exec_cmd(self, cmd: str, kwargs: Dict[str, object]):
        """Despacha el comando recibido en la cola al metodo correspondiente."""
        if cmd == "ensure":
            return self._ensure_browser()
        if cmd == "bind_whatsapp_tab":
            return self._bind_whatsapp_tab()
        if cmd == "open_new_chat":
            return self._open_new_chat()
        if cmd == "select_contact":
            return self._select_contact(str(kwargs["contact"]))
        if cmd == "send_message":
            return self._send_message(str(kwargs["text"]), str(kwargs["contact"]))
        if cmd == "post_sleep_recover":
            # Timeout extendido para dar tiempo al browser de restaurarse tras hibernacion
            self._quick_cdp_check_timeout = 12
            try:
                self._post_sleep_recover()
            finally:
                self._quick_cdp_check_timeout = 2
            return True
        if cmd == "shutdown":
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
        """True si el contexto CDP responde al acceder a sus paginas (proxy de conexion viva)."""
        try:
            return self.context is not None and self.context.pages is not None
        except Exception:
            return False

    def _is_page_alive(self) -> bool:
        """True si la pagina Playwright no esta cerrada."""
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
        """Registra los PIDs que el worker lanzo para poder matarlos al shutdown.

        Calcula la diferencia entre los PIDs existentes post-launch y la linea base
        capturada antes de lanzar. Tambien agrega el PID directo del Popen si esta disponible.
        Solo guarda enteros positivos validos.
        """
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

        # Si hay PIDs activos del browser, esperamos que su puerto CDP se restaure
        # antes de lanzar una instancia nueva (que usaria otro puerto o perfil,
        # perdiendo la sesion de WhatsApp). Tipico escenario post-hibernacion.
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

    def _connect_over_cdp(self, timeout_ms: Optional[int] = None) -> bool:
        """
        Conecta Playwright al browser via CDP.
        'timeout_ms': timeout en ms por intento; si None usa self.cdp_timeout (default 90s).
        Pasar un valor menor (ej 30000) permite detectar browsers zombie rapidamente.
        """
        from playwright.sync_api import sync_playwright

        # FIX V8.5.0: tras dias de uso continuo, la instancia de sync_playwright
        # puede quedar stale (el proceso interno de Playwright puede haberse caido).
        # Validamos accediendo a un atributo; si lanza excepcion, recreamos la instancia.
        if self.playwright is not None:
            try:
                _ = self.playwright.chromium  # health check rapido
            except Exception:
                self.log("[CDP] Instancia Playwright stale detectada. Reiniciando instancia...")
                try:
                    self.playwright.stop()
                except Exception:
                    pass
                self.playwright = None

        if self.playwright is None:
            self.playwright = sync_playwright().start()

        effective_timeout = timeout_ms if timeout_ms is not None else self.cdp_timeout

        self.browser = None
        for attempt in range(self.cdp_retries):
            try:
                self.browser = self.playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{self.remote_port}",
                    timeout=effective_timeout,
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

    def _kill_all_browser_processes(self, exec_path: str = "") -> int:
        """
        Mata TODOS los procesos del browser, incluidos zombies post-hibernacion.
        A diferencia de _kill_process_tree() (solo mata PIDs que lanzamos nosotros),
        este metodo elimina cualquier instancia del browser por nombre de proceso.
        Util cuando el browser responde al puerto HTTP pero CDP se cuelga (zombie).
        Devuelve el numero de PIDs encontrados antes de la eliminacion.
        """
        path = exec_path or str(self.browser_exec or "").strip()
        if not path:
            return 0
        pids = _existing_pids(path)
        if not pids:
            return 0
        base = os.path.basename(path).lower()
        if os.name == "nt":
            try:
                # Matar por nombre de imagen: mas confiable que por PID individual
                subprocess.run(
                    ["taskkill", "/IM", base, "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=12,
                    **_subprocess_no_window_kwargs(),
                )
            except Exception:
                # Fallback: matar cada PID individualmente
                for pid in sorted(pids, reverse=True):
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            **_subprocess_no_window_kwargs(),
                        )
                    except Exception:
                        pass
        else:
            for pid in sorted(pids, reverse=True):
                try:
                    os.kill(pid, 9)
                except Exception:
                    pass
        return len(pids)

    def _wait_port_free(self, timeout_sec: int = 15) -> bool:
        """Espera hasta que el puerto CDP quede libre (disponible para bind). Util tras kill de zombies."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self._is_port_available(self.remote_port):
                return True
            time.sleep(1)
        return False

    def _ensure_browser_connection(self) -> bool:
        """
        Garantiza que haya una conexion CDP activa con el navegador.
        1. Si ya hay conexion viva -> retorna True de inmediato.
        2. Si hay un browser corriendo en el puerto -> conecta via CDP.
           FIX V8.2.0: si el puerto HTTP responde pero CDP falla (browser zombie
           post-hibernacion), mata todos los procesos zombie antes de relanzar.
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

        # Registrar exec_path para uso en kill de zombies (incluso antes de lanzar)
        exec_path = str(self.browser_paths.get(self.browser_choice, "")).strip()
        if exec_path:
            self.browser_exec = exec_path

        # Intentar conectar a un browser ya en ejecucion (quick check configurable)
        attached_to_existing = False
        quick_timeout = int(self._quick_cdp_check_timeout)
        port_was_up = self._wait_for_debug_port(timeout=quick_timeout)

        if port_was_up:
            # Usar timeout reducido (30s) para detectar zombies rapido sin bloquear 270s
            zombie_check_timeout = min(30000, self.cdp_timeout)
            attached_to_existing = self._connect_over_cdp(timeout_ms=zombie_check_timeout)
            if attached_to_existing:
                self.log(f"Conectado a instancia ya abierta en puerto CDP {self.remote_port}.")
            elif exec_path and _existing_pids(exec_path):
                # Puerto HTTP responde pero CDP fallo → browser zombie post-hibernacion.
                # Matar todos los procesos zombie para poder relanzar browser fresco.
                self.log(
                    f"[CDP] Puerto {self.remote_port} responde HTTP pero CDP fallo. "
                    f"Eliminando procesos zombie de {self.browser_choice}..."
                )
                killed = self._kill_all_browser_processes(exec_path)
                self.log(f"[CDP] {killed} proceso(s) zombie eliminados. Esperando que el puerto quede libre...")
                self._wait_port_free(timeout_sec=15)

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
        Estrategia en dos pasos:
          1. Intentar reconectar directamente (browser puede ya estar listo).
          2. Si falla y hay procesos zombie (responden HTTP pero no CDP), matarlos y
             relanzar browser fresco.
        Protegida con el flag '_recovering_from_sleep' para evitar doble ejecucion
        en paralelo, y con un cooldown de 30s para evitar reentrada secuencial.
        FIX V8.2.0: si la recuperacion falla completamente, se resetea el cooldown
        para que el proximo evento de hibernacion pueda disparar un nuevo intento
        de inmediato (en lugar de quedar bloqueado por el cooldown).
        """
        # Evitar recuperacion doble en paralelo
        if self._recovering_from_sleep:
            self.log("[SLEEP-RECOVER] Recuperacion ya en progreso. Ignorando llamada duplicada.")
            return
        # Cooldown: evitar doble recuperacion secuencial (worker + watchdog de GUI)
        now = time.time()
        if now - self._last_sleep_recover_at < 30:
            self.log("[SLEEP-RECOVER] Recuperacion reciente (<30s). Ignorando llamada redundante.")
            return
        self._recovering_from_sleep = True
        self._last_sleep_recover_at = now

        self.log(
            "[SLEEP-RECOVER] Iniciando recuperacion post-hibernacion "
            f"(timeout deteccion CDP: {self._quick_cdp_check_timeout}s)..."
        )
        self.status("Sistema despertando de hibernacion. Reconectando navegador...")
        recovered = False
        try:
            # Paso 1: Forzar cierre de handles obsoletos y reconectar directamente
            self._reset_connection_handles()
            if self._ensure_browser_connection():
                if self._bind_whatsapp_tab():
                    self.log("[SLEEP-RECOVER] Reconexion post-hibernacion exitosa.")
                    self.status("Reconexion post-hibernacion exitosa. WhatsApp listo.")
                    recovered = True
                    return
                else:
                    self.log("[SLEEP-RECOVER] Browser reconectado, pero WhatsApp no quedo listo (posible QR).")
                    self.status("Reconexion post-hibernacion: WhatsApp requiere escanear QR.")
                    recovered = True  # Browser OK, el QR es problema del usuario
                    return

            # Paso 2: La reconexion directa fallo. Intentar kill de zombies + relaunch fresco.
            exec_path = str(self.browser_exec or self.browser_paths.get(self.browser_choice, "")).strip()
            if exec_path:
                zombie_pids = _existing_pids(exec_path)
                if zombie_pids:
                    self.log(
                        f"[SLEEP-RECOVER] Reconexion directa fallida con {len(zombie_pids)} proceso(s) activos. "
                        "Intentando kill de zombies y relanzamiento..."
                    )
                    killed = self._kill_all_browser_processes(exec_path)
                    self.log(f"[SLEEP-RECOVER] {killed} proceso(s) eliminados. Esperando liberacion del puerto...")
                    self._wait_port_free(timeout_sec=20)
                    self._reset_connection_handles()
                    if self._ensure_browser_connection():
                        if self._bind_whatsapp_tab():
                            self.log("[SLEEP-RECOVER] Reconexion post-hibernacion exitosa (tras kill de zombies).")
                            self.status("Reconexion post-hibernacion exitosa. WhatsApp listo.")
                            recovered = True
                            return
                        else:
                            self.log("[SLEEP-RECOVER] Browser relanzado, WhatsApp no quedo listo (posible QR).")
                            self.status("Reconexion post-hibernacion: WhatsApp requiere escanear QR.")
                            recovered = True
                            return

            self.log("[SLEEP-RECOVER] No se pudo reconectar el navegador tras hibernacion.")
            self.status("Error de reconexion post-hibernacion. Verifique el navegador.")
        except Exception as error:
            self.log(f"[SLEEP-RECOVER] Error inesperado durante recuperacion: {error}")
        finally:
            # Si la recuperacion fallo completamente, resetear cooldown para que el
            # proximo evento de hibernacion pueda disparar un nuevo intento de inmediato.
            if not recovered:
                self._last_sleep_recover_at = 0.0
            self._recovering_from_sleep = False

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
        """Cierra overlays o menus abiertos presionando Escape."""
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(120)
        except Exception:
            pass

    def _close_attach_menu(self) -> None:
        """Cierra el menu de adjuntos si esta visible (evita que bloquee el compositor)."""
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
            "header [data-testid='conversation-header'] span[title]",
            "#main header span[title]",
            "header span[title]",
            "#main header [title]",
        ):
            try:
                node = page.locator(selector).first
                if node.is_visible(timeout=500):
                    text = (node.get_attribute("title") or node.inner_text(timeout=300) or "").strip()
                    if text:
                        return text
            except Exception:
                continue
        # WA Web 2025: fallback JavaScript — lee texto visible del header principal.
        # Independiente de data-testid o clases CSS que WhatsApp puede cambiar.
        try:
            js_text = page.evaluate("""
                () => {
                    // El header del chat abierto está en #main (no en el panel lateral)
                    const mainHeader = document.querySelector('#main header')
                        || document.querySelector('[data-testid="conversation-header"]')
                        || document.querySelector('[data-testid="conversation-info-header"]');
                    if (!mainHeader) return '';

                    // Preferir atributo title no vacío y que no sea solo timestamp/números
                    const withTitle = mainHeader.querySelectorAll('[title]');
                    for (const el of withTitle) {
                        const t = (el.getAttribute('title') || '').trim();
                        if (t && t.length > 1 && !/^[\\d:\\s]+(am|pm)?$/i.test(t)) return t;
                    }
                    // Fallback: primer texto significativo encontrado en el header
                    const walker = document.createTreeWalker(mainHeader, NodeFilter.SHOW_TEXT, null);
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = (node.textContent || '').trim();
                        if (t && t.length > 1 && !/^[\\d:\\s]+(am|pm)?$/i.test(t)) return t;
                    }
                    return '';
                }
            """)
            if js_text:
                return js_text.strip()
        except Exception:
            pass
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
            "footer div[aria-label^='Message ']",
            "footer div[aria-label^='Escribe a']",
            "footer div[aria-label^='Escribe un mensaje a']",
            "footer div[aria-label^='Mensaje a']",
            "footer div[aria-label^='Escreva']",
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
                        # WA Web 2026: formatos de aria-label del compositor en distintos idiomas
                        match = re.search(
                            r"(?:Type(?:\s+a)?\s+message\s+to"
                            r"|Message\s+to"
                            r"|Message\s+"
                            r"|Escribe(?:\s+un\s+mensaje)?\s+a"
                            r"|Mensaje\s+a"
                            r"|Escreva(?:\s+uma)?\s+mensagem\s+(?:para|a)"
                            r")\s*(.+?)(?:\.)?$",
                            label,
                            flags=re.I,
                        )
                        if match:
                            return match.group(1).strip()
            except Exception:
                continue
        return self._get_header_name()

    def _is_in_chat(self, contact: str) -> bool:
        """True si el chat actualmente abierto en WA Web corresponde al contacto indicado."""
        active = self._get_active_chat_from_composer()
        return _like_match(contact, active)

    def _focus_global_search(self):
        """Enfoca y limpia el cuadro de busqueda global del panel lateral de WhatsApp Web.

        Retorna el elemento del cuadro de busqueda si lo encontro, o None si fallo.
        Prueba multiples selectores en orden de confiabilidad antes de caer al
        selector por role ARIA (mas resistente a cambios de WA Web).
        """
        page = self.page
        if page is None:
            return None
        # FIX V8.9.11: Escape solo si hay resultados de busqueda activos.
        # Antes se presionaba incondicionalmente (V8.5.0). El problema: tras
        # _clear_global_search el campo queda enfocado; 60s despues Escape colapsa
        # el panel de busqueda de WA Web 2026 y todos los selectores fallan hasta
        # que el usuario interactua manualmente. Solo presionar si _is_search_active()
        # confirma que hay resultados visibles que limpiar.
        if self._is_search_active():
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
            except Exception:
                pass
        for selector in (
            '[aria-label="Search input textbox"]',
            "[data-testid='chat-list-search'] div[contenteditable='true']",
            "div[data-testid='chat-list-search']",
            "div[aria-label='Search input textbox']",
            'div[aria-label="Search or start new chat"]',
            'div[aria-label="Buscar o empezar nuevo chat"]',
            'div[aria-label="Buscar o empezar un nuevo chat"]',
        ):
            try:
                root = page.locator(selector).first
                root.wait_for(state="visible", timeout=4000)
                root.click(force=True)
                page.wait_for_timeout(100)
                # Triple click selecciona todo el contenido (mas confiable que Ctrl+A en contenteditable)
                try:
                    root.triple_click(timeout=1000)
                    page.keyboard.press("Delete")
                except Exception:
                    pass
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                return root
            except Exception:
                continue
        try:
            name_re = re.compile(r"(Buscar|Search|Search or start|Buscar o empezar)", re.I)
            root = page.get_by_role("textbox", name=name_re).first
            root.click(force=True)
            page.wait_for_timeout(100)
            try:
                root.triple_click(timeout=1000)
                page.keyboard.press("Delete")
            except Exception:
                pass
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            return root
        except Exception:
            return None

    def _clear_global_search(self) -> None:
        """Limpia el texto del cuadro de busqueda global sin cerrarlo necesariamente.

        Se usa despues de seleccionar un contacto para dejar el panel lateral
        en estado limpio y evitar que resultados previos contaminen la siguiente busqueda.
        """
        page = self.page
        if page is None:
            return
        # V8.7.4: NO presionar Escape si el compose esta visible — en WA Web 2026
        # Escape cierra el chat abierto. Solo presionar cuando no haya chat activo.
        if not self._is_compose_visible():
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(120)
            except Exception:
                pass
        for selector in (
            '[aria-label="Search input textbox"]',
            "[data-testid='chat-list-search'] div[contenteditable='true']",
            "div[data-testid='chat-list-search']",
            "div[aria-label='Search input textbox']",
        ):
            try:
                root = page.locator(selector).first
                if root.is_visible(timeout=250):
                    root.click(force=True)
                    try:
                        root.triple_click(timeout=800)
                        page.keyboard.press("Delete")
                    except Exception:
                        pass
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
        """Escribe el nombre del contacto en el buscador; intenta variantes si la primera no produce resultados.

        Variantes probadas: nombre original, tokens separados por espacio, tokens concatenados sin espacio.
        Retorna en cuanto detecta al menos un elemento de resultado visible en el panel.
        """
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
            page.wait_for_timeout(900)
            try:
                if page.get_by_role("gridcell").first.is_visible(timeout=400):
                    return
            except Exception:
                pass
            try:
                if page.locator("[data-testid='cell-frame-container']").first.is_visible(timeout=400):
                    return
            except Exception:
                pass
            try:
                if page.locator("[role='row'], [role='listitem']").first.is_visible(timeout=400):
                    return
            except Exception:
                pass
            try:
                # WA Web 2026: lista de contactos sin role especifico
                if page.locator("span[title]:visible").first.is_visible(timeout=400):
                    return
            except Exception:
                pass

    def _collect_candidates(self):
        """Recolecta elementos DOM candidatos a ser el contacto buscado, en orden de prioridad de fuente.

        Fuentes consultadas (de mayor a menor prioridad):
        1. Resultados del panel de busqueda de WA Web (data-testid especificos).
        2. role='row' o 'listitem' dentro del panel de busqueda.
        3. role='gridcell' global (lista de chats).
        4. cell-frame-container generico.
        5. span[title] como ultima opcion.
        Cada candidato se representa como (tipo, nombre, nodo, indice_base).
        """
        page = self.page
        candidates = []
        if page is None:
            return candidates

        def clean_name(raw: str) -> str:
            value = (raw or "").strip().split("\n", 1)[0]
            value = re.sub(r"\s+\d{1,2}:\d{2}\s*(am|pm|a\.m\.|p\.m\.)?$", "", value, flags=re.I)
            return value.strip()

        # WA Web 2025: resultados dentro del panel de búsqueda (prioridad alta)
        try:
            for idx, node in enumerate(page.locator(
                "[data-testid='search-composition-list'] [data-testid='cell-frame-container'],"
                " [data-testid='default-search-results'] [data-testid='cell-frame-container'],"
                " [data-testid='pane-side'] [data-testid='cell-frame-container']"
            ).all()):
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
                    candidates.append(("search-result", name, node, 50 + idx))
        except Exception:
            pass

        # WA Web 2025: role='row' o 'listitem' en panel de búsqueda
        try:
            for idx, node in enumerate(page.locator(
                "[data-testid='search-composition-list'] [role='row'],"
                " [data-testid='search-composition-list'] [role='listitem'],"
                " [data-testid='default-search-results'] [role='row'],"
                " [data-testid='default-search-results'] [role='listitem']"
            ).all()):
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
                    candidates.append(("search-listitem", name, node, 200 + idx))
        except Exception:
            pass

        try:
            for idx, node in enumerate(page.get_by_role("gridcell").all()):
                try:
                    raw = node.get_attribute("aria-label") or node.inner_text(timeout=200) or ""
                except Exception:
                    raw = ""
                name = clean_name(raw)
                if name:
                    candidates.append(("gridcell", name, node, 1000 + idx))
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
                    candidates.append(("cell", name, node, 2000 + idx))
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
                    candidates.append(("span", name, node, 3000 + idx))
        except Exception:
            pass
        return candidates

    def _rank_candidates(self, contact: str, candidates):
        """Ordena los candidatos por similitud con el nombre buscado (cobertura de tokens + posicion).

        La formula de score combina: cobertura de tokens (peso 5.0), si empieza por el
        primer token del nombre buscado (peso 1.5), penalizacion por diferencia de longitud,
        y bonificacion por posicion mas alta en la lista. Retorna lista ordenada descendente.
        """
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

    def _click_contact_js(self, contact: str) -> "dict | None":
        """Localiza el contacto en el panel lateral y devuelve las coordenadas para click real.

        Busca span[title] que coincida con el contacto dentro del panel izquierdo (#pane-side),
        filtrando spans en posicion secundaria (subtitulos de grupo como "X is also in this group"),
        luego sube el arbol DOM hasta encontrar el contenedor clickeable real.

        NO hace click en JS — solo retorna coordenadas para que page.mouse.click() en Python
        dispare la cadena completa de eventos de puntero. Un click JS adicional antes desplaza
        el elemento durante la animacion de WA Web, causando que page.mouse.click() quede fuera.

        Retorna dict con {clicked, name, method, x, y} si encontro el elemento, o None en error.
        """
        page = self.page
        if page is None:
            return None
        # POR QUE: usar JS en lugar de Playwright.click() — los data-testid cambian con cada version de WA Web;
        # el DOM-walking por role/tabindex es mas estable.
        try:
            result = page.evaluate("""
                (contact) => {
                    const tokens = contact.toLowerCase().split(/\\s+/).filter(Boolean);
                    const matches = (text) => text && tokens.length > 0 && tokens.every(t => text.toLowerCase().includes(t));

                    // Detectar si un span esta en posicion secundaria (subtitulo de grupo,
                    // mensaje previo o indicador de membresia) en lugar de ser el nombre principal.
                    // En WA Web, los subtitulos "X is also in this group" tienen ancestros con
                    // data-testid que incluyen "secondary", "msg", "last-" o "subtitle".
                    function isSecondarySpan(span) {
                        let el = span.parentElement;
                        for (let i = 0; i < 8; i++) {
                            if (!el || el === document.body) break;
                            const testid = (el.getAttribute('data-testid') || '').toLowerCase();
                            const cls = (el.getAttribute('class') || '').toLowerCase();
                            if (testid.includes('secondary') || testid.includes('subtitle') ||
                                testid.includes('msg') || testid.includes('last-') ||
                                cls.includes('secondary') || cls.includes('subtitle')) {
                                return true;
                            }
                            el = el.parentElement;
                        }
                        return false;
                    }

                    // Buscar SOLO en el panel lateral izquierdo (no en el chat abierto)
                    const pane = document.querySelector('#pane-side')
                        || document.querySelector('[data-testid="pane-side"]')
                        || document.querySelector('[aria-label="Chat list"]')
                        || document.querySelector('[aria-label="Chats"]')
                        || document.querySelector('[data-testid="chat-list"]')
                        || document.body;

                    const allSpans = Array.from(pane.querySelectorAll('span[title]')).filter(s => matches(s.title));

                    // Priorizar spans de nombre principal (no subtitulos de grupos)
                    const primarySpans = allSpans.filter(s => !isSecondarySpan(s));
                    const spansToTry = primarySpans.length > 0 ? primarySpans : allSpans;

                    for (const span of spansToTry) {
                        // Subir el arbol DOM buscando el contenedor clickeable real.
                        // Solo retornar coordenadas — el click real lo hace page.mouse.click en Python
                        // para evitar que el JS-click desplace el elemento antes de que el mouse llegue.
                        let el = span;
                        for (let i = 0; i < 12; i++) {
                            el = el.parentElement;
                            if (!el || el === document.body) break;
                            const role = el.getAttribute('role');
                            const testid = el.getAttribute('data-testid');
                            const tabidx = el.getAttribute('tabindex');
                            const tag = el.tagName;

                            if (
                                tag === 'LI' ||
                                role === 'gridcell' || role === 'row' || role === 'listitem' || role === 'option' ||
                                testid === 'cell-frame-container' || testid === 'conversation-item' ||
                                (testid && testid.includes('list-item')) ||
                                tabidx === '0'
                            ) {
                                const rect = el.getBoundingClientRect();
                                return {clicked: true, name: span.title,
                                        method: tag + (role || testid || ''),
                                        x: rect.left + rect.width / 2,
                                        y: rect.top + rect.height / 2};
                            }
                        }
                        // Fallback: subir exactamente 5 niveles desde el span
                        let parent = span;
                        for (let i = 0; i < 5; i++) {
                            if (!parent.parentElement || parent.parentElement === document.body) break;
                            parent = parent.parentElement;
                        }
                        if (parent !== span) {
                            const rect2 = parent.getBoundingClientRect();
                            return {clicked: true, name: span.title, method: 'depth-5-fallback',
                                    x: rect2.left + rect2.width / 2,
                                    y: rect2.top + rect2.height / 2};
                        }
                    }
                    return {clicked: false, reason: 'no matching span found in pane-side'};
                }
            """, contact)
            if result and result.get("clicked"):
                self.log(f"[JS-CLICK] '{result.get('name')}' clickeado via JS ({result.get('method')})")
                return result
            if result:
                self.log(f"[JS-CLICK] Sin resultado: {result.get('reason', 'unknown')}")
        except Exception as error:
            self.log(f"[JS-CLICK] Error: {error}")
        return None

    def _is_compose_visible(self) -> bool:
        """True si hay un compositor de mensajes visible (chat abierto, cualquier contacto)."""
        page = self.page
        if page is None:
            return False
        for sel in (
            "footer div[contenteditable='true']",
            "footer [data-testid='conversation-compose-box-input']",
            "#main div[contenteditable='true'][data-lexical-editor='true']",
            "#main [data-testid='conversation-compose-box-input'][contenteditable='true']",
            "#main footer",
        ):
            try:
                if page.locator(sel).first.is_visible(timeout=300):
                    return True
            except Exception:
                pass
        return False

    def _is_search_active(self) -> bool:
        """True si el panel de busqueda de WA Web tiene resultados visibles.

        Se usa para detectar si el panel de busqueda esta activo como overlay
        antes de retornar de _select_contact y antes de escribir en _send_message,
        de modo que podamos descartarlo con Escape sin cerrar el chat.
        """
        page = self.page
        if page is None:
            return False
        for sel in (
            "[data-testid='search-composition-list']",
            "[data-testid='default-search-results']",
            "[data-testid='pane-side'] [role='listbox']",
        ):
            try:
                if page.locator(sel).first.is_visible(timeout=200):
                    return True
            except Exception:
                continue
        for sel in (
            "[data-testid='chat-list-search'] div[contenteditable='true']",
            '[aria-label="Search input textbox"]',
        ):
            try:
                node = page.locator(sel).first
                if node.is_visible(timeout=200):
                    if (node.inner_text(timeout=200) or "").strip():
                        return True
            except Exception:
                continue
        return False

    def _wait_header(self, contact: str, timeout_ms: int = 9000) -> bool:
        """Espera hasta que el header de WA Web confirme que el chat del contacto esta abierto.

        Si los selectores del header no pueden leer el nombre (WA Web actualizo su estructura),
        acepta el chat como correcto si el compose box es visible: es mejor enviar el mensaje
        que regresar al modo busqueda, que cierra el chat definitivamente.
        V8.9.9: deteccion de compose en 1-pass (antes 2-pass) para mayor velocidad en WA Web 2026.
        """
        end_time = time.time() + (timeout_ms / 1000.0)
        while time.time() < end_time:
            if self._is_in_chat(contact):
                return True
            # V8.9.9: compose visible => chat abierto. Sin 2-pass para capturar apertura
            # en WA Web 2026 donde el compositor puede quedar brevemente oculto entre ciclos.
            if self._is_compose_visible():
                self.log(f"[WAIT-HEADER] Compose visible, aceptando chat.")
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

            # V8.7.3 — Estrategia 1: teclado (ArrowDown + Enter).
            # No depende de coordenadas DOM ni de selectores que cambian con WA Web.
            # ArrowDown mueve el foco al primer resultado de busqueda; Enter lo abre.
            # Es el comportamiento exacto de un usuario tecladista y WA Web 2026 lo soporta.
            try:
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(400)
                page.keyboard.press("Enter")
                page.wait_for_timeout(1200)
                # Confirmacion rapida via compose box (mas fiable que header en WA Web 2026)
                if self._is_compose_visible():
                    # V8.10.0: descartar panel de busqueda si sigue activo como overlay.
                    # En WA Web 2026 el panel puede persistir sobre el chat recien abierto;
                    # si no lo descartamos aqui, _send_message recibe el Enter como
                    # "abrir resultado de busqueda" en lugar de "enviar mensaje".
                    if self._is_search_active():
                        try:
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(350)
                        except Exception:
                            pass
                    self.log(f"Contacto '{contact}' abierto via teclado (compose).")
                    return True
                if self._wait_header(contact, timeout_ms=3000):
                    if self._is_search_active():
                        try:
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(350)
                        except Exception:
                            pass
                    self.log(f"Contacto '{contact}' abierto via teclado (header).")
                    return True
                # V8.9.9: WA Web 2026 puede mantener el panel de busqueda como overlay
                # sobre el chat recien abierto, ocultando el compositor. Escape descarta
                # el overlay; si el chat ya estaba abierto, el compositor queda visible.
                # Si no habia chat, Escape cierra el panel y Strategy 2 opera sobre la
                # lista de chats recientes (donde el contacto suele estar visible).
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)
                except Exception:
                    pass
                if self._is_compose_visible():
                    self.log(f"Contacto '{contact}' confirmado via teclado (compose post-Escape).")
                    return True
                if self._wait_header(contact, timeout_ms=1500):
                    self.log(f"Contacto '{contact}' confirmado via teclado (header post-Escape).")
                    return True
                self.log("[KEYBOARD-1] Sin confirmacion. Probando mouse.click.")
            except Exception:
                pass

            # V8.7.3 — Estrategia 2: JS localiza coordenadas + mouse.click limpio.
            # Sin blur previo al click: el blur.() oculta los resultados de busqueda
            # ANTES de que el click llegue al elemento, haciendo que las coordenadas
            # apunten al area vacia que quedo tras desaparecer el panel de resultados.
            js_result = self._click_contact_js(contact)
            if js_result and js_result.get("clicked"):
                cx = js_result.get("x", 0)
                cy = js_result.get("y", 0)
                self.log(f"[JS-LOCATE] '{js_result.get('name')}' en ({cx:.0f},{cy:.0f}) via {js_result.get('method')}")
                if cx and cy:
                    try:
                        page.mouse.click(cx, cy)
                        # Detectar apertura rapido: si compose aparece en <1200ms, confirmar
                        # SIN esperar el header (que en WA Web 2026 puede tardar mas).
                        page.wait_for_timeout(1200)
                        if self._is_compose_visible():
                            self.log(f"Contacto '{contact}' abierto via mouse.click (compose).")
                            return True
                    except Exception as _me:
                        self.log(f"[MOUSE-CLICK] Error: {_me}")
                if self._wait_header(contact, timeout_ms=5000):
                    self.log(f"Contacto '{contact}' abierto via mouse.click (header).")
                    return True
                self.log("[MOUSE-CLICK] Sin confirmacion tras mouse.click.")

            # V8.7.3 — Estrategia 3: candidatos Playwright + teclado de respaldo.
            # Solo llegar aqui si las dos estrategias anteriores fallaron y el compose
            # NO esta visible (para no interrumpir un chat que ya este abierto).
            if self._is_compose_visible():
                self.log(f"Compose visible al inicio de fallback — retornando True.")
                return True

            # Fallback Playwright: click directo en candidatos rankeados
            ranked = self._rank_candidates(contact, self._collect_candidates())

            if not ranked:
                self._clear_global_search()
                raise TimeoutError(f"Sin candidatos en busqueda para contacto: {contact!r}")

            for attempt, (score, kind, name, node, idx) in enumerate(ranked[:4], start=1):
                self.log(f"[LIKE] intento {attempt}: '{name}' (score={score:.2f}, kind={kind})")
                try:
                    node.scroll_into_view_if_needed(timeout=1200)
                except Exception:
                    pass
                try:
                    target = node
                    if kind in ("span",):
                        for ancestor_selector in (
                            "xpath=ancestor::*[@data-testid='cell-frame-container' or @role='gridcell' or @role='row' or @role='listitem' or @tabindex='0'][1]",
                        ):
                            try:
                                candidate = node.locator(ancestor_selector).first
                                candidate.wait_for(state="attached", timeout=400)
                                target = candidate
                                break
                            except Exception:
                                pass
                    target.click(timeout=3000, force=True)
                except Exception:
                    try:
                        node.click(timeout=3000, force=True)
                    except Exception:
                        continue
                page.wait_for_timeout(1000)
                if self._is_compose_visible():
                    self.log(f"Contacto seleccionado por coincidencia LIKE (compose): {name}")
                    return True
                if self._wait_header(contact, timeout_ms=4000):
                    self.log(f"Contacto seleccionado por coincidencia LIKE: {name}")
                    return True

            # Fallback final de teclado — solo si compose NO esta visible
            if not self._is_compose_visible():
                try:
                    page.keyboard.press("ArrowDown")
                    page.wait_for_timeout(400)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)
                    if self._is_compose_visible():
                        self.log(f"Contacto seleccionado via teclado final (compose): {contact}")
                        return True
                    if self._wait_header(contact, timeout_ms=4000):
                        self.log(f"Contacto seleccionado via teclado (ArrowDown+Enter): {contact}")
                        return True
                except Exception:
                    pass

            self._clear_global_search()
            if self._wait_header(contact, timeout_ms=5000):
                self.log(f"Contacto seleccionado (confirmacion post-click): {contact}")
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
            # V8.7.4: _is_compose_visible() como fallback primario — mas fiable que
            # _is_in_chat en WA Web 2026 donde los selectores del header cambian.
            # Si compose esta visible, asumimos que el chat ya esta abierto.
            if self._is_in_chat(contact) or self._is_compose_visible():
                return True
            self.log(
                f"[ensure_chat_target] actual='{self._get_active_chat_from_composer()}', objetivo='{contact}', reintento {idx + 1}/{attempts}"
            )
            if not self._select_contact(contact):
                time.sleep(0.2)
        return self._is_in_chat(contact) or self._is_compose_visible()

    def _get_composer_for_contact(self):
        """Localiza el elemento contenteditable del compositor de mensajes en el footer.

        Intenta selectores en orden de especificidad descendente: desde aria-label exacto
        hasta el contenteditable generico del footer. Retorna una tupla (node, container)
        donde node es el parrafo interno (si existe) y container es el div raiz.
        """
        page = self.page
        last_error = None
        for selector in (
            "footer div[aria-label='Type a message']",
            "footer div[aria-label='Escribe un mensaje']",
            "footer div[aria-label^='Type']",
            "footer div[aria-label^='Escribe']",
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
        """Activa el foco del compositor y asegura que este listo para recibir texto.

        Cierra menus de adjuntos, hace scroll al nodo, lo enfoca via JS y via click,
        y dispara un Space+Backspace para despertar el editor Lexical de WA Web (que
        puede estar en estado inerte si no recibio interaccion previa del usuario).
        """
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
        """Cuenta los mensajes salientes visibles en el chat actual (para detectar si se envio uno nuevo)."""
        page = self.page
        if page is None:
            return 0
        for selector in (
            # WA Web 2026: data-id comienza con 'true_' en mensajes salientes
            "[data-id^='true_']",
            "[data-testid='msg-container'][data-id^='true_']",
            # Versiones anteriores (clase CSS)
            "div.message-out",
            "[data-testid='msg-container'].message-out",
            "[class*='message-out']",
        ):
            try:
                count = int(page.locator(selector).count())
                if count > 0:
                    return count
            except Exception:
                continue
        return 0

    def _wait_outgoing_increment(self, base_count: int, timeout_ms: int = 6000) -> bool:
        """Espera a que el contador de mensajes salientes aumente respecto al valor base.

        Complementa a _verify_message_sent para casos en que el texto del mensaje
        no aparece en pantalla de inmediato (mensajes largos o con formato especial).
        """
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
        """Verifica que el texto del mensaje aparezca en los mensajes salientes del chat.

        Normaliza el texto antes de comparar para tolerar diferencias de saltos de linea.
        Para textos largos (>= 6 chars) acepta coincidencia parcial (uno contiene al otro).
        """
        page = self.page
        end = time.time() + timeout_ms / 1000.0
        text = self._normalized_text(text)
        while time.time() < end:
            for selector in (
                # WA Web 2026: data-id^='true_' para mensajes salientes
                "[data-id^='true_'] span.selectable-text",
                "[data-id^='true_'] [data-lexical-text='true']",
                "[data-id^='true_'] span[dir='ltr']",
                # Selectores clasicos (versiones anteriores)
                "div.message-out span.selectable-text",
                "div.message-out [data-testid='msg-text'] span",
                "div.message-out [data-lexical-text='true']",
                "[class*='message-out'] span.selectable-text",
                "[class*='message-out'] [data-lexical-text='true']",
            ):
                try:
                    nodes = page.locator(selector).all()
                except Exception:
                    nodes = []
                for node in nodes:
                    try:
                        if not node.is_visible():
                            continue
                        candidate = self._normalized_text(node.inner_text())
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
        """Normaliza saltos de linea y espacios multiples para comparaciones de texto."""
        return re.sub(r"\s+", " ", re.sub(r"\r\n|\r", "\n", value or "")).strip()

    def _read_composer_text(self, node, container) -> str:
        """Lee el texto actual del compositor (prueba node y container como fallback)."""
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
        """Espera hasta que el compositor quede vacio (indica que el mensaje fue enviado)."""
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
        # V8.10.0: descartar panel de busqueda si sigue activo antes de escribir.
        # En WA Web 2026 el panel intercepta el Enter del envio si no se descarta.
        try:
            if self._is_search_active():
                self.log("[SEND] Panel de busqueda activo detectado — descartando con Escape.")
                page.keyboard.press("Escape")
                page.wait_for_timeout(350)
        except Exception:
            pass
        normalized_text = re.sub(r"\r\n|\r", "\n", text).strip()

        try:
            node, container = self._get_composer_for_contact()
            # V8.7.4: _clear_global_search() removida aqui — presionaba Escape que en
            # WA Web 2026 cierra el chat recien abierto. La busqueda ya se limpia
            # cuando WA Web abre el chat. Se limpiara despues del envio exitoso.
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
            # Intentar con data-testid primero (mas confiable en WA Web 2025)
            # force=True: ignora overlays que puedan cubrir el boton (WA Web 2026)
            for _send_sel in (
                "button[data-testid='send']",
                "span[data-testid='send']",
                "[data-testid='compose-btn-send']",
            ):
                try:
                    _sb = page.locator(_send_sel).first
                    if _sb.is_visible(timeout=600):
                        _sb.click(timeout=1500, force=True)
                        sent = True
                        break
                except Exception:
                    continue
            # Fallback por rol ARIA (compatibilidad anterior)
            if not sent:
                try:
                    send_btn = page.get_by_role("button", name=re.compile(r"Enviar|Send", re.I)).first
                    if send_btn.is_visible(timeout=700):
                        send_btn.click(timeout=1500, force=True)
                        sent = True
                except Exception:
                    pass
            # V8.10.0: fallback via JS click — llega directo al boton ignorando overlays
            if not sent:
                try:
                    _js_clicked = page.evaluate("""
                        () => {
                            const selectors = [
                                "button[data-testid='send']",
                                "span[data-testid='send']",
                                "[data-testid='compose-btn-send']",
                                "button[aria-label='Send']",
                                "button[aria-label='Enviar']",
                                "button[aria-label='Enviar mensaje']"
                            ];
                            for (const sel of selectors) {
                                const btn = document.querySelector(sel);
                                if (btn) { btn.click(); return true; }
                            }
                            return false;
                        }
                    """)
                    if _js_clicked:
                        sent = True
                        self.log("[SEND] Boton enviado via JS click fallback.")
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

            # V8.9.12: Verificacion 1 — compositor limpiado (rapida, siempre funciona en WA Web 2026).
            # _verify_message_sent y _wait_outgoing_increment usan 'div.message-out' que no existe
            # en WA Web 2026; ambas siempre hacian timeout (9s + 6s = 15s perdidos por envio).
            # _wait_composer_cleared detecta el envio en ~1-2s sin depender de clases CSS.
            if sent and self._wait_composer_cleared(node, container, timeout_ms=4000):
                self.log(f"Mensaje enviado a '{contact}' (compositor limpiado tras envio).")
                self._clear_global_search()
                return True

            # Verificacion 2 — texto en mensajes salientes (fallback; timeouts reducidos).
            if self._verify_message_sent(normalized_text, timeout_ms=4000):
                self.log(f"Mensaje enviado a '{contact}'.")
                self._clear_global_search()
                return True

            # Verificacion 3 — incremento de salientes.
            if self._wait_outgoing_increment(outgoing_before, timeout_ms=2000):
                self.log(f"Mensaje enviado a '{contact}' (verificacion por incremento de mensajes salientes).")
                self._clear_global_search()
                return True

            # Fallback anti-duplicados: si accion de envio fue ejecutada y el compositor quedo vacio, no reintentar.
            post_send_text = self._read_composer_text(node, container)
            if sent and not post_send_text and (pre_send_text or normalized_text):
                self.log(
                    f"Mensaje enviado a '{contact}' (confirmacion por compositor vacio; se evita reintento duplicado)."
                )
                self._clear_global_search()
                return True

            self.status("No se verifico el envio en pantalla.")
            return False
        except Exception as error:
            self.status("Error al enviar mensaje.")
            self.log(f"Error al enviar a '{contact}': {error}")
            return False

    def _close_our_pages(self) -> None:
        """Cierra solo las paginas que el worker abrio (no cierra pestanas del usuario)."""
        for page in list(self._opened_pages):
            try:
                page.close()
            except Exception:
                pass
        self._opened_pages.clear()

    def _kill_process_tree(self) -> None:
        """Mata los procesos del browser que el worker lanzo (no afecta instancias preexistentes).

        En Windows usa taskkill /T /F para matar el arbol completo de procesos hijo.
        En Unix usa SIGTERM seguido de terminate() en el Popen. Solo actua sobre los PIDs
        registrados en _launched_pids; nunca toca instancias del browser ya existentes
        antes de que el worker iniciara.
        """
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
