# Architecture Decision Records — WhatsApp Message Scheduler

Proyecto: WhatsApp Message Scheduler
Version de referencia: V8.5.0
Responsable: erickson558
Fecha: 2026-06-03

---

## ADR-001 — Separacion Frontend/Backend

**Estado:** Aceptado

### Contexto

La aplicacion necesita coordinar una interfaz grafica de usuario (GUI) con operaciones de automatizacion de browser que son inherentemente bloqueantes y de larga duracion (conexion CDP, busqueda de contactos, envio de mensajes). Mezclar ambas responsabilidades en un unico modulo crearia acoplamiento fuerte, dificultaria las pruebas y bloqueria el hilo principal de Tkinter con operaciones de I/O.

### Decision

Se adopta una separacion estricta en dos capas:

- **Frontend** (`frontend/gui.py`, `WhatsAppSchedulerApp`): responsable exclusivamente de la interfaz Tkinter, la programacion temporal de mensajes (`after()`), y la coordinacion de configuracion. Nunca toca Playwright directamente.
- **Backend** (`backend/whatsapp_backend.py`, `WhatsAppBackend`; `backend/browser_worker.py`, `BrowserWorker`): contiene toda la logica de automatizacion del browser. Expone una fachada de metodos sincronicos thread-safe hacia la GUI.
- El punto de entrada `enviar_whatsapp.py` es un thin wrapper de dos lineas que delega inmediatamente a `frontend.gui.main`.

Los modulos de soporte (`config_store.py`, `i18n.py`, `logging_service.py`) pertenecen al paquete `backend` pero son accedidos directamente por el frontend donde corresponde (configuracion, traduccion, logging).

### Consecuencias

**Positivas:**
- El hilo principal de Tkinter nunca se bloquea; las operaciones lentas ocurren en el hilo del worker.
- Cada capa puede evolucionar de forma independiente (por ejemplo, reemplazar Tkinter por otra GUI sin tocar Playwright).
- La fachada `WhatsAppBackend` encapsula los timeouts y el manejo de errores, simplificando el codigo de la GUI.

**Negativas:**
- La comunicacion via cola introduce complejidad (serializar comandos, esperar respuestas con timeout).
- El estado del contacto seleccionado se duplica entre `WhatsAppBackend._selected_contact` y el worker, requiriendo coordinacion cuidadosa para evitar race conditions.

---

## ADR-002 — Tkinter como Framework de GUI (con CustomTkinter hibrido desde V8.4.0)

**Estado:** Aceptado (evolucionado)

### Contexto

Se requeria una GUI de escritorio para Windows que permitiera a usuarios no tecnicos programar mensajes de WhatsApp con calendarios, selectores de hora, repeticion periodica y configuracion de navegador. Las alternativas evaluadas incluian: PyQt6/PySide6, wxPython, Dear PyGui y Tkinter.

### Decision

Se selecciona **Tkinter** (con el paquete complementario `tkcalendar` para el selector de fecha) como framework de GUI base. Desde V8.4.0 se adopta adicionalmente **CustomTkinter** en un enfoque hibrido: los botones principales usan `CTkButton` para esquinas redondeadas y soporte nativo de modo oscuro/claro, mientras que el resto de la UI permanece en Tkinter clasico. Ver ADR-008 para la decision detallada de la adopcion de CustomTkinter.

Razones para la seleccion original de Tkinter:
- Viene incluido en la distribucion estandar de CPython (sin dependencia extra en produccion).
- Integra nativamente con el bucle de eventos de Python, simplificando la programacion temporal via `root.after()`.
- Compatibilidad directa con PyInstaller: genera ejecutables `.exe` sin dependencias de DLLs externas.
- Curva de aprendizaje baja para mantenimiento futuro por el equipo.
- El widget `ttk.Notebook` permite organizar los 4 grupos de mensajes en pestanas sin codigo adicional.

Se implementa el patron de generacion (`_schedule_generation`) para invalidar callbacks `after()` pendientes tras cancelaciones, solucionando el problema de doble ejecucion post-hibernacion que Tkinter no garantiza por orden entre `after(0,...)` y timers vencidos.

### Consecuencias

**Positivas:**
- Distribucion como ejecutable unico: `enviar_whatsapp.exe` sin instaladores ni dependencias del sistema.
- La API `root.after()` permite programar mensajes futuros de forma precisa sin hilos adicionales.
- `tkcalendar.DateEntry` provee un selector de fecha nativo con aspecto adecuado.
- Con CTk (V8.4.0+): botones modernos con esquinas redondeadas y toggle de modo oscuro/claro real.

**Negativas:**
- Tkinter clasico tiene limitaciones esteticas; mitigado parcialmente con CustomTkinter en elementos principales.
- El sistema `after()` no es preciso a nivel de milisegundos; puede desfasar ligeramente en sistemas bajo carga.
- `tkcalendar` es una dependencia adicional que requiere empaquetarse explicitamente en el `.spec` de PyInstaller.
- La mezcla Tkinter/CTk requiere `_theme_children()` recursivo para mantener coherencia visual entre los dos sistemas de widgets.

---

## ADR-003 — Playwright para Automatizacion del Browser

**Estado:** Aceptado

### Contexto

WhatsApp Web no expone una API publica. La unica forma de enviar mensajes de forma programatica es automatizar un browser real que ya tenga la sesion de WhatsApp Web iniciada. Se evaluaron: Selenium, Playwright, pyautogui y conexion directa via WebSockets al protocolo de WhatsApp.

### Decision

Se utiliza **Playwright** (sync API via `playwright.sync_api`) conectado al browser del usuario mediante el **protocolo CDP** (Chrome DevTools Protocol) en el puerto `remote_debugging_port` (default: 9222). El flujo es:

1. El usuario lanza su browser habitualmente (Opera, Brave, Chrome o Edge) con `--remote-debugging-port=9222`.
2. `BrowserWorker` detecta si el browser ya esta corriendo (via `socket` TCP al puerto) o lo lanza el mismo.
3. Se conecta via `playwright.chromium.connect_over_cdp()` con timeout configurable (`cdp_timeout`, default: 90 s).
4. Enumera las paginas abiertas y enlaza la que contiene WhatsApp Web.
5. Usa selectores CSS/aria de WhatsApp Web para buscar el contacto y enviar el mensaje.

Se implementa un mecanismo de keepalive periodico (ping a la pagina) y relaunch automatico si se pierde la conexion (`relaunch_on_disconnect`).

### Consecuencias

**Positivas:**
- El usuario mantiene su sesion de WhatsApp Web sin QR adicional; Playwright simplemente "toma el control" de un browser ya autenticado.
- Playwright es mas robusto y rapido que Selenium para automatizacion moderna, con mejor soporte para SPAs.
- Soporte multi-browser (Opera, Brave, Chrome, Edge) con una sola implementacion.
- El modo CDP es menos invasivo que lanzar un browser controlado por Playwright desde cero.

**Negativas:**
- `playwright` es una dependencia de gran tamano que requiere los binarios del browser; en el `.spec` se necesitan `collect_submodules('playwright')` y los hidden imports `playwright.sync_api` / `playwright._impl._errors`.
- La sincronizacion post-hibernacion es compleja: el puerto CDP puede tardar hasta varios minutos en restaurarse, requiriendo timeouts extendidos (`_TIMEOUT_POST_SLEEP = 600 s`) y logica de reintento.
- Los selectores de WhatsApp Web pueden cambiar con actualizaciones de la aplicacion, requiriendo mantenimiento reactivo.
- No se pueden ejecutar pruebas automatizadas sin un browser real y una sesion activa de WhatsApp.

---

## ADR-004 — Patron Worker Queue Thread-Safe

**Estado:** Aceptado

### Contexto

Playwright (sync API) no es thread-safe: todas las operaciones sobre `Page`, `Browser` y `Context` deben ejecutarse desde el mismo hilo. Sin embargo, la GUI programa mensajes en hilos Tkinter (`after()`) y puede necesitar enviar mensajes a multiples contactos casi simultaneamente (por ejemplo, tras despertar de hibernacion). Se requeria un mecanismo para serializar las operaciones de browser sin bloquear la GUI.

### Decision

Se implementa el patron **Worker Queue** en `BrowserWorker(threading.Thread)`:

- `BrowserWorker` es un daemon thread que posee en exclusiva todos los objetos de Playwright.
- La GUI se comunica con el worker a traves de `queue.Queue` (FIFO, thread-safe por diseno de Python): envia un `dict` con el comando y kwargs, y recibe la respuesta en un `queue.Queue` de un solo uso.
- El metodo `worker.call(command, timeout, **kwargs)` encapsula este protocolo: pone el request en `req_q`, bloquea esperando la respuesta con timeout, y re-lanza excepciones recibidas del worker.
- `WhatsAppBackend` anade un nivel adicional: el `_delivery_lock` serializa el par atomico `select_contact + send_message` para evitar que dos mensajes programados casi simultaneamente intercalen sus operaciones.
- Un contador de generacion (`_schedule_generation`) en la GUI invalida callbacks `after()` de iteraciones anteriores, previniendo doble envio post-hibernacion.

### Consecuencias

**Positivas:**
- Garantia de que Playwright siempre se usa desde un unico hilo, eliminando race conditions a nivel de browser.
- La GUI nunca se bloquea: `worker.call()` se invoca desde hilos de trabajo (no desde el hilo de Tkinter directamente).
- El patron es extensible: agregar nuevos comandos solo requiere implementar el handler en `BrowserWorker.run()` y llamar a `worker.call("nuevo_comando")`.

**Negativas:**
- Los timeouts en `worker.call()` deben ser generosos para cubrir escenarios de recuperacion (hasta 600 s), lo que puede hacer que un fallo tarde en manifestarse.
- La depuracion es mas compleja: errores en el worker se propagan como excepciones a traves de la cola, perdiendo el traceback original en algunos casos.
- El `_delivery_lock` introduce serializacion adicional: dos mensajes a contactos distintos no pueden enviarse en paralelo aunque tecnicamente podrian.

---

## ADR-005 — Persistencia JSON con config.json

**Estado:** Aceptado

### Contexto

La aplicacion necesita persistir entre sesiones: configuracion del browser (ruta, puerto, timeouts), mensajes programados (hasta 16 bloques en 4 grupos), y preferencias del usuario (idioma, geometria de ventana). Se evaluaron: SQLite, JSON plano, INI/TOML, y no persistencia (estado en memoria).

### Decision

Se utiliza un **archivo JSON** (`config.json`) gestionado por la clase `ConfigStore` con las siguientes caracteristicas:

- Esquema unico con secciones `global`, `messages_group1..4`.
- `_deep_merge` garantiza que claves nuevas (versiones futuras) se completan con defaults sin perder datos existentes del usuario.
- `_ensure_len` normaliza las listas de mensajes al tamano configurado (`num_messages_groupN`).
- `_migrate_legacy_browser_paths` convierte el esquema antiguo (claves planas como `opera_path`) al nuevo esquema anidado (`browser_paths.Opera`), permitiendo upgrades transparentes.
- En caso de `json.JSONDecodeError` o `OSError`, se crea un backup `.bak` y se regenera con defaults, evitando que un config corrupto crashee la aplicacion.
- El archivo se escribe con `json.dump(..., indent=4, ensure_ascii=False)` para ser legible y editable manualmente.

### Consecuencias

**Positivas:**
- Sin dependencias de base de datos: el archivo es portable y facil de inspeccionar/editar manualmente.
- El mecanismo de merge permite evolucionar el esquema entre versiones sin migraciones complejas.
- El backup automatico en caso de corrupcion protege los datos del usuario.
- PyInstaller puede empaquetar la aplicacion sin incluir motores de base de datos.

**Negativas:**
- No hay control de concurrencia a nivel de archivo: si dos instancias de la aplicacion se ejecutan simultaneamente, pueden corromperse mutuamente el `config.json`.
- El archivo crece linealmente con el numero de grupos y mensajes; no es adecuado si se escala a cientos de mensajes.
- No hay historial de cambios ni posibilidad de rollback fino mas alla del backup `.bak`.
- Las rutas del browser (incluyendo rutas de Windows con backslashes) deben manejarse con cuidado en la serializacion JSON.

---

## ADR-006 — PyInstaller para Empaquetado como Ejecutable

**Estado:** Aceptado

### Contexto

El publico objetivo son usuarios de Windows sin conocimientos de Python. Se requeria distribuir la aplicacion como un unico archivo ejecutable `.exe` sin requerir instalacion de Python, pip, ni dependencias adicionales. Las alternativas evaluadas: cx_Freeze, Nuitka, py2exe, y PyInstaller.

### Decision

Se utiliza **PyInstaller** (modo `onefile`, `console=False`) configurado mediante `enviar_whatsapp.spec`:

- `onefile`: todo queda en un unico `.exe` autocontenido, incluyendo el interprete Python y todas las dependencias.
- `console=False`: suprime la ventana de terminal negra al ejecutar la GUI en Windows.
- `upx=True`: compresion del ejecutable con UPX para reducir el tamano del binario.
- `icon=['enviar_whatsapp.ico']`: icono personalizado del ejecutable.
- Se recolectan explicitamente los datos de `tkcalendar` (`collect_data_files`) y todos los submodulos de `playwright` (`collect_submodules`), necesarios porque PyInstaller no los detecta automaticamente.
- `hiddenimports`: se declaran `playwright.sync_api` y `playwright._impl._errors` para garantizar su inclusion.
- Un script PowerShell (`build_exe.ps1`) orquesta la compilacion con opcion `-Clean` para limpiar artefactos previos.

### Consecuencias

**Positivas:**
- Distribucion de un unico archivo: el usuario descarga `enviar_whatsapp.exe` y ejecuta directamente.
- No se requiere Python instalado en la maquina del usuario final.
- La firma SHA-256 del ejecutable (`enviar_whatsapp.exe.sha256`) permite verificar la integridad del binario descargado.

**Negativas:**
- El ejecutable es grande (tipicamente >50 MB) porque incluye el interprete Python y todas las dependencias.
- El primer arranque es lento en modo `onefile` porque PyInstaller extrae el contenido a un directorio temporal (`runtime_tmpdir`).
- Playwright requiere que el usuario tenga el browser instalado en su sistema; los binarios del browser no se empaquetan en el `.exe`.
- Los antivirus pueden marcar el ejecutable como sospechoso (falso positivo) por el comportamiento de PyInstaller.
- Depurar un ejecutable empaquetado es mas dificil que depurar el codigo fuente directamente.

---

## ADR-007 — GitHub Actions para CI/CD y Release Automatizado

**Estado:** Aceptado

### Contexto

Se necesitaba un proceso repetible y libre de errores para generar y publicar nuevas versiones del ejecutable. El proceso manual (build local, upload manual a GitHub Releases) era propenso a inconsistencias entre versiones y olvidar actualizar el SHA-256.

### Decision

Se implementa un workflow de GitHub Actions (`.github/workflows/release.yml`) que se dispara en cada push a `main` o manualmente via `workflow_dispatch`:

1. **Checkout** del repositorio completo (`fetch-depth: 0` para acceso a todos los tags).
2. **Lectura de version** desde el archivo `VERSION` (fuente unica de verdad).
3. **Validacion de tag**: falla si el tag `vX.Y.Z` ya existe en el repositorio remoto, obligando al desarrollador a incrementar `VERSION` antes de mergear a `main`.
4. **Build del ejecutable** via `.\build_exe.ps1 -PythonExe python -Clean` en un runner `windows-latest`.
5. **Generacion del SHA-256** del ejecutable generado.
6. **Creacion del GitHub Release** con el tag de version, adjuntando el `.exe` y el `.sha256`, con notas autogeneradas (`--generate-notes`).

El workflow usa `permissions: contents: write` (minimo necesario) y `concurrency: cancel-in-progress: false` para evitar que dos releases simultaneos se interfieran.

### Consecuencias

**Positivas:**
- Proceso de release totalmente reproducible: el mismo script que corre localmente corre en CI.
- Garantia de que cada release en GitHub Releases corresponde exactamente al codigo de `main`.
- La validacion del tag previene sobreescribir releases existentes por descuido.
- El SHA-256 automatico permite a los usuarios verificar la integridad del binario descargado.
- Las notas de release se generan automaticamente a partir de los commits.

**Negativas:**
- El build tarda varios minutos en el runner de GitHub (instalacion de dependencias Python + PyInstaller).
- Cualquier push a `main` dispara un intento de release; si `VERSION` no se actualizo, el workflow falla (comportamiento intencionado pero puede sorprender).
- El runner `windows-latest` tiene un browser preinstalado pero la sesion de WhatsApp no puede probarse en CI (no hay pruebas de integracion automatizadas).
- La dependencia de `GITHUB_TOKEN` y permisos de escritura en el repositorio debe gestionarse correctamente en entornos fork o con restricciones de seguridad adicionales.

---

## ADR-008 — CustomTkinter para Componentes Visuales Mejorados

**Estado:** Aceptado (V8.4.0)

### Contexto

La GUI en Tkinter puro tenia aspecto anticuado (botones rectangulares planos, sin soporte real de modo oscuro). Los usuarios esperan interfaces modernas con esquinas redondeadas y soporte de tema oscuro. Refactorizar toda la GUI a Qt/wxPython tendria un costo altisimo y romperia la integracion con `root.after()`. Se evaluaron: PyQt6, tkinter-styled, ttkbootstrap, y CustomTkinter.

### Decision

Se adopta **CustomTkinter 5.2.2** en modo hibrido para modernizar exclusivamente los elementos de accion principal (botones "Programar", "Salir", "Donar"). La decision de mantener el resto en Tkinter clasico se baso en:

- Migracion minima de riesgo: solo 3 widgets criticos cambian de tipo; el arbol de widgets principal (grupos de mensajes, listboxes, labels, notebook) permanece sin cambios.
- `ctk.set_appearance_mode("dark"|"light")` sincroniza todos los widgets CTk con un solo comando; los widgets Tkinter se actualizan via `_theme_children()`.
- `ctk.set_default_color_theme("green")` establece el color base verde coherente con la marca WhatsApp antes de crear cualquier widget CTk.
- CustomTkinter ya es compatible con PyInstaller via el hook estandar `hook-customtkinter.py`.
- `Pillow` (requerido por CTk para manejo de imagenes en iconos) ya estaba en el entorno del proyecto.

El sistema de temas usa el diccionario `_THEMES` con paletas "light" y "dark" aplicadas via `_theme_children()` para widgets Tkinter y via `ctk.set_appearance_mode()` para widgets CTk.

### Consecuencias

**Positivas:**
- Botones modernos con esquinas redondeadas, colores hover, y cursor hand2 sin CSS ni recursos externos.
- Toggle de modo oscuro/claro en tiempo real sin reiniciar la aplicacion.
- La preferencia de tema persiste en `config.json` entre sesiones.
- La migracion fue no-invasiva: el codigo de logica de scheduling y backend no cambio.

**Negativas:**
- Nueva dependencia `customtkinter==5.2.2` y `Pillow` en `requirements.txt`.
- La coexistencia de widgets Tkinter y CTk requiere `_theme_children()` para mantener coherencia; si se agregan nuevos widgets CTk, deben excluirse del recorrido recursivo (chequeo `type.__name__.startswith("CTk")`).
- CustomTkinter tiene su propio ciclo de mantenimiento; actualizaciones mayores pueden romper la API de configuracion de colores.
- El boton de donacion (ambar) debe excluirse explicitamente del restyle recursivo para no ser sobreescrito por el tema activo.

---

## ADR-009 — Estrategia de Confiabilidad para Ejecucion de Largo Plazo

**Estado:** Aceptado (V8.5.0)

### Contexto

Tras dias de ejecucion continua sin reiniciar la aplicacion, el bot dejaba de enviar mensajes. El diagnostico identifico cuatro causas raiz independientes: (1) keepalive que no detectaba la pantalla de QR/sesion-expirada de WhatsApp Web; (2) mensajes repetitivos que se abandonaban permanentemente al agotar 20 reintentos; (3) el cuadro de busqueda de contacto que no se limpiaba correctamente si habia un overlay/panel de busqueda activo; (4) la instancia Playwright que quedaba stale tras dias de uso y no se detectaba.

### Decision

Se implementan cuatro mejoras independientes, cada una resolviendo una causa raiz especifica:

**1. Keepalive con deteccion de sesion expirada:**
Se agrega la llamada `_looks_like_login_required()` dentro del bloque try del keepalive. Si retorna True, se lanza excepcion y se dispara `_hard_recover("keepalive")`. Antes solo se detectaba desconexion CDP (evaluando `document.readyState`), que retorna "complete" incluso con el QR visible.

**2. Mensajes repetitivos nunca se abandonan:**
En `_retry_message_delivery`, cuando `retries >= max_attempts`, se verifica si el mensaje tiene `repeat != "Ninguno"` o si es un grupo con items repetitivos. En ese caso se reinicia el contador y se reprograma con cooldown de 300 s en lugar de descartar. Mensajes de un solo disparo se descartan normalmente.

**3. Cuadro de busqueda: limpieza robusta:**
`_focus_global_search()` y `_clear_global_search()` presionan `Escape` antes de cualquier accion para cerrar paneles de busqueda activos. Se agrega `triple_click()` como metodo de seleccion mas confiable que `Ctrl+A` en elementos `contenteditable`. Se agregan selectores CSS adicionales para mayor compatibilidad con futuras versiones de WhatsApp Web.

**4. Playwright stale: health-check antes de reusar:**
`_connect_over_cdp()` accede a `self.playwright.chromium` antes de usarlo. Si lanza excepcion, se detiene la instancia invalida y se crea una nueva. Sin este check, una instancia stale causaria fallos silenciosos que solo se manifestaban tras horas de degradacion.

### Consecuencias

**Positivas:**
- El bot puede ejecutarse indefinidamente sin intervencion manual en condiciones normales (sin QR requerido).
- Los mensajes diarios/semanales/mensuales nunca se pierden permanentemente, incluso tras periodos de inestabilidad.
- La busqueda de contactos es mas robusta frente a estados intermedios de la UI de WhatsApp Web.
- La instancia Playwright se auto-sana sin requerir reinicio de la aplicacion.

**Negativas:**
- El keepalive ahora es mas costoso (agrega una verificacion DOM adicional cada 60 s). El impacto es despreciable.
- El cooldown de 5 min al agotar retries puede causar un breve retraso en la recuperacion tras un fallo prolongado.
- `triple_click()` en Playwright es una operacion de mouse real; en sistemas muy lentos puede tener comportamiento inesperado si el elemento se mueve entre el triple click y la siguiente accion.
