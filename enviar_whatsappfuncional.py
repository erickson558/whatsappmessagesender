# -*- coding: utf-8 -*-
# Versión 7.3.6

import os, re, json, subprocess, time, requests, tkinter as tk, threading, calendar, queue, glob, sys, unicodedata
from tkinter import ttk, filedialog
from tkcalendar import DateEntry
from datetime import datetime, timedelta

# ================== ROTACIÓN DE LOGS ==================
def _rotate_logs(pattern):
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for f in files[3:]:
        try: os.remove(f)
        except Exception: pass

# ================= SPLASH =================
def show_splash():
    s = tk.Toplevel()
    s.overrideredirect(True)
    s.attributes('-topmost', True)
    w, h = 420, 220
    x = s.winfo_screenwidth()//2 - w//2
    y = s.winfo_screenheight()//2 - h//2
    s.geometry(f"{w}x{h}+{x}+{y}")
    s.configure(bg="white")
    frm = tk.Frame(s, bg="white"); frm.pack(expand=True, fill="both")
    tk.Label(frm, text="Cargando aplicación...", font=("Helvetica",16), bg="white").pack(pady=14)
    pb = ttk.Progressbar(frm, orient="horizontal", mode="determinate", length=300); pb.pack(pady=10)
    tk.Label(frm, text="Inicializando GUI y componentes...", bg="white").pack()
    s.update()
    for i in range(0, 101, 5):
        pb['value'] = i
        s.update_idletasks()
        time.sleep(0.02)
    return s

# ================= Normalización LIKE =================
def _normalize_like(s: str) -> str:
    if not s: return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("’","'")
    s = re.sub(r"[^a-z0-9\s@.+#'_-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _tokens(s: str):
    s = _normalize_like(s)
    return [t for t in s.split() if t]

def _coverage_score(needle: str, cand: str) -> float:
    ta, hb = _tokens(needle), _tokens(cand)
    if not ta or not hb: return 0.0
    hit = sum(1 for t in ta if t in hb)
    return hit / len(ta)

def _like_match(needle: str, cand: str) -> bool:
    ta, hb = _tokens(needle), _tokens(cand)
    return all(t in hb for t in ta) if ta else False

# ================= GLOBALS =================
status_label = None
log_text = None
scheduled_messages, scheduled_after_ids = [], []
selected_contact = ""
app_quitting = False
clock_after_id = None

_rotate_logs("logaplicacion*.txt")
_rotate_logs("logmensajes*.txt")
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
app_log_filename = f"logaplicacion{log_timestamp}.txt"
msg_log_filename = f"logmensajes{log_timestamp}.txt"
app_log_file = open(app_log_filename, "a", encoding="utf-8")
msg_log_file = open(msg_log_filename, "a", encoding="utf-8")

# ================= CONFIG =================
CONFIG_FILE = "config.json"

def deep_merge(dst, src):
    for k,v in src.items():
        if isinstance(v, dict):
            node = dst.setdefault(k, {})
            if isinstance(node, dict): deep_merge(node, v)
            else: dst[k]=v
        else:
            dst.setdefault(k, v)
    return dst

default_config = {
    "global": {
        "browser": "Opera",
        "brave_path": "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe",
        "opera_path": "C:\\Program Files\\Opera\\opera.exe",
        "remote_debugging_port": 9222,
        "debug_port_timeout": 60,
        "cdp_timeout": 90000,
        "cdp_retries": 3,
        "extra_wait": 5,
        "num_messages_group1": 4,
        "num_messages_group2": 4,
        "num_messages_group3": 4,
        "num_messages_group4": 4,
        "window_geometry": "1250x900",
        "window_state": "normal",
        "window_x": None,
        "window_y": None,
        "version": "7.3.6"
    },
    "messages_group1": [ { "contact":"","message":"","date":"","hour":"","minute":"","ampm":"","repeat":"Ninguno","send":False,"days":[] } for _ in range(4) ],
    "messages_group2": [ { "contact":"","message":"","date":"","hour":"","minute":"","ampm":"","repeat":"Ninguno","send":False,"days":[] } for _ in range(4) ],
    "messages_group3": [ { "contact":"","message":"","date":"","hour":"","minute":"","ampm":"","repeat":"Ninguno","send":False,"days":[] } for _ in range(4) ],
    "messages_group4": [ { "contact":"","message":"","date":"","hour":"","minute":"","ampm":"","repeat":"Ninguno","send":False,"days":[] } for _ in range(4) ],
}

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(default_config,f,indent=4,ensure_ascii=False)
with open(CONFIG_FILE,"r",encoding="utf-8") as f: loaded = json.load(f)
config = deep_merge(loaded, default_config)
with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)

global_config = config["global"]
browser_choice = global_config.get("browser","Opera")
brave_path = global_config.get("brave_path")
opera_path = global_config.get("opera_path")
remote_port = global_config.get("remote_debugging_port")
debug_port_timeout = global_config.get("debug_port_timeout")
cdp_timeout = global_config.get("cdp_timeout")
cdp_retries = global_config.get("cdp_retries")
extra_wait = global_config.get("extra_wait")
num_messages_group1 = global_config.get("num_messages_group1",4)
num_messages_group2 = global_config.get("num_messages_group2",4)
num_messages_group3 = global_config.get("num_messages_group3",4)
num_messages_group4 = global_config.get("num_messages_group4",4)
window_geometry = global_config.get("window_geometry","1250x900")
window_state = global_config.get("window_state","normal")
window_x = global_config.get("window_x", None)
window_y = global_config.get("window_y", None)
__version__ = global_config.get("version","7.3.6")

def _ensure_len(lst, n):
    lst=(lst or [])[:n]
    while len(lst)<n:
        lst.append({"contact":"","message":"","date":"","hour":"","minute":"","ampm":"","repeat":"Ninguno","send":False,"days":[]})
    return lst

messages_config_group1 = _ensure_len(config.get("messages_group1"), num_messages_group1)
messages_config_group2 = _ensure_len(config.get("messages_group2"), num_messages_group2)
messages_config_group3 = _ensure_len(config.get("messages_group3"), num_messages_group3)
messages_config_group4 = _ensure_len(config.get("messages_group4"), num_messages_group4)
day_names = ["Lun","Mar","Mie","Jue","Vie","Sab","Dom"]

# ================= UI-safe =================
def _ui_call(fn,*args,**kwargs):
    if app_quitting: return
    if 'root' in globals() and root and threading.current_thread() is not threading.main_thread():
        try: root.after(0, lambda: (None if app_quitting else fn(*args,**kwargs)))
        except tk.TclError: pass
    else:
        try: fn(*args,**kwargs)
        except tk.TclError: pass

def log_message(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} - {msg}\n"
    def _do():
        if log_text is not None and log_text.winfo_exists():
            log_text.insert(tk.END, line); log_text.see(tk.END)
        else:
            print(line, end="")
        app_log_file.write(line); app_log_file.flush()
    _ui_call(_do)

def update_status(text):
    def _do():
        if status_label is not None and status_label.winfo_exists():
            status_label.config(text="Estado: "+text)
        log_message(text)
    _ui_call(_do)

def log_message_sent(contact, message_text):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} - Mensaje enviado a {contact}: {message_text}\n"
    msg_log_file.write(line); msg_log_file.flush()

# ================= Helpers procesos =================
def _pids_by_name_win(name):
    try:
        out = subprocess.run(
            ["powershell","-NoProfile","-Command", f"(Get-Process -Name '{name}' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id) -join ','"],
            capture_output=True, text=True, timeout=5
        )
        txt = (out.stdout or "").strip()
        return set(int(x) for x in txt.split(",") if x.strip().isdigit())
    except Exception:
        return set()

def _existing_pids(browser_exe):
    if os.name != "nt":
        try:
            out = subprocess.run(["pgrep","-x", browser_exe], capture_output=True, text=True, timeout=5)
            return set(int(x) for x in (out.stdout or "").split() if x.isdigit())
        except Exception:
            return set()
    base = os.path.basename(browser_exe).lower()
    name = "opera" if "opera" in base else ("brave" if "brave" in base else base.replace(".exe",""))
    return _pids_by_name_win(name)

# ================= Report callback exception =================
def _swallow_tk_errors_during_shutdown(exc, val, tb):
    import tkinter as _tk
    if app_quitting and isinstance(val, _tk.TclError): return
    import traceback as _traceback
    _traceback.print_exception(exc, val, tb)

# ================= Worker Playwright =================
class BrowserWorker(threading.Thread):
    def __init__(self, remote_port, debug_port_timeout, cdp_timeout, cdp_retries, extra_wait,
                 brave_path, opera_path, browser_choice_getter, log_fn, status_fn):
        super().__init__(daemon=True)
        self.remote_port = remote_port
        self.debug_port_timeout = debug_port_timeout
        self.cdp_timeout = cdp_timeout
        self.cdp_retries = cdp_retries
        self.extra_wait = extra_wait
        self.brave_path = brave_path
        self.opera_path = opera_path
        self.browser_choice_getter = browser_choice_getter
        self.log = log_fn
        self.status = status_fn
        self.req_q = queue.Queue()
        self._stop = threading.Event()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.browser_process = None
        self.browser_exec = None
        self._baseline_pids = set()
        self._we_started = False
        self._opened_pages = []
        self._last_opened_chat_label = ""

    def run(self):
        while not self._stop.is_set():
            try:
                cmd, kwargs, done, out = self.req_q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if cmd=="ensure": out["result"]=self._ensure_browser()
                elif cmd=="open_new_chat": out["result"]=self._open_new_chat()
                elif cmd=="select_contact": out["result"]=self._select_contact(kwargs["contact"])
                elif cmd=="send_message": out["result"]=self._send_message(kwargs["text"])
                elif cmd=="shutdown": self._shutdown(); out["result"]=True; self._stop.set()
                else: out["error"]=f"Comando desconocido: {cmd}"
            except Exception as e:
                out["error"]=str(e)
            finally:
                done.set()
        self._shutdown()

    def call(self, cmd, **kwargs):
        done = threading.Event(); out={}
        self.req_q.put((cmd, kwargs, done, out)); done.wait()
        if "error" in out: raise RuntimeError(out["error"])
        return out.get("result")

    # ---------- CDP / Navegador ----------
    def _wait_for_debug_port(self, timeout=None):
        timeout = timeout or self.debug_port_timeout
        url = f"http://127.0.0.1:{self.remote_port}/json/version"
        start = time.time()
        while time.time()-start < timeout:
            try:
                r = requests.get(url)
                if r.status_code==200: return True
            except Exception: pass
            time.sleep(1)
        return False

    def _launch_browser_proc(self):
        choice = self.browser_choice_getter()
        exec_path = self.opera_path if choice=="Opera" else self.brave_path
        self.browser_exec = exec_path
        if not exec_path:
            self.status(f"No se ha configurado la ruta para {choice}."); return False
        self._baseline_pids = _existing_pids(exec_path)
        self.status(f"Lanzando {choice} con ejecutable: {exec_path}")
        try:
            self.browser_process = subprocess.Popen(
                [exec_path, f"--remote-debugging-port={self.remote_port}"],
                shell=False
            )
        except Exception as e:
            self.log(f"Fallo al lanzar {choice}: {e}")
            return False
        ok = self._wait_for_debug_port(self.debug_port_timeout)
        if not ok:
            self.log(f"Error: No se detectó CDP en puerto {self.remote_port}.")
        post = _existing_pids(exec_path)
        self._we_started = (len(self._baseline_pids) == 0 and len(post) > 0)
        return ok

    def _connect_over_cdp(self):
        from playwright.sync_api import sync_playwright
        if self.playwright is None: self.playwright = sync_playwright().start()
        for attempt in range(self.cdp_retries):
            try:
                self.browser = self.playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{self.remote_port}", timeout=self.cdp_timeout
                )
                self.log(f"Conexión CDP establecida en el intento {attempt+1}.")
                break
            except Exception as e:
                self.log(f"Intento {attempt+1}/{self.cdp_retries} - Error CDP: {e}")
                time.sleep(5)
        if self.browser is None: return False

        self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        self.page = None
        for p in self.context.pages:
            if "web.whatsapp.com" in p.url:
                self.page = p
                break
        if not self.page:
            self.page = self.context.new_page()
            self._opened_pages.append(self.page)
            self.page.goto("https://web.whatsapp.com/", timeout=60000)
            self.log("Abierta pestaña WhatsApp Web. Escanea QR si aplica.")
        return True

    def _wait_app_ready(self, total_timeout_ms=90000):
        p = self.page
        start = time.time()
        while (time.time() - start) * 1000 < total_timeout_ms:
            try:
                for ls in ("load","domcontentloaded","networkidle"):
                    try: p.wait_for_load_state(ls, timeout=2500)
                    except Exception: pass
                grid_ok = False
                try: grid_ok = p.get_by_role("grid").first.is_visible(timeout=800)
                except Exception: grid_ok = False
                sb_ok = False
                try:
                    sb_ok = p.locator('[aria-label="Search input textbox"]').first.is_visible(timeout=800)
                except Exception:
                    try:
                        name_re = re.compile(r"(Buscar|Search|Search or start|Cuadro de texto para ingresar|Cuadro de texto|Buscar o empezar)", re.I)
                        sb_ok = p.get_by_role("textbox", name=name_re).first.is_visible(timeout=800)
                    except Exception:
                        try: sb_ok = p.locator("[data-testid='chat-list-search'] div[contenteditable='true']").first.is_visible(timeout=800)
                        except Exception: sb_ok = False
                if grid_ok and sb_ok: return True
            except Exception: pass
            p.wait_for_timeout(400)
        return False

    def _ensure_whatsapp_loaded(self, total_timeout=90000):
        p = self.page
        try: p.wait_for_load_state("load", timeout=min(15000,total_timeout))
        except Exception: pass
        return self._wait_app_ready(total_timeout_ms=total_timeout)

    def _ensure_browser(self):
        if self.browser is None or self.page is None:
            if not self._launch_browser_proc(): return False
            time.sleep(self.extra_wait)
            if not self._connect_over_cdp(): return False
        ok = self._ensure_whatsapp_loaded(total_timeout=90000)
        if not ok:
            self.status("Error: WhatsApp Web no disponible tras 90s.")
            return False
        return True

    def _dismiss_overlays(self):
        p = self.page
        try: p.keyboard.press("Escape"); p.wait_for_timeout(120)
        except Exception: pass

    def _close_attach_menu(self):
        p = self.page
        try:
            menu = p.locator("[data-testid='attach-menu'], [role='menu']").first
            if menu.is_visible(timeout=300):
                self.log("Menú de adjuntos visible. Cerrando con Escape.")
                p.keyboard.press("Escape")
                p.wait_for_timeout(150)
        except Exception:
            pass

    # ---------- HEADER / COMPOSITOR ----------
    def _get_header_name(self) -> str:
        p = self.page
        for sel in (
            "header [data-testid='conversation-info-header'] span[title]",
            "header span[title]"
        ):
            try:
                head = p.locator(sel).first
                if head.is_visible(timeout=600):
                    return (head.get_attribute("title") or head.inner_text(timeout=300) or "").strip()
            except Exception: pass
        try:
            h = p.get_by_role("heading").first
            if h.is_visible(timeout=600):
                return (h.inner_text(timeout=300) or "").strip()
        except Exception: pass
        try:
            return (p.locator("header").inner_text(timeout=500) or "").strip().split("\n",1)[0]
        except Exception: pass
        return ""

    def _get_active_chat_from_composer(self) -> str:
        p = self.page
        for sel in (
            "footer div[aria-label^='Type to']",
            "footer div[aria-label^='Type a message to']",
            "footer div[aria-label^='Escribe a']",
            "footer [data-testid='conversation-compose-box-input'][contenteditable='true']",
            "footer div[contenteditable='true'][data-lexical-editor='true']",
            "footer div[role='textbox'][contenteditable='true'][aria-multiline='true']",
            "footer div[contenteditable='true'][data-tab]",
            "footer div[contenteditable='true']",
        ):
            try:
                el = p.locator(sel).last
                if el.is_visible(timeout=600):
                    lbl = el.get_attribute("aria-label") or ""
                    if lbl:
                        m = re.search(r"(?:Type(?: a message)? to|Escribe a)\s+(.+?)(?:\.)?$", lbl, flags=re.I)
                        if m: return m.group(1).strip()
            except Exception: pass
        return self._get_header_name()

    def _is_in_chat(self, contact: str) -> bool:
        active = self._get_active_chat_from_composer()
        return _like_match(contact, active)

    # ---------- SEARCH helpers ----------
    def _focus_global_search(self):
        p = self.page
        try:
            root = p.locator('[aria-label="Search input textbox"]').first
            root.wait_for(state="visible", timeout=4000)
            root.click(force=True)
            try: p.locator(".selectable-text").first.click(force=True)
            except Exception: pass
            p.keyboard.press("Control+A"); p.keyboard.press("Delete"); p.keyboard.press("Backspace")
            return root
        except Exception:
            pass
        try:
            root = p.locator("[data-testid='chat-list-search'] div[contenteditable='true']").first
            root.wait_for(state="visible", timeout=4000)
            root.click(force=True)
            try: root.locator("p.selectable-text.copyable-text, p").last.click(force=True)
            except Exception: pass
            p.keyboard.press("Control+A"); p.keyboard.press("Delete"); p.keyboard.press("Backspace")
            return root
        except Exception:
            try:
                name_re = re.compile(r"(Buscar|Search|Search or start|Cuadro de texto para ingresar|Cuadro de texto|Buscar o empezar)", re.I)
                root = p.get_by_role("textbox", name=name_re).first
                root.click(force=True)
                try: root.get_by_role("paragraph").first.click(force=True)
                except Exception:
                    try: root.locator("p").last.click(force=True)
                    except Exception: pass
                p.keyboard.press("Control+A"); p.keyboard.press("Delete"); p.keyboard.press("Backspace")
                return root
            except Exception:
                return None

    def _clear_global_search(self):
        p = self.page
        try:
            root = p.locator('[aria-label="Search input textbox"]').first
            if root.is_visible(timeout=300):
                root.click(force=True)
                p.keyboard.press("Control+A"); p.keyboard.press("Delete"); p.keyboard.press("Backspace")
                # IMPORTANT: blur to avoid swallowing Enter
                try: p.evaluate("el=>el.blur()", root)
                except Exception: pass
                return
        except Exception: pass
        try:
            root = p.locator("[data-testid='chat-list-search'] div[contenteditable='true']").first
            if root.is_visible(timeout=300):
                root.click(force=True)
                p.keyboard.press("Control+A"); p.keyboard.press("Delete"); p.keyboard.press("Backspace")
                try: p.evaluate("el=>el.blur()", root)
                except Exception: pass
        except Exception: pass

    def _type_search_variants(self, contact: str):
        p = self.page
        variants = [contact]
        toks = _tokens(contact)
        if toks:
            variants.append(" ".join(toks))
            variants.append("".join(toks))
        for v in variants:
            p.keyboard.press("Control+A"); p.keyboard.press("Delete"); p.keyboard.press("Backspace")
            for ch in v: p.keyboard.type(ch, delay=10)
            p.wait_for_timeout(600)
            # si hay resultados, devolvemos
            try:
                if p.get_by_role("gridcell").first.is_visible(timeout=400):
                    return True
            except Exception: pass
            try:
                if p.locator("[data-testid='cell-frame-container']").first.is_visible(timeout=400):
                    return True
            except Exception: pass
        return True

    def _collect_candidates(self):
        p = self.page; candidates=[]
        def _clean_name(raw: str) -> str:
            raw = (raw or "").strip().split("\n",1)[0]
            raw = re.sub(r"\s+\d{1,2}:\d{2}\s*(am|pm|a\.m\.|p\.m\.)?$", "", raw, flags=re.I)
            return raw.strip()
        # gridcell
        try:
            cells = p.get_by_role("gridcell").all()
            for idx, el in enumerate(cells):
                try: raw = el.get_attribute("aria-label") or el.inner_text(timeout=200) or ""
                except Exception: raw = ""
                nm = _clean_name(raw)
                if nm: candidates.append(("gridcell", nm, el, idx))
        except Exception: pass
        # cell-frame-container
        try:
            cells = p.locator("[data-testid='cell-frame-container']").all()
            for j, el in enumerate(cells):
                try:
                    name_el = el.locator("span[title]").first
                    raw = name_el.get_attribute("title") or name_el.inner_text(timeout=200) or ""
                except Exception:
                    try: raw = el.get_attribute("aria-label") or el.inner_text(timeout=200) or ""
                    except Exception: raw = ""
                nm = _clean_name(raw)
                if nm: candidates.append(("cell", nm, el, 1000+j))
        except Exception: pass
        # spans sueltos (por si acaso)
        try:
            spans = p.locator("span[title]").all()
            base = 2000
            for k, sp in enumerate(spans):
                try: raw = sp.get_attribute("title") or sp.inner_text(timeout=200) or ""
                except Exception: raw = ""
                nm = _clean_name(raw)
                if nm:
                    candidates.append(("span", nm, sp, base+k))
        except Exception: pass
        return candidates

    def _rank_candidates(self, contact: str, candidates):
        toks = _tokens(contact)
        first = toks[0] if toks else ""
        ranked = []
        for kind, nm, el, idx in candidates:
            cov = _coverage_score(contact, nm)
            starts = 1.0 if (first and _normalize_like(nm).startswith(first)) else 0.0
            len_penalty = abs(len(_normalize_like(nm)) - len(_normalize_like(contact)))
            score = cov*5.0 + starts*1.5 + max(0, 3 - len_penalty*0.2) + max(0, 1.0 - idx*0.01)
            ranked.append((score, kind, nm, el, idx))
        ranked.sort(key=lambda x:(-x[0], x[4]))
        return ranked

    def _wait_header(self, contact, timeout_ms=9000):
        end = time.time() + timeout_ms/1000.0
        while time.time() < end:
            if self._is_in_chat(contact):
                return True
            self.page.wait_for_timeout(140)
        return False

    # ---------- SELECCIÓN SOLO LIKE ----------
    def _select_contact(self, contact):
        if not self._ensure_browser(): return False
        p = self.page

        if self._is_in_chat(contact):
            self.log(f"Contacto '{contact}' ya estaba abierto (composer/header OK).")
            return True

        try:
            sb = self._focus_global_search()
            if sb is None:
                if not self._open_new_chat(): return False
                sb = self._focus_global_search()
                if sb is None:
                    self.status("No se pudo acceder al cuadro de búsqueda.")
                    return False

            self._type_search_variants(contact)

            cand = self._collect_candidates()
            ranked = self._rank_candidates(contact, cand)

            if not ranked:
                # teclado: abrir primer resultado
                try:
                    p.keyboard.press("ArrowDown"); p.wait_for_timeout(100)
                    p.keyboard.press("Enter"); p.wait_for_timeout(350)
                except Exception: pass
            else:
                limit = min(4, len(ranked))
                for attempt in range(limit):
                    score, kind, nm, el, idx = ranked[attempt]
                    self.log(f"[LIKE pick] intento {attempt+1}/{limit}: '{nm}' (score={score:.2f}, idx={idx})")
                    try: el.scroll_into_view_if_needed(timeout=1500)
                    except Exception: pass
                    # clic en contenedor clickeable
                    try:
                        target = el
                        if kind in ("span",):
                            try: target = el.locator("xpath=ancestor::*[@data-testid='cell-frame-container' or @role='gridcell'][1]").first
                            except Exception: target = el
                        target.click(timeout=3000, force=True)
                    except Exception:
                        try: el.click(timeout=3000, force=True)
                        except Exception:
                            try:
                                p.keyboard.press("ArrowDown"); p.wait_for_timeout(100)
                                p.keyboard.press("Enter"); p.wait_for_timeout(350)
                            except Exception: pass

                    # IMPORTANT: blur del buscador para que ENTER no se vaya allí
                    try:
                        sbox = p.locator('[aria-label="Search input textbox"]').first
                        if sbox.is_visible(timeout=200):
                            p.evaluate("el=>el.blur()", sbox)
                    except Exception: pass

                    if self._wait_header(contact, timeout_ms=9000):
                        self._last_opened_chat_label = self._get_active_chat_from_composer()
                        self.log(f"Contacto seleccionado por LIKE: '{nm}' → activo='{self._last_opened_chat_label}'")
                        return True
                    else:
                        self.log(f"[LIKE pick] '{nm}' no abrió el chat correcto. Probamos siguiente.")

            # blur buscador y limpiar
            self._clear_global_search()

            if self._wait_header(contact, timeout_ms=9000):
                self._last_opened_chat_label = self._get_active_chat_from_composer()
                self.log(f"Contacto seleccionado (fallback teclado) → '{self._last_opened_chat_label}'")
                return True

            raise TimeoutError("No se obtuvo header del contacto tras seleccionar (LIKE).")

        except Exception as e:
            self.status(f"Error al seleccionar el contacto: {contact}")
            self.log(f"Error al seleccionar '{contact}': {e}")
            return False

    def _open_new_chat(self):
        if not self._ensure_browser(): return False
        p = self.page
        try:
            btn = p.get_by_role("button", name=re.compile(r"Nuevo chat|New chat|Nueva conversación", re.I)).first
            btn.click(timeout=6000, force=True)
            p.wait_for_timeout(350)
            return True
        except Exception: pass
        try:
            el = p.locator("button[data-testid='chat-list-new-chat'], span[data-icon='new-chat-outline']").first
            el.click(timeout=6000, force=True); p.wait_for_timeout(350); return True
        except Exception: pass
        try:
            p.keyboard.down("Control"); p.keyboard.press("KeyN"); p.keyboard.up("Control")
            p.wait_for_timeout(350); return True
        except Exception:
            return False

    def _ensure_chat_target(self, contact: str, attempts=3) -> bool:
        if not contact: return False
        for i in range(attempts):
            if self._is_in_chat(contact):
                return True
            self.log(f"[ensure_chat_target] actual='{self._get_active_chat_from_composer()}', objetivo='{contact}'. Reintentando ({i+1}/{attempts})...")
            if not self._select_contact(contact):
                time.sleep(0.2)
        return self._is_in_chat(contact)

    # ---------- COMPOSITOR EN FOOTER ----------
    def _get_composer_for_contact(self):
        p = self.page
        last_err = None
        for sel in (
            "footer div[aria-label^='Type to']",
            "footer div[aria-label^='Type a message to']",
            "footer div[aria-label^='Escribe a']",
        ):
            try:
                cont = p.locator(sel).last
                if cont.is_visible(timeout=900):
                    try:
                        par = cont.locator("p.selectable-text.copyable-text, p").last
                        if par.is_visible(timeout=300): return par, cont
                    except Exception: pass
                    return cont, cont
            except Exception as e:
                last_err = e
        for sel in (
            "footer [data-testid='conversation-compose-box-input'][contenteditable='true']",
            "footer div[contenteditable='true'][data-lexical-editor='true']",
            "footer div[role='textbox'][contenteditable='true'][aria-multiline='true']",
            "footer div[contenteditable='true'][data-tab]",
            "footer div[contenteditable='true']",
        ):
            try:
                cont = p.locator(sel).last
                if cont.is_visible(timeout=900):
                    try:
                        par = cont.locator("p.selectable-text.copyable-text, p").last
                        if par.is_visible(timeout=300): return par, cont
                    except Exception: pass
                    return cont, cont
            except Exception as e:
                last_err = e
        raise RuntimeError(f"No se encontró el compositor en footer. Detalle: {last_err}")

    def _prime_composer(self, node):
        p = self.page
        self._close_attach_menu()
        try: node.scroll_into_view_if_needed(timeout=2000)
        except Exception: pass

        try:
            p.locator("footer .selectable-text").last.click(force=True)
            p.wait_for_timeout(50)
        except Exception: pass

        try: p.evaluate("(el)=>el.focus()", node)
        except Exception: pass
        try:
            box = node.bounding_box()
            if box:
                cx = box["x"] + max(10, box["width"] * 0.50)
                cy = box["y"] + box["height"] * 0.50
                p.mouse.move(cx, cy); p.mouse.click(cx, cy); p.wait_for_timeout(60)
            else:
                node.click(force=True); p.wait_for_timeout(60)
        except Exception:
            try: node.click(force=True)
            except Exception: pass

        try:
            p.evaluate("""
                (el)=>{
                  try{
                    const target = el.closest('[contenteditable="true"]') || el;
                    target.focus();
                    const sel = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(target);
                    range.collapse(false);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    const ev = new InputEvent('input', {bubbles:true, cancelable:true, data:'', inputType:'insertText'});
                    target.dispatchEvent(ev);
                  }catch(e){}
                }
            """, node)
        except Exception: pass

        # Confirmar foco en contenteditable
        try:
            ok = p.evaluate("""
                ()=>{
                  const ae = document.activeElement;
                  return !!(ae && ae.isContentEditable);
                }
            """)
            if not ok:
                # intenta focus al contenedor contenteditable del footer
                try:
                    cont = p.locator("footer div[contenteditable='true']").last
                    p.evaluate("(el)=>el.focus()", cont)
                except Exception: pass
        except Exception: pass

        try:
            p.keyboard.press("Space"); p.keyboard.press("Backspace")
        except Exception: pass
        self._close_attach_menu()

    def _verify_message_sent(self, text, timeout_ms=9000):
        p = self.page
        end_time = time.time() + (timeout_ms / 1000.0)
        norm = lambda s: re.sub(r"\r\n|\r", "\n", s).strip()
        text = norm(text)
        while time.time() < end_time:
            try:
                for sel in ("div.message-out span.selectable-text",
                            "div.message-out [data-testid='msg-text'] span",
                            "div.message-out [data-lexical-text='true']"):
                    try: nodes = p.locator(sel).all()
                    except Exception: nodes = []
                    for c in nodes:
                        try:
                            if not c.is_visible(): continue
                            t = norm(c.inner_text())
                            if t == text: return True
                        except Exception: pass
            except Exception: pass
            p.wait_for_timeout(220)
        return False

    def _send_message(self, text):
        p = self.page
        current_target = globals().get("selected_contact","") or ""
        if not current_target or not self._ensure_chat_target(current_target, attempts=3):
            self.status(f"No se pudo asegurar el chat objetivo: {current_target}. Mensaje NO enviado.")
            self.log(f"ABORT: header='{self._get_active_chat_from_composer()}', objetivo='{current_target}'.")
            return False

        def _norm(s): return re.sub(r"\r\n|\r", "\n", s).strip()
        text = _norm(text)

        try:
            node, cont = self._get_composer_for_contact()

            # MUY IMPORTANTE: asegurar que el buscador no captura teclas
            self._clear_global_search()

            self._prime_composer(node)

            wrote = False
            try: p.keyboard.insert_text(text); wrote = True
            except Exception: pass
            if not wrote:
                try: node.fill(text); wrote = True
                except Exception: pass
            if not wrote:
                try: p.keyboard.type(text, delay=14); wrote = True
                except Exception: pass
            if not wrote:
                try:
                    p.evaluate("document.execCommand('insertText', false, arguments[0])", text)
                    wrote = True
                except Exception: pass

            if not wrote:
                raise RuntimeError("No se pudo escribir en el compositor.")

            sent = False
            try:
                send_btn = p.get_by_role("button", name=re.compile(r"Enviar|Send", re.I)).first
                if send_btn.is_visible(timeout=900):
                    send_btn.click(timeout=1500); sent = True
            except Exception: pass
            if not sent:
                try:
                    for sels in ("footer div[aria-label^='Type to']",
                                 "footer div[aria-label^='Type a message to']",
                                 "footer div[aria-label^='Escribe a']"):
                        try:
                            p.locator(sels).last.press("Enter"); sent=True; break
                        except Exception: continue
                except Exception: pass
            if not sent:
                try: node.press("Enter")
                except Exception:
                    try: cont.press("Enter")
                    except Exception: p.keyboard.press("Enter")
                self._close_attach_menu()

            if self._verify_message_sent(text, timeout_ms=9000):
                self.log(f"Mensaje enviado (a '{current_target}').")
                return True

            # Reintentos
            for i, d in enumerate((22, 18), start=1):
                if not self._ensure_chat_target(current_target, attempts=2):
                    self.status(f"No se pudo asegurar el chat objetivo en reintento {i}.")
                    return False
                node, cont = self._get_composer_for_contact()
                self._clear_global_search()
                self._prime_composer(node)
                try: p.keyboard.insert_text(text)
                except Exception:
                    try: node.fill(text)
                    except Exception:
                        try: p.keyboard.type(text, delay=d)
                        except Exception:
                            try: p.evaluate("document.execCommand('insertText', false, arguments[0])", text)
                            except Exception: pass
                try:
                    for sels in ("footer div[aria-label^='Type to']",
                                 "footer div[aria-label^='Type a message to']",
                                 "footer div[aria-label^='Escribe a']"):
                        try:
                            p.locator(sels).last.press("Enter"); break
                        except Exception: continue
                    else:
                        try: node.press("Enter")
                        except Exception:
                            try: cont.press("Enter")
                            except Exception: p.keyboard.press("Enter")
                except Exception:
                    try: node.press("Enter")
                    except Exception:
                        try: cont.press("Enter")
                        except Exception: p.keyboard.press("Enter")
                self._close_attach_menu()
                if self._verify_message_sent(text, timeout_ms=9000):
                    self.log(f"Mensaje enviado tras reintento ({i}/2) a '{current_target}'.")
                    return True

            self.status("Error al enviar mensaje")
            self.log("No se verificó el bubble tras intentos.")
            return False

        except Exception as e:
            self.status("Error al enviar mensaje")
            self.log(f"Error al enviar el mensaje: {e}")
            return False

    # ---------- CIERRE ----------
    def _close_our_pages(self):
        try:
            for p in list(self._opened_pages):
                try: p.close()
                except Exception: pass
            self._opened_pages.clear()
        except Exception: pass

    def _kill_process_tree(self):
        if not self._we_started or not self.browser_process:
            return
        try:
            pid = self.browser_process.pid
            if os.name == "nt":
                subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try: self.browser_process.terminate()
                except Exception: pass
        except Exception:
            pass

    def _shutdown(self):
        try: self._close_our_pages()
        except Exception: pass
        try:
            if self.context: self.context.close()
        except Exception: pass
        try:
            if self.browser: self.browser.close()
        except Exception: pass
        try:
            if self.playwright: self.playwright.stop()
        except Exception: pass
        try: self._kill_process_tree()
        except Exception: pass

# ================= Utilidades programación =================
def stop_repetition(group, index, cb):
    cb.set("Ninguno")
    for msg in scheduled_messages:
        if isinstance(msg, dict) and not msg.get("is_group"):
            if msg.get("group")==group and msg.get("index")==index:
                msg["repeat"]="Ninguno"
    update_status(f"Repetición detenida para Grupo {group}, Bloque {index+1}")

def add_months(sourcedate, months):
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, sourcedate.hour, sourcedate.minute, sourcedate.second)

def schedule_message(msg):
    target_dt = msg['datetime'] if isinstance(msg.get('datetime'), datetime) else datetime.now() + timedelta(seconds=2)
    delay_ms = max(1000, int((target_dt - datetime.now()).total_seconds()*1000))
    def _start():
        if not app_quitting:
            threading.Thread(target=process_scheduled_message, args=(msg,), daemon=True).start()
    try:
        after_id = root.after(delay_ms, _start)
        scheduled_after_ids.append(after_id)
    except tk.TclError:
        pass

def process_scheduled_message(msg):
    global selected_contact

    def _reprogram_repeat(m, now):
        if m.get("repeat")=="Cada minuto":
            m['datetime']=max(datetime.now()+timedelta(seconds=1), m['datetime']+timedelta(minutes=1)); schedule_message(m)
        elif m.get("repeat")=="Cada hora":
            m['datetime']=max(datetime.now()+timedelta(seconds=1), m['datetime']+timedelta(hours=1)); schedule_message(m)
        elif m.get("repeat")=="Diariamente":
            m['datetime']=max(datetime.now()+timedelta(seconds=1), m['datetime']+timedelta(days=1)); schedule_message(m)
        elif m.get("repeat")=="Semanalmente":
            m['datetime']=max(datetime.now()+timedelta(seconds=1), m['datetime']+timedelta(weeks=1)); schedule_message(m)
        elif m.get("repeat")=="Mensualmente":
            m['datetime']=max(datetime.now()+timedelta(seconds=1), add_months(m['datetime'],1)); schedule_message(m)

    if not ensure_browser():
        update_status("Error: WhatsApp no está disponible"); return

    now = datetime.now()

    if msg.get("is_group"):
        contact = msg["contact"]
        items = list(msg.get("items") or [])
        if not items: return

        runnable = []
        for m in items:
            days = m.get("days") or []
            if days and datetime.now().weekday() not in days:
                delta=1
                while (datetime.now()+timedelta(days=delta)).weekday() not in days:
                    delta+=1
                new_time = datetime.now()+timedelta(days=delta)
                m["datetime"]=new_time
                update_status(f"Hoy no es un día permitido. Reprogramando para: {new_time}")
                schedule_message(m)
            else:
                runnable.append(m)

        if not runnable: return

        selected_contact = contact
        if not select_contact(contact):
            update_status(f"Error: No se pudo iniciar chat con {contact}")
            return

        for m in runnable:
            ok = send_message_playwright(m['message'])
            if ok:
                update_status(f"Mensaje enviado a {contact}")
                m['last_sent'] = now
                log_message_sent(contact, m['message'])
            else:
                update_status(f"Error al enviar mensaje a {contact}")
            _reprogram_repeat(m, now)
        return

    last = msg.get("last_sent")
    if msg.get("repeat")=="Cada minuto" and last and (last.year,last.month,last.day,last.hour,last.minute)==(now.year,now.month,now.day,now.hour,now.minute):
        update_status(f"Mensaje {msg['index']+1} ya fue enviado este minuto. Reprogramando.")
        msg['datetime'] = now.replace(second=0, microsecond=0)+timedelta(minutes=1); schedule_message(msg); return
    if msg.get("repeat")=="Cada hora" and last and (last.year,last.month,last.day,last.hour)==(now.year,now.month,now.day,now.hour):
        update_status(f"Mensaje {msg['index']+1} ya fue enviado esta hora. Reprogramando.")
        msg['datetime'] = now.replace(minute=0, second=0, microsecond=0)+timedelta(hours=1); schedule_message(msg); return
    if msg.get("repeat")=="Diariamente" and last and last.date()==now.date():
        update_status(f"Mensaje {msg['index']+1} ya fue enviado hoy. Reprogramando.")
        msg['datetime'] = now.replace(hour=0, minute=0, second=0, microsecond=0)+timedelta(days=1); schedule_message(msg); return
    if msg.get("repeat")=="Semanalmente" and last and last.isocalendar()[1]==now.isocalendar()[1] and last.year==now.year:
        update_status(f"Mensaje {msg['index']+1} ya fue enviado esta semana. Reprogramando.")
        msg['datetime'] = msg['datetime'] + timedelta(weeks=1); schedule_message(msg); return
    if msg.get("repeat")=="Mensualmente" and last and (last.year,last.month)==(now.year,now.month):
        update_status(f"Mensaje {msg['index']+1} ya fue enviado este mes. Reprogramando.")
        msg['datetime'] = add_months(now.replace(second=0, microsecond=0),1); schedule_message(msg); return

    if msg.get("days"):
        if datetime.now().weekday() not in msg["days"]:
            delta=1
            while (datetime.now()+timedelta(days=delta)).weekday() not in msg["days"]: delta+=1
            new_time = datetime.now()+timedelta(days=delta)
            msg["datetime"]=new_time; update_status(f"Hoy no es un día permitido. Reprogramando para: {new_time}")
            schedule_message(msg); return

    selected_contact = msg['contact']
    if select_contact(msg['contact']):
        if send_message_playwright(msg['message']):
            update_status(f"Mensaje enviado a {msg['contact']}"); msg['last_sent']=now
            log_message_sent(msg['contact'], msg['message'])
            if msg.get("repeat")=="Cada minuto":
                msg['datetime']=max(datetime.now()+timedelta(seconds=1), msg['datetime']+timedelta(minutes=1)); schedule_message(msg)
            elif msg.get("repeat")=="Cada hora":
                msg['datetime']=max(datetime.now()+timedelta(seconds=1), msg['datetime']+timedelta(hours=1)); schedule_message(msg)
            elif msg.get("repeat")=="Diariamente":
                msg['datetime']=max(datetime.now()+timedelta(seconds=1), msg['datetime']+timedelta(days=1)); schedule_message(msg)
            elif msg.get("repeat")=="Semanalmente":
                msg['datetime']=max(datetime.now()+timedelta(seconds=1), msg['datetime']+timedelta(weeks=1)); schedule_message(msg)
            elif msg.get("repeat")=="Mensualmente":
                msg['datetime']=max(datetime.now()+timedelta(seconds=1), add_months(msg['datetime'],1)); schedule_message(msg)
    else:
        update_status(f"Error: No se pudo iniciar chat con {msg['contact']}")

# ================= GUI =================
def _bind_listbox_keyboard(lb: tk.Listbox):
    def on_key(e):
        key = e.keysym
        if key in ("Up","Down","Prior","Next","Home","End"):
            try:
                cur = lb.curselection()
                if not cur:
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(0); lb.see(0)
                    return "break"
                i = cur[0]
                if key=="Up" and i>0: i-=1
                elif key=="Down" and i<lb.size()-1: i+=1
                elif key=="Prior": i=max(0, i-5)
                elif key=="Next":  i=min(lb.size()-1, i+5)
                elif key=="Home":  i=0
                elif key=="End":   i=lb.size()-1
                lb.selection_clear(0, tk.END)
                lb.selection_set(i); lb.see(i)
                return "break"
            except Exception:
                return "break"
        ch = e.char
        if ch:
            txt = ch.strip()
            if not txt:
                return
            buf = getattr(lb, "_typebuf", "")
            last_ts = getattr(lb, "_typebuf_time", 0)
            now = time.time()
            if now - last_ts > 0.9:
                buf = ""
            buf += txt
            lb._typebuf = buf
            lb._typebuf_time = now

            pattern = re.compile(rf"^{re.escape(buf)}$", re.I)
            for i in range(lb.size()):
                val = lb.get(i)
                if pattern.match(str(val)):
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(i); lb.see(i)
                    return "break"
            pattern2 = re.compile(rf"^{re.escape(buf)}", re.I)
            for i in range(lb.size()):
                val = lb.get(i)
                if pattern2.match(str(val)):
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(i); lb.see(i)
                    return "break"
        return
    lb.bind("<Key>", on_key)

def create_message_blocks(frame, num_msgs, group_id, pre_config=None):
    entries_contact, entries_message, entries_date = [], [], []
    listbox_hour, listbox_minute, listbox_ampm = [], [], []
    send_vars, repeat_vars, days_vars_all = [], [], []

    hours = [str(i) for i in range(1,13)]
    minutes = [f"{i:02d}" for i in range(60)]
    ampm_options = ["AM","PM"]

    for i in range(num_msgs):
        pre = pre_config[i] if pre_config and i<len(pre_config) else {}
        sub = tk.Frame(frame, relief=tk.GROOVE, borderwidth=2, takefocus=True)
        sub.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
        hdr = tk.Frame(sub, takefocus=True); hdr.pack(fill="x", padx=5, pady=2)
        tk.Label(hdr, text=f"Mensaje {i+1}", font=("Helvetica",14), takefocus=True).pack(side="left")
        var_send = tk.BooleanVar(value=bool(pre.get("send",False))); send_vars.append(var_send)
        tk.Checkbutton(hdr, text="Enviar", variable=var_send, takefocus=True, underline=0).pack(side="right")

        tk.Label(sub, text="Contacto:", takefocus=True).pack(anchor="w", padx=5)
        ent_c = tk.Entry(sub, width=40, takefocus=True); ent_c.insert(0, pre.get("contact","")); ent_c.pack(padx=5,pady=2)
        entries_contact.append(ent_c)

        tk.Label(sub, text="Mensaje:", takefocus=True).pack(anchor="w", padx=5)
        txt = tk.Text(sub, height=3, width=50, takefocus=True); txt.insert(tk.END, pre.get("message","")); txt.pack(padx=5,pady=2)
        entries_message.append(txt)

        tk.Label(sub, text="Fecha de envío:", takefocus=True).pack(anchor="w", padx=5)
        df = tk.Frame(sub); df.pack(padx=5,pady=2, fill=tk.X)
        de = DateEntry(df, date_pattern="yyyy-mm-dd", takefocus=True); de.set_date(pre.get("date", datetime.now().strftime("%Y-%m-%d"))); de.pack(side=tk.LEFT)
        tk.Button(df, text="Set Actual Date", command=lambda de=de: de.set_date(datetime.now()), underline=0).pack(side=tk.LEFT, padx=5)
        entries_date.append(de)

        ft = tk.Frame(sub, takefocus=True); ft.pack(padx=5,pady=2, fill=tk.X)
        tk.Label(ft, text="Hora:", takefocus=True).grid(row=0,column=0,padx=5)
        fh = tk.Frame(ft); fh.grid(row=1,column=0,padx=5)
        lb_h = tk.Listbox(fh, height=4, exportselection=False, selectbackground="blue", takefocus=True)
        for h in hours: lb_h.insert(tk.END, h); lb_h.pack(side="left", fill="y")
        sb_h = tk.Scrollbar(fh, orient="vertical", command=lb_h.yview); lb_h.configure(yscrollcommand=sb_h.set); sb_h.pack(side="right", fill="y")
        listbox_hour.append(lb_h)
        _bind_listbox_keyboard(lb_h)

        tk.Label(ft, text="Minutos:", takefocus=True).grid(row=0,column=1,padx=5)
        fm = tk.Frame(ft); fm.grid(row=1,column=1,padx=5)
        lb_m = tk.Listbox(fm, height=4, exportselection=False, selectbackground="blue", takefocus=True)
        for m in minutes: lb_m.insert(tk.END, m); lb_m.pack(side="left", fill="y")
        sb_m = tk.Scrollbar(fm, orient="vertical", command=lb_m.yview); lb_m.configure(yscrollcommand=sb_m.set); sb_m.pack(side="right", fill="y")
        listbox_minute.append(lb_m)
        _bind_listbox_keyboard(lb_m)

        tk.Label(ft, text="AM/PM:", takefocus=True).grid(row=0,column=2,padx=5)
        lb_ap = tk.Listbox(ft, height=2, exportselection=False, selectbackground="blue", takefocus=True)
        for ap in ampm_options: lb_ap.insert(tk.END, ap)
        lb_ap.grid(row=1,column=2,padx=5)
        listbox_ampm.append(lb_ap)
        _bind_listbox_keyboard(lb_ap)

        if pre.get("hour",""):
            try: idx = [str(h) for h in range(1,13)].index(str(pre["hour"])); lb_h.selection_set(idx); lb_h.see(idx)
            except Exception: pass
        if pre.get("minute","")!="":
            try: idx = [f"{m:02d}" for m in range(60)].index(str(pre["minute"]).zfill(2)); lb_m.selection_set(idx); lb_m.see(idx)
            except Exception: pass
        if pre.get("ampm",""):
            try: idx=["AM","PM"].index(pre["ampm"].upper()); lb_ap.selection_set(idx); lb_ap.see(idx)
            except Exception: pass

        tk.Label(sub, text="Repetir:", takefocus=True).pack(anchor="w", padx=5)
        cb_rep = ttk.Combobox(sub, values=["Ninguno","Cada minuto","Cada hora","Diariamente","Semanalmente","Mensualmente"], state="readonly", width=15)
        cb_rep.set(pre.get("repeat","Ninguno")); cb_rep.pack(side=tk.LEFT, padx=5, pady=2)
        repeat_vars.append(cb_rep)

        tk.Button(sub, text="Detener repetición", command=lambda grp=group_id, idx=i, cb=cb_rep: stop_repetition(grp, idx, cb), takefocus=True, underline=0).pack(side=tk.LEFT, padx=5, pady=2)

        tk.Label(sub, text="Días:", takefocus=True).pack(anchor="w", padx=5)
        df2 = tk.Frame(sub); df2.pack(padx=5,pady=2, fill=tk.X)
        current_days_vars=[]; pre_days=pre.get("days",[])
        for j, d in enumerate(day_names):
            var=tk.BooleanVar(value=(j in pre_days)); tk.Checkbutton(df2, text=d, variable=var).pack(side=tk.LEFT); current_days_vars.append(var)
        days_vars_all.append(current_days_vars)

    return (entries_contact, entries_message, entries_date, listbox_hour, listbox_minute, listbox_ampm,
            send_vars, repeat_vars, days_vars_all)

# ================= Programación / Guardado =================
def schedule_messages_group(group_name, entries_contact, entries_message, entries_date,
                            listbox_hour, listbox_minute, listbox_ampm, send_vars, repeat_vars, group_id, days_vars):
    msgs=[]; now=datetime.now(); now_min=now.replace(second=0,microsecond=0)
    for i in range(len(entries_contact)):
        if not send_vars[i].get(): continue
        contact=entries_contact[i].get().strip()
        message_text=entries_message[i].get("1.0", tk.END).strip()
        if not contact or not message_text: continue
        date_str=entries_date[i].get()
        hsel=listbox_hour[i].curselection(); msel=listbox_minute[i].curselection(); asel=listbox_ampm[i].curselection()
        if not hsel or not msel or not asel:
            update_status(f"Error: Seleccione hora, minuto y AM/PM para mensaje {i+1} del {group_name}")
            return []
        hour_val=int(listbox_hour[i].get(hsel[0])); minute_val=int(listbox_minute[i].get(msel[0])); ampm_val=listbox_ampm[i].get(asel[0])
        if ampm_val.upper()=="PM" and hour_val!=12: hour_val+=12
        elif ampm_val.upper()=="AM" and hour_val==12: hour_val=0
        try:
            scheduled_date=datetime.strptime(date_str,"%Y-%m-%d")
            scheduled_datetime=scheduled_date.replace(hour=hour_val, minute=minute_val)
        except ValueError:
            update_status(f"Error: Fecha/hora incorrecta en mensaje {i+1} del {group_name}"); return []
        update_status(f"Programando mensaje {i+1} del {group_name} para: {scheduled_datetime} (Ahora: {now_min})")
        if scheduled_datetime<now_min:
            update_status(f"Mensaje {i+1} del {group_name} está en el pasado y no se programará."); continue
        repeat_value=repeat_vars[i].get()
        repeat={"Cada minuto":"Cada minuto","Cada hora":"Cada hora","Diariamente":"Diariamente","Semanalmente":"Semanalmente","Mensualmente":"Mensualmente"}.get(repeat_value,"Ninguno")
        allowed_days=[j for j,var in enumerate(days_vars[i]) if var.get()]
        msgs.append({"group":group_id,"index":i,"contact":contact,"message":message_text,"datetime":scheduled_datetime,"sent":False,"repeat":repeat,"days":allowed_days,"last_sent":None})
    return msgs

def cancel_all_scheduled_messages():
    global scheduled_after_ids
    for aid in scheduled_after_ids:
        try: root.after_cancel(aid)
        except Exception: pass
    scheduled_after_ids.clear()

def schedule_all_messages():
    global scheduled_messages
    cancel_all_scheduled_messages()
    scheduled_messages=[]

    g1=schedule_messages_group("Grupo 1", entries_contact1, entries_message1, entries_date1, listbox_hour1, listbox_minute1, listbox_ampm1, send_vars1, repeat_vars1, 1, days_vars1)
    g2=schedule_messages_group("Grupo 2", entries_contact2, entries_message2, entries_date2, listbox_hour2, listbox_minute2, listbox_ampm2, send_vars2, repeat_vars2, 2, days_vars2)
    g3=schedule_messages_group("Grupo 3", entries_contact3, entries_message3, entries_date3, listbox_hour3, listbox_minute3, listbox_ampm3, send_vars3, repeat_vars3, 3, days_vars3)
    g4=schedule_messages_group("Grupo 4", entries_contact4, entries_message4, entries_date4, listbox_hour4, listbox_minute4, listbox_ampm4, send_vars4, repeat_vars4, 4, days_vars4)

    all_msgs = g1+g2+g3+g4
    grouped = {}
    for m in all_msgs:
        key = (m["datetime"], m["contact"])
        grouped.setdefault(key, []).append(m)

    scheduled_messages = []
    for (dt, contact), items in grouped.items():
        scheduled_messages.append({
            "is_group": True,
            "datetime": dt,
            "contact": contact,
            "items": items,
        })

    for sm in scheduled_messages:
        schedule_message(sm)

    update_status("Mensajes programados para los 4 grupos.")

def save_messages_config():
    def collect(e_c,e_m,e_d,lb_h,lb_m,lb_a,rep,days,send):
        out=[]
        for i in range(len(e_c)):
            days_sel=[j for j,v in enumerate(days[i]) if v.get()]
            out.append({
                "contact": e_c[i].get().strip(),
                "message": e_m[i].get("1.0", tk.END).strip(),
                "date": e_d[i].get(),
                "hour": lb_h[i].get(lb_h[i].curselection()[0]) if lb_h[i].curselection() else "",
                "minute": lb_m[i].get(lb_m[i].curselection()[0]) if lb_m[i].curselection() else "",
                "ampm": lb_a[i].get(lb_a[i].curselection()[0]) if lb_a[i].curselection() else "",
                "repeat": rep[i].get(),
                "send": bool(send[i].get()),
                "days": days_sel
            })
        return out
    config["messages_group1"] = collect(entries_contact1, entries_message1, entries_date1, listbox_hour1, listbox_minute1, listbox_ampm1, repeat_vars1, days_vars1, send_vars1)
    config["messages_group2"] = collect(entries_contact2, entries_message2, entries_date2, listbox_hour2, listbox_minute2, listbox_ampm2, repeat_vars2, days_vars2, send_vars2)
    config["messages_group3"] = collect(entries_contact3, entries_message3, entries_date3, listbox_hour3, listbox_minute3, listbox_ampm3, repeat_vars3, days_vars3, send_vars3)
    config["messages_group4"] = collect(entries_contact4, entries_message4, entries_date4, listbox_hour4, listbox_minute4, listbox_ampm4, repeat_vars4, days_vars4, send_vars4)
    with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)
    update_status("Configuración de mensajes guardada.")

# ================= GUI =================
root = tk.Tk()
root.title("Programador de Mensajes WhatsApp (Brave / Opera con Playwright)")
root.report_callback_exception = _swallow_tk_errors_during_shutdown

_splash = show_splash()

if window_x is not None and window_y is not None:
    try:
        root.geometry(f"{window_geometry}+{int(window_x)}+{int(window_y)}")
    except Exception:
        root.geometry(window_geometry)
else:
    root.geometry(window_geometry)

if window_state == "zoomed":
    try: root.state("zoomed")
    except Exception: pass

root.minsize(1000,800)

version_label = tk.Label(root, text=f"Versión: {__version__}", font=("Helvetica",10)); version_label.pack(side=tk.BOTTOM, pady=2)

top = tk.Frame(root); top.pack(side=tk.TOP, fill=tk.X, pady=5)
tk.Label(top, text="Navegador:").grid(row=0,column=0,padx=5)
browser_combo = ttk.Combobox(top, values=["Brave","Opera"], state="readonly", width=10); browser_combo.set(browser_choice); browser_combo.grid(row=0,column=1,padx=5)
def on_browser_select(e=None):
    global browser_choice
    sel = browser_combo.get()
    if sel!=browser_choice:
        browser_choice=sel; config["global"]["browser"]=sel
        with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)
        update_status(f"Navegador seleccionado: {sel}")
browser_combo.bind("<<ComboboxSelected>>", on_browser_select)

def select_brave_path():
    global brave_path
    sel = filedialog.askopenfilename(title="Seleccionar la ruta de Brave", filetypes=[("Executable","*.exe")])
    if sel:
        brave_path=sel; config["global"]["brave_path"]=sel
        with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)
        update_status(f"Ruta de Brave actualizada a: {sel}")

def select_opera_path():
    global opera_path
    sel = filedialog.askopenfilename(title="Seleccionar la ruta de Opera", filetypes=[("Executable","*.exe")])
    if sel:
        opera_path=sel; config["global"]["opera_path"]=sel
        with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)
        update_status(f"Ruta de Opera actualizada a: {sel}")

def reset_default_paths():
    global brave_path, opera_path
    brave_path=default_config["global"]["brave_path"]; opera_path=default_config["global"]["opera_path"]
    config["global"]["brave_path"]=brave_path; config["global"]["opera_path"]=opera_path
    with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)
    update_status("Rutas por defecto restauradas para Brave y Opera.")

btn_brave = tk.Button(top, text="Ruta Brave", command=select_brave_path, underline=5); btn_brave.grid(row=0,column=2,padx=5)
btn_opera = tk.Button(top, text="Ruta Opera", command=select_opera_path, underline=5); btn_opera.grid(row=0,column=3,padx=5)
btn_reset = tk.Button(top, text="Usar Ruta por defecto", command=reset_default_paths, underline=14); btn_reset.grid(row=0,column=4,padx=5)
btn_save = tk.Button(top, text="Guardar Configuración", command=save_messages_config, underline=8); btn_save.grid(row=0,column=5,padx=5)

clock_label = tk.Label(root, font=("Helvetica",12)); clock_label.pack(side=tk.BOTTOM, pady=5)
def update_clock():
    global clock_after_id
    if app_quitting: return
    try:
        if not (root and root.winfo_exists()): return
        if clock_label and clock_label.winfo_exists():
            clock_label.config(text="Hora actual: "+datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except tk.TclError:
        return
    if not app_quitting:
        try: clock_after_id = root.after(1000, update_clock)
        except tk.TclError: pass
update_clock()

status_label = tk.Label(root, text="Estado: listo", anchor="w"); status_label.pack(fill="x")

mid = tk.Frame(root); mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
canvas = tk.Canvas(mid); canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
vscroll = tk.Scrollbar(mid, orient=tk.VERTICAL, command=canvas.yview); vscroll.pack(side=tk.RIGHT, fill=tk.Y)
canvas.configure(yscrollcommand=vscroll.set)
main_frame = tk.Frame(canvas); canvas.create_window((0,0), window=main_frame, anchor="nw")
def on_cfg(event): canvas.configure(scrollregion=canvas.bbox("all"))
main_frame.bind("<Configure>", on_cfg)

log_frame = tk.Frame(root); log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False)
log_text = tk.Text(log_frame, height=10); log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
log_scroll = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview); log_text.configure(yscrollcommand=log_scroll.set); log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

notebook = ttk.Notebook(main_frame); notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
frame_group1 = tk.Frame(notebook); notebook.add(frame_group1, text="Grupo 1")
frame_group2 = tk.Frame(notebook); notebook.add(frame_group2, text="Grupo 2")
frame_group3 = tk.Frame(notebook); notebook.add(frame_group3, text="Grupo 3")
frame_group4 = tk.Frame(notebook); notebook.add(frame_group4, text="Grupo 4")

(entries_contact1, entries_message1, entries_date1, listbox_hour1, listbox_minute1, listbox_ampm1, send_vars1, repeat_vars1, days_vars1) = create_message_blocks(frame_group1, num_messages_group1, 1, messages_config_group1)
(entries_contact2, entries_message2, entries_date2, listbox_hour2, listbox_minute2, listbox_ampm2, send_vars2, repeat_vars2, days_vars2) = create_message_blocks(frame_group2, num_messages_group2, 2, messages_config_group2)
(entries_contact3, entries_message3, entries_date3, listbox_hour3, listbox_minute3, listbox_ampm3, send_vars3, repeat_vars3, days_vars3) = create_message_blocks(frame_group3, num_messages_group3, 3, messages_config_group3)
(entries_contact4, entries_message4, entries_date4, listbox_hour4, listbox_minute4, listbox_ampm4, send_vars4, repeat_vars4, days_vars4) = create_message_blocks(frame_group4, num_messages_group4, 4, messages_config_group4)

# ================= Worker wrappers =================
def _browser_choice_getter():
    try: return browser_combo.get()
    except Exception: return browser_choice

worker = BrowserWorker(
    remote_port=remote_port,
    debug_port_timeout=debug_port_timeout,
    cdp_timeout=cdp_timeout,
    cdp_retries=cdp_retries,
    extra_wait=extra_wait,
    brave_path=brave_path,
    opera_path=opera_path,
    browser_choice_getter=_browser_choice_getter,
    log_fn=log_message,
    status_fn=update_status
)
worker.start()

def ensure_browser():
    try: return worker.call("ensure")
    except Exception as e: update_status(f"Error ensure_browser: {e}"); return False

def open_new_chat():
    try: return worker.call("open_new_chat")
    except Exception as e: log_message(f"Error open_new_chat: {e}"); return False

def select_contact(contact):
    try: return worker.call("select_contact", contact=contact)
    except Exception as e:
        update_status(f"Error al seleccionar el contacto: {contact}")
        log_message(f"Error select_contact '{contact}': {e}")
        return False

def send_message_playwright(message_text):
    global selected_contact
    try:
        ok = worker.call("send_message", text=message_text)
        if ok: log_message_sent(selected_contact, message_text)
        return ok
    except Exception as e:
        update_status("Error al enviar mensaje"); log_message(f"Error send_message: {e}")
        return False

# ================= Botones / Atajos =================
btn_schedule = tk.Button(root, text="Programar mensajes", command=schedule_all_messages, underline=10); btn_schedule.pack(side=tk.TOP, pady=5)
btn_exit = tk.Button(root, text="Salir", command=lambda: root.event_generate("<<ExitRequested>>"), underline=0); btn_exit.pack(side=tk.TOP, pady=5)

root.bind_all("<Alt-b>", lambda e: select_brave_path())
root.bind_all("<Alt-o>", lambda e: select_opera_path())
root.bind_all("<Alt-r>", lambda e: reset_default_paths())
root.bind_all("<Alt-g>", lambda e: save_messages_config())
root.bind_all("<Alt-p>", lambda e: schedule_all_messages())
root.bind_all("<Alt-s>", lambda e: root.event_generate("<<ExitRequested>>"))

if _splash is not None and _splash.winfo_exists():
    _splash.destroy()

threading.Thread(target=ensure_browser, daemon=True).start()

# ================= Persistencia / cierre =================
def _save_window_placement():
    try:
        st = root.state()
        config["global"]["window_state"] = "zoomed" if st == "zoomed" else "normal"
        if st == "normal":
            root.update_idletasks()
            x = root.winfo_x()
            y = root.winfo_y()
            config["global"]["window_x"] = x
            config["global"]["window_y"] = y
        with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(config,f,indent=4,ensure_ascii=False)
    except Exception:
        pass

def _on_exit_requested(event=None):
    global app_quitting, clock_after_id
    app_quitting = True
    try:
        if clock_after_id is not None:
            root.after_cancel(clock_after_id)
            clock_after_id = None
    except Exception:
        pass
    cancel_all_scheduled_messages()
    _save_window_placement()

    def shutdown_and_quit():
        try:
            worker.call("shutdown")
        except Exception:
            pass
        try:
            app_log_file.close(); msg_log_file.close()
        except Exception:
            pass
        try:
            root.after(0, lambda: (root.quit(), root.destroy()))
        except Exception:
            pass

    threading.Thread(target=shutdown_and_quit, daemon=True).start()

root.bind("<<ExitRequested>>", _on_exit_requested)

# ================= Mainloop =================
try:
    root.mainloop()
finally:
    try: app_log_file.close(); msg_log_file.close()
    except Exception: pass
