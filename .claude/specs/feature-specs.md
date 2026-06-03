# Especificacion de Diseno de Software (SDD)
# WhatsApp Message Scheduler — v8.5.0

**Proyecto:** Programador de Mensajes WhatsApp  
**Autor:** Equipo de desarrollo  
**Fecha:** 2026-06-03  
**Version del documento:** 1.2  
**Version de la aplicacion:** 8.5.0

---

## Indice

1. [Programacion de mensajes (4 grupos x 4 mensajes)](#1-programacion-de-mensajes)
2. [Automatizacion de navegador (Playwright + CDP)](#2-automatizacion-de-navegador)
3. [Recuperacion post-hibernacion](#3-recuperacion-post-hibernacion)
4. [Soporte multi-idiomas (ES/EN/PT)](#4-soporte-multi-idiomas)
5. [Sistema de logging](#5-sistema-de-logging)
6. [Persistencia de configuracion](#6-persistencia-de-configuracion)
7. [Boton Comprame una cerveza (PayPal)](#7-boton-comprame-una-cerveza)
8. [[PENDIENTE] Multi-idioma extendido](#8-pendiente-multi-idioma-extendido)
9. [GUI moderna con CustomTkinter (V8.4.0)](#9-gui-moderna-con-customtkinter)
10. [Confiabilidad de largo plazo (V8.5.0)](#10-confiabilidad-de-largo-plazo)

---

## 1. Programacion de Mensajes

**Estado:** Activo

### Descripcion

La aplicacion permite al usuario definir hasta 16 mensajes programados organizados en 4 grupos independientes, cada uno con hasta 4 mensajes. Cada mensaje tiene su propio contacto destino, texto, fecha, hora y configuracion de repeticion. Al presionar "Programar mensajes", todos los mensajes con el checkbox "Enviar" activo se registran en el scheduler de Tkinter (`root.after`) y se envian automaticamente cuando llega su turno.

### Criterios de Aceptacion

- La UI presenta 4 pestanas (tabs), una por grupo, etiquetadas "Grupo 1" a "Grupo 4".
- Cada tab contiene 4 bloques de mensaje con los campos: Contacto, Mensaje (texto multilínea), Fecha de envio (DateEntry), Hora, Minuto, AM/PM, Repetir (combobox), Dias de la semana (checkboxes Lun-Dom) y checkbox "Enviar".
- El campo Fecha acepta seleccion visual mediante calendario (tkcalendar.DateEntry).
- El combobox "Repetir" ofrece las opciones: Ninguno, Cada minuto, Cada hora, Diariamente, Semanalmente, Mensualmente.
- Los checkboxes de dias solo son relevantes para repeticion semanal.
- Al programar, si la fecha/hora ya paso y no hay repeticion configurada, el mensaje se omite con aviso en el log.
- Si la fecha ya paso pero hay repeticion activa, se calcula automaticamente la proxima ocurrencia valida y se reprograma.
- El boton "Detener repeticion" en cada bloque cancela la repeticion de ese mensaje especifico.
- El boton "Set hoy" rellena la fecha del bloque con la fecha actual.
- Un contador de generacion (`_schedule_generation`) invalida callbacks pendientes de ciclos anteriores, previniendo dobles envios tras re-programacion.
- Los mensajes enviados satisfactoriamente muestran confirmacion en el log de la UI y en el archivo de log de mensajes.

### Notas de Implementacion

- Modulo principal: `frontend/gui.py`, clase `WhatsAppSchedulerApp`.
- Estructura de datos por grupo: dataclass `MessageGroupWidgets` con listas de widgets indexadas por posicion.
- Los grupos y sus mensajes se almacenan en `config.json` bajo las claves `messages_group1` a `messages_group4`.
- La logica de calculo de proxima ocurrencia maneja los casos: mensual (usando `calendar.monthrange` para validar el ultimo dia del mes), semanal (iteracion sobre dias habilitados), diaria/horaria/por minuto (offset fijo).
- Los `after` IDs se acumulan en `self.scheduled_after_ids` para poder cancelarlos masivamente con `_cancel_all_scheduled_messages()`.
- El metodo `_process_scheduled_message` recibe el contacto y el mensaje como parametros propios (no como estado compartido) para evitar race conditions cuando multiples mensajes se envian en simultaneo post-hibernacion.

---

## 2. Automatizacion de Navegador (Playwright + CDP)

**Estado:** Activo

### Descripcion

La automatizacion del navegador se realiza mediante Playwright conectado via Chrome DevTools Protocol (CDP) a una instancia de navegador previamente abierta (o lanzada por la propia aplicacion). Esto permite controlar WhatsApp Web sin depender de APIs externas ni de sesiones de Selenium. El `BrowserWorker` es un hilo daemon que recibe comandos mediante una cola thread-safe y ejecuta las operaciones sobre el navegador de forma serializada.

### Criterios de Aceptacion

- Los navegadores soportados son: Opera, Brave, Chrome, Microsoft Edge.
- La aplicacion puede conectarse a un navegador ya abierto en el puerto CDP configurado (por defecto 9222) o lanzar uno nuevo con el perfil `whats_profile`.
- La conexion CDP se reintenta hasta `cdp_retries` veces (por defecto 3) con timeout de `cdp_timeout` ms (por defecto 90000 ms) por intento.
- El worker detecta y enlaza automaticamente la pestana que contiene WhatsApp Web (`web.whatsapp.com`).
- La seleccion de contacto realiza busqueda por texto en WhatsApp Web usando algoritmo de tokenizacion y cobertura de terminos para tolerar coincidencias parciales y caracteres especiales.
- El envio de mensaje escribe el texto en el campo de entrada y simula el envio (Enter), con verificacion posterior.
- El worker mantiene la conexion activa mediante keepalives periodicos cada `keepalive_interval_sec` segundos (por defecto 60 s).
- Si el navegador se desconecta y `relaunch_on_disconnect` esta habilitado, el worker relanza el browser automaticamente.
- Los argumentos extra de lanzamiento del navegador son configurables via `browser_extra_args` en `config.json`.
- La ruta del ejecutable de cada navegador es configurable desde la UI y persiste en `config.json`.

### Notas de Implementacion

- Modulo: `backend/browser_worker.py`, clase `BrowserWorker(threading.Thread)`.
- Fachada publica: `backend/whatsapp_backend.py`, clase `WhatsAppBackend`.
- Configuracion en tiempo de ejecucion: dataclass `BrowserRuntimeSettings` (campos: `browser`, `browser_paths`, `remote_port`, `debug_port_timeout`, `cdp_timeout`, `cdp_retries`, `extra_wait`, `keepalive_interval_sec`, `relaunch_on_disconnect`, `user_data_dir`, `browser_extra_args`).
- Comunicacion GUI-worker: metodo `worker.call(command, timeout, **kwargs)` con cola de respuesta por llamada (pattern request/reply sobre `queue.Queue`).
- Normalizacion de nombres de contacto: funcion `_normalize_like` aplica NFKD, elimina diacriticos, minuscula, elimina caracteres especiales; `_coverage_score` calcula proporcion de tokens del needle presentes en el candidato.
- Deteccion de procesos zombie (Windows): funcion `_pids_by_name_win` via PowerShell `Get-Process`; `_existing_pids` mapea el ejecutable del browser al nombre de proceso correspondiente.
- Creacion de subprocesos sin ventana en Windows: flags `CREATE_NO_WINDOW` + `STARTF_USESHOWWINDOW` en `_subprocess_no_window_kwargs`.
- Los timeouts por operacion definidos en `WhatsAppBackend`: bind=120 s, select=60 s, send=120 s, post_sleep=600 s.
- Un `_delivery_lock` en `WhatsAppBackend` serializa los pares `select_contact + send_message` para evitar race conditions entre hilos de mensajeria concurrentes.

---

## 3. Recuperacion Post-Hibernacion

**Estado:** Activo

### Descripcion

Cuando el sistema operativo entra en suspension o hibernacion, la conexion CDP con el navegador se interrumpe y los timers de Tkinter (`after`) quedan congelados. Al despertar, los timers vencidos se disparan en rafaga. La funcionalidad de recuperacion post-hibernacion detecta este escenario, fuerza la reconexion del navegador (matando instancias zombie si es necesario) y reprograma los mensajes con repeticion para envio inmediato, evitando tanto el envio duplicado como la perdida de mensajes.

### Criterios de Aceptacion

- La aplicacion detecta que el sistema estuvo suspendido comparando el tiempo real transcurrido con el tiempo de CPU esperado (watchdog que corre cada 30 s; si el gap supera 60 s, se considera wake-from-sleep).
- Al detectar wake-from-sleep, se muestra el mensaje "Sistema desperto de hibernacion. Reconectando WhatsApp..." en el log y en la barra de estado.
- La reconexion post-sleep corre en un hilo separado para no bloquear la GUI, usando `trigger_post_sleep_recovery()` con timeout de 600 s.
- Antes de reconectar, el worker mata procesos zombie del browser (instancias previas que quedaron colgadas) usando `_kill_process_tree`.
- Los mensajes pendientes cuya fecha de envio ya paso (vencidos durante la suspension) y tienen repeticion activa se reprograman para ejecutarse de inmediato.
- Los mensajes sin repeticion que vencieron durante la suspension se omiten (no se envian retroactivamente).
- El contador `_schedule_generation` se incrementa en cada ciclo de cancel/reschedule. Los callbacks `after` capturan su generacion al momento de crearse; si al dispararse la generacion actual difiere de la capturada, el callback se descarta sin enviar.
- Esto garantiza que los timers vencidos durante hibernacion que se disparan tras el reschedule no generen envios duplicados.
- El log indica cuantos mensajes con repeticion fueron reprogramados para envio inmediato post-hibernacion.

### Notas de Implementacion

- Watchdog: metodo `_start_sleep_watchdog` en `WhatsAppSchedulerApp`; hilo daemon que compara `time.monotonic()` contra el tiempo esperado en intervalos de 30 s.
- Umbral de deteccion: gap > 60 s entre tiempo esperado y real.
- Recovery en backend: comando `post_sleep_recover` enviado al `BrowserWorker` via `worker.call`; el worker mata zombies, cierra la conexion existente y vuelve a ejecutar `bind_whatsapp_tab`.
- Timeout extendido (600 s) justificado por: kill de zombies (~20 s) + relaunch del browser (~60 s) + CDP retries (~270 s con 3 reintentos de 90 s cada uno).
- Reschedule de mensajes post-wake: metodo `_reschedule_after_wake` en la GUI; itera `self.scheduled_messages`, identifica los vencidos con repeticion activa, cancela los `after` anteriores y los reagenda con `after(0, ...)` para ejecucion inmediata.

---

## 4. Soporte Multi-Idiomas (ES/EN)

**Estado:** Activo

### Descripcion

La aplicacion soporta dos idiomas: Espanol (idioma canónico/interno) e Ingles. El idioma se selecciona desde la UI mediante un combobox en la barra superior. Todos los textos de la interfaz (etiquetas, botones, mensajes de estado, opciones de combobox, nombres de dias) se obtienen a traves del objeto `Translator`, que sirve la traduccion adecuada segun el idioma activo. Los valores de configuracion interna (opciones de repeticion, claves de config.json) siempre se almacenan en espanol como valores canonicos.

### Criterios de Aceptacion

- La UI incluye un selector de idioma ("Idioma:" / "Language:") en la barra de controles superior.
- Los idiomas disponibles son: Espanol (es) y English (en).
- Todos los textos visibles en la interfaz (titulos, botones, etiquetas, mensajes de estado, opciones de repeticion, nombres de dias de la semana) se traducen al idioma seleccionado.
- El idioma seleccionado se persiste en `config.json` bajo `global.language`.
- Al cambiar de idioma se muestra un aviso indicando que es necesario reiniciar la aplicacion para aplicar el cambio.
- Los valores internos de repeticion (almacenados en config.json) permanecen siempre en espanol: "Ninguno", "Cada minuto", "Cada hora", "Diariamente", "Semanalmente", "Mensualmente".
- `Translator.display_to_canonical(display)` convierte el texto de pantalla (en cualquier idioma) al valor canonico en espanol para persistencia.
- `Translator.canonical_to_display(canonical)` convierte el valor canonico al texto traducido para mostrarlo en la UI.
- Si una clave de traduccion no existe en el idioma activo, se usa el catalogo espanol como fallback.
- Si el idioma solicitado no esta soportado, se usa espanol por defecto.

### Notas de Implementacion

- Modulo: `backend/i18n.py`.
- Clase principal: `Translator`; acepta `lang` en constructor o via propiedad `lang`.
- Catalogos: `_ES` (espanol) y `_EN` (ingles), ambos diccionarios `Dict[str, object]`.
- Registro de idiomas: `_CATALOGS: Dict[str, Dict]` — agregar un nuevo idioma requiere solo anadir una entrada aqui y el catalogo correspondiente.
- Metodo `t(key, **kwargs)`: resuelve la cadena con formato (`str.format(**kwargs)`) de forma segura (captura `KeyError`/`ValueError`).
- Metodos especializados: `days()` retorna lista de 7 nombres; `repeat_options()` retorna lista de 6 opciones; ambos en el idioma activo.
- `CANONICAL_REPEAT_OPTIONS`: lista importable con los 6 valores canonicos en espanol (usado por la GUI para validacion).
- La instancia `Translator` se crea en `WhatsAppSchedulerApp.__init__` con el idioma leido de `config_store` antes de construir la ventana.

---

## 5. Sistema de Logging

**Estado:** Activo

### Descripcion

La aplicacion mantiene dos archivos de log separados con timestamp en el nombre: uno para eventos de la aplicacion (`logaplicacion<stamp>.txt`) y otro exclusivo para mensajes enviados (`logmensajes<stamp>.txt`). Adicionalmente, los eventos se muestran en tiempo real en el widget de texto de la UI. El sistema rota automaticamente los logs, conservando solo los 3 archivos mas recientes de cada tipo.

### Criterios de Aceptacion

- Al iniciar la aplicacion se crean dos nuevos archivos de log con el timestamp del momento de inicio (formato `YYYYMMDD_HHMMSS`).
- Cada entrada de log incluye fecha y hora con formato `YYYY-MM-DD HH:MM:SS`.
- Los eventos de la aplicacion (errores, cambios de estado, reconexiones, etc.) se escriben en `logaplicacion<stamp>.txt`.
- Cada mensaje enviado exitosamente se registra en `logmensajes<stamp>.txt` con el contacto y el texto del mensaje.
- Los eventos de la aplicacion tambien se muestran en el widget `Text` de la UI (panel inferior), con scroll automatico hacia la ultima linea.
- El sistema de rotacion elimina archivos de log que superen los 3 mas recientes de cada tipo, comparando por fecha de modificacion.
- Las escrituras en disco son thread-safe (protegidas por `threading.Lock`).
- En modo ejecutable (.exe compilado con PyInstaller), los logs se crean en el mismo directorio del ejecutable (no en el CWD del proceso).
- En modo desarrollo, los logs se crean en el directorio de trabajo actual.
- El callback de UI se captura atomicamente antes de invocarse para evitar race conditions si otro hilo lo anula entre el `if` y la llamada.

### Notas de Implementacion

- Modulo: `backend/logging_service.py`, clase `LoggingService`.
- Deteccion de modo frozen (PyInstaller): `getattr(sys, "frozen", False)` — si True, `_base_dir = os.path.dirname(sys.executable)`.
- Rotacion: funcion `rotate_logs(pattern, keep=3)` usando `glob.glob` + `os.path.getmtime`.
- La rotacion se ejecuta antes de crear los nuevos archivos (al instanciar `LoggingService`).
- Metodos publicos: `log_app(message)`, `log_message_sent(contact, message)`, `set_ui_callback(callback)`, `close()`.
- La GUI llama `logger.set_ui_callback(self._append_log_line)` despues de construir los widgets pero antes de arrancar el backend, garantizando que los primeros logs del backend ya tengan callback disponible.
- `_append_log_line` en la GUI encolara la actualizacion en el hilo principal via `root.after(0, ...)` si se llama desde un hilo secundario.

---

## 6. Persistencia de Configuracion

**Estado:** Activo

### Descripcion

Toda la configuracion de la aplicacion se almacena en un archivo `config.json` en el directorio de trabajo. Al iniciar, la configuracion se carga y se fusiona con los valores por defecto (deep merge), garantizando que campos nuevos anadidos en versiones posteriores siempre tengan un valor valido. Los datos de los 4 grupos de mensajes (contactos, textos, fechas, opciones de repeticion) tambien se persisten en este archivo.

### Criterios de Aceptacion

- Si `config.json` no existe al iniciar, se crea automaticamente con todos los valores por defecto.
- Si `config.json` existe pero esta corrupto (JSON invalido), se genera un backup (`config.json.bak`) y se recrea con valores por defecto sin crashear la aplicacion.
- Los campos presentes en el archivo se preservan; los campos faltantes (nuevos en la version actual) se completan con defaults mediante deep merge.
- La configuracion global incluye: navegador seleccionado, rutas de los 4 navegadores, puerto CDP, timeouts, numero de mensajes por grupo, geometria y estado de la ventana, idioma, y otros parametros avanzados del worker.
- Cada grupo de mensajes almacena una lista de hasta 4 bloques con: contacto, mensaje, fecha, hora, minuto, ampm, repeticion, checkbox enviar, dias seleccionados.
- Los navegadores soportados y sus rutas por defecto estan definidos en `config_store.py`: Opera, Brave, Chrome, Edge.
- Las rutas legacy (claves `opera_path`, `brave_path`, etc.) se migran automaticamente al nuevo formato `browser_paths` dict.
- La geometria y posicion de la ventana principal se guardan al cerrar y se restauran al iniciar.
- El boton "Guardar configuracion" en la UI escribe el estado actual de todos los campos al archivo.
- El boton "Restaurar rutas" restablece las rutas de los navegadores a sus valores por defecto.

### Notas de Implementacion

- Modulo: `backend/config_store.py`, clase `ConfigStore`.
- Formato: JSON con indentacion de 4 espacios, codificacion UTF-8, `ensure_ascii=False`.
- Deep merge: funcion `_deep_merge(target, defaults)` — recursiva para dicts, `setdefault` para valores escalares (preserva valores existentes, solo rellena ausentes).
- Estructura top-level del JSON: `global` (dict de parametros), `messages_group1` a `messages_group4` (listas de dicts).
- Funcion `_ensure_len(items, count)` garantiza que cada grupo tenga exactamente `num_messages_groupN` bloques (rellena con bloques vacios o trunca si hay mas).
- Acceso desde GUI: metodos `get_global(key, default)`, `set_global(key, value)`, `get_group_messages(group_id)`, `set_group_messages(group_id, messages)`.
- `ConfigStore` se instancia como primer paso en `WhatsAppSchedulerApp.__init__`, antes de crear la ventana, para que el idioma y la geometria esten disponibles en la construccion de la UI.

---

## 7. Boton "Comprame una cerveza" (PayPal)

**Estado:** Activo (implementado en V8.2.0, refinado en V8.4.0 con CTkButton)

### Descripcion

Boton de donaciones voluntarias en la interfaz que abre la pagina PayPal del desarrollador en el navegador del sistema. Implementado como `CTkButton` con color ambar distintivo (`#F5A623`) en la barra de controles inferior de la ventana principal.

**URL de donacion:** `https://www.paypal.com/donate/?hosted_button_id=ZABFRXC2P3JQN`

### Criterios de Aceptacion

- Existe un boton visible etiquetado "Comprame una cerveza" (ES) / "Buy me a beer" (EN) / "Me pague uma cerveja" (PT).
- Al hacer clic, se abre la URL de PayPal en el navegador por defecto del sistema (`webbrowser.open`).
- El boton respeta el idioma activo y usa la clave i18n `btn_donate`.
- El boton no interfiere con las acciones de programacion ni con el flujo de cierre.
- La URL esta definida como constante `_DONATE_URL` en `frontend/gui.py`.
- El boton es visualmente distinguible mediante color ambar y tamano reducido (secundario).

### Notas de Implementacion

- Constante: `_DONATE_URL = "https://www.paypal.com/donate/?hosted_button_id=ZABFRXC2P3JQN"` en `frontend/gui.py`.
- Widget: `ctk.CTkButton` con `fg_color="#F5A623"`, `hover_color="#D4891A"`, `corner_radius=6`.
- El sistema de temas preserva el color ambar del boton de donacion (excluido del restyle recursivo en `_theme_children`).
- Ubicacion: zona inferior de la ventana principal, debajo de los botones "Programar" y "Salir".

---

## 8. [PENDIENTE] Multi-Idioma Extendido

**Estado:** Pendiente

### Descripcion

Ampliar el soporte de idiomas mas alla de Espanol e Ingles, agregando catalogo(s) para otros idiomas (ej. Portugues, Frances, Aleman) sin necesidad de modificar la logica de la aplicacion. La arquitectura actual del modulo `i18n.py` ya soporta N idiomas mediante el diccionario `_CATALOGS`; solo se requiere definir los nuevos catalogos y actualizar el selector de idioma en la UI para incluirlos.

### Criterios de Aceptacion

- Cada nuevo idioma tiene un catalogo completo que cubre todas las claves presentes en `_ES` (idioma referencia).
- El selector de idioma en la UI lista dinamicamente todos los idiomas registrados en `_CATALOGS` sin necesidad de cambios en la GUI.
- Si una clave no esta traducida en el nuevo idioma, el sistema usa el catalogo espanol como fallback automaticamente (comportamiento heredado del metodo `t()`).
- Los valores canonicos de repeticion (almacenados en config.json) permanecen en espanol independientemente del idioma de la UI.
- Las opciones de repeticion del nuevo idioma se integran correctamente con `display_to_canonical` y `canonical_to_display`.
- La aplicacion no requiere reinicio para descubrir nuevos idiomas si se agregan en caliente (deseable, no obligatorio para MVP).
- La lista de idiomas soportados es accesible via `Translator.supported_languages()`.

### Notas de Implementacion

- Para agregar un idioma nuevo: (1) definir el dict `_XX: Dict[str, object]` con todas las claves de `_ES`; (2) registrarlo en `_CATALOGS["xx"] = _XX`; no se requieren mas cambios en logica.
- El selector de idioma en la GUI debe obtener las opciones via `Translator.supported_languages()` en lugar de una lista hardcodeada.
- Considerar externalizar los catalogos a archivos `.json` o `.toml` por idioma para facilitar contribuciones de traductores sin tocar codigo Python.
- La clave `"days"` almacena una lista de 7 strings (no un string); el metodo `days()` la maneja como caso especial — mantener esta convencion en nuevos catalogos.
- La clave `"version_label"` usa el placeholder `{v}` — todos los catalogos deben incluirla con el mismo placeholder.

---

---

## 9. GUI Moderna con CustomTkinter

**Estado:** Activo (implementado en V8.4.0)

### Descripcion

Migracion parcial de la GUI de Tkinter puro a una combinacion hibrida Tkinter + CustomTkinter (`customtkinter==5.2.2`). Los botones principales (`Programar`, `Salir`, `Donar`) se renderizaron con `CTkButton` que ofrecen esquinas redondeadas, modos de apariencia (claro/oscuro) nativos, y tema de color verde coherente con la marca WhatsApp. El resto de la UI (grupos de mensajes, listboxes, labels) permanece en Tkinter clasico.

### Criterios de Aceptacion

- Los botones "Programar mensajes", "Salir" y "Comprame una cerveza" son `CTkButton` con esquinas redondeadas (`corner_radius=8`).
- Existe un boton toggle "Oscuro/Claro" en la barra superior que alterna el modo de apariencia en tiempo real.
- El modo de apariencia se persiste en `config.json` bajo `global.theme` ("light" o "dark").
- Al activar modo oscuro: fondo `#1A1A2E`, logs `#0D1117` con texto verde, tabs y botones en paleta oscura.
- Al activar modo claro: fondo `#F0F2F5`, estilo visual WhatsApp verde/blanco.
- `ctk.set_default_color_theme("green")` se llama antes de crear cualquier widget CTk.
- `ctk.set_appearance_mode()` sincroniza todos los widgets CTk al modo activo.
- La funcion `_theme_children()` aplica el tema recursivamente a widgets Tkinter clasicos, preservando el color ambar del boton de donacion.
- El selector de tema no provoca reinicios ni perdida de datos configurados.

### Notas de Implementacion

- Dependencia: `customtkinter==5.2.2`, `Pillow` (requerido por CTk para iconos).
- Paletas de colores: diccionario `_THEMES` con entradas "light" y "dark" en `frontend/gui.py`.
- Colores de marca: `_C_PRIMARY="#075E54"`, `_C_ACCENT="#128C7E"`, `_C_ACTION="#25D366"`.
- `CTkButton` y `CTkFont` son los unicos widgets CTk usados; el resto del arbol es Tkinter puro.
- `_theme_children(widget, th, area)` itera recursivamente y configura `bg/fg/activebackground` segun tipo de widget, saltando widgets cuyo `type.__name__` empiece por "CTk" (auto-tematizan via CTk).
- ADR asociado: ADR-008.

---

## 10. Confiabilidad de Largo Plazo

**Estado:** Activo (implementado en V8.5.0)

### Descripcion

Conjunto de cuatro mejoras independientes que resuelven la perdida de gestion del bot tras varios dias de ejecucion continua sin reiniciar la aplicacion. Los problemas raiz documentados: (1) keepalive ciego al QR, (2) retries que abandonan mensajes permanentemente, (3) cuadro de busqueda que no se limpia con overlay abierto, (4) instancia Playwright que se vuelve stale.

### Criterios de Aceptacion

#### 10.1 Keepalive con deteccion de sesion expirada
- El ciclo de keepalive (cada `keepalive_interval_sec`, default 60 s) detecta no solo la desconexion CDP sino tambien la pantalla de login/QR de WhatsApp Web.
- Si `_looks_like_login_required()` retorna True durante el keepalive, se dispara `_hard_recover("keepalive")` automaticamente.
- El log muestra `[KEEPALIVE] Conexion CDP inestable: WhatsApp Web requiere reautenticacion` al detectar el QR.

#### 10.2 Mensajes repetitivos nunca se abandonan
- Cuando `_retry_message_delivery` agota `max_attempts` (default 20), los mensajes con `repeat != "Ninguno"` (o grupos con items repetitivos) NO se descartan.
- En su lugar, se reinicia el contador de retries y se reprograma el mensaje con un cooldown de 300 s (5 min).
- Mensajes de un solo disparo (`repeat == "Ninguno"`, no es grupo) se descartan normalmente al agotar retries.
- El log indica: `[RETRY] Reintentos agotados para '<contacto>'. Reprogramando en 300s`.

#### 10.3 Cuadro de busqueda de contacto: limpieza robusta
- `_focus_global_search()` presiona `Escape` antes de enfocar el campo, cerrando cualquier panel de busqueda activo.
- `_clear_global_search()` tambien presiona `Escape` antes de limpiar el campo.
- Ambos metodos usan `triple_click()` antes de `Ctrl+A+Delete` para garantizar la seleccion completa del contenido del `contenteditable`.
- Se agregan selectores CSS adicionales como fallback para mayor compatibilidad con futuras versiones de WhatsApp Web.

#### 10.4 Instancia Playwright validada antes de reusar
- `_connect_over_cdp()` ejecuta un health-check (`playwright.chromium`) antes de reusar la instancia existente.
- Si el health-check lanza excepcion (instancia stale), se detiene la instancia invalida y se crea una nueva via `sync_playwright().start()`.
- El log indica `[CDP] Instancia Playwright stale detectada. Reiniciando instancia...` cuando ocurre.

### Notas de Implementacion

- Archivos modificados: `backend/browser_worker.py` (keepalive, search-box, playwright health-check), `frontend/gui.py` (retry reprogram).
- `_looks_like_login_required()` ya existia en `browser_worker.py` para detectar pantalla de QR; se reutilizo en keepalive.
- El cooldown de 5 min al agotar retries evita spam de intentos cuando el sistema esta en un estado de falla persistente.
- `triple_click()` es un metodo nativo de Playwright que selecciona todo el contenido de un elemento con un triple click del mouse.

---

*Fin del documento — WhatsApp Message Scheduler SDD v1.2*
