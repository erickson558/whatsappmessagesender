# Changelog

## [v8.7.6] — 2026-06-06
### Fixed
- CI: workflow Release fallaba en "Ensure tag does not exist yet" por dos causas: (1) `git fetch --tags --force` generaba archivos `.lock` stale en runner Windows (filesystem case-insensitive); reemplazado por `git ls-remote` que consulta el remoto sin writes locales. (2) `fetch-depth: 0` en el checkout descargaba todos los tags y también causaba lock conflicts; simplificado a checkout estándar sin fetch de historial completo.
- CI: simplificado checkout — eliminado `fetch-depth: 0` y `fetch-tags: false`; el step `Create GitHub release --generate-notes` no requiere historial local completo (GitHub lo resuelve server-side).

## [v8.7.5] — 2026-06-06
### Docs
- Agente `python-desktop-engineer`, skills `diagnose-bot` y `verify-selectors`, SDD `project-spec.md` actualizados con patrones de confiabilidad V8.7.4 (guard compose en `_clear_global_search`, `_ensure_chat_target` con `_is_compose_visible`, seleccion teclado-first, skill `/debug-wa-click`).
- Versión bumpeada a V8.7.5 para resolver conflicto de tag duplicado en GitHub Actions (el commit de docs anterior usaba el mismo tag v8.7.4 ya existente).

## [v8.7.4] — 2026-06-06
### Fixed
- Bug crítico: `_send_message` cerraba el chat tras abrir el compose box. Causa: `_clear_global_search()` se llamaba dentro de `_send_message` ANTES de escribir el mensaje; su `page.keyboard.press("Escape")` interno cerraba el chat en WA Web 2026, y el click en el search box volvía al modo búsqueda. Solución: removida la llamada a `_clear_global_search()` del flujo pre-escritura; se mueve a después del envío exitoso para limpiar el search box sin interrumpir el chat.
- Bug crítico: `_clear_global_search()` presionaba Escape incondicionalmente, cerrando cualquier chat abierto. Ahora verifica `_is_compose_visible()` antes de presionar Escape — solo lo hace cuando no hay chat activo.
- `_ensure_chat_target()`: usaba `_is_in_chat()` como única verificación; en WA Web 2026 esta función puede dar falso negativo (selectores del header cambiados), causando que `_select_contact` se llamara de nuevo innecesariamente (navegando al search y cerrando el chat). Ahora acepta `_is_compose_visible()` como señal válida de que el chat está abierto.

## [v8.7.3] — 2026-06-06
### Fixed
- Bug crítico: `_select_contact` revertía el chat al estado de búsqueda tras abrirlo. Causa raíz identificada en tres regresiones: (1) `blur()` en el search input antes del `page.mouse.click()` ocultaba el panel de resultados antes de que el click llegara al elemento, causando que las coordenadas apuntaran a área vacía; (2) falta de detección rápida de éxito — `_wait_header` esperaba hasta 9000ms sin verificar `_is_compose_visible()`, y durante esa espera las estrategias de fallback (ArrowDown+Enter) interrumpían el chat ya abierto; (3) ArrowDown sin guard de compose — si el chat estaba abierto pero el header no se detectaba, el ArrowDown lo navegaba a otro chat.
- Reescritura completa de la secuencia de estrategias en `_select_contact`:
  1. **Teclado primario**: ArrowDown → Enter → wait 1200ms → `_is_compose_visible()` → `return True` inmediato. No depende de coordenadas DOM ni selectores que cambien con WA Web.
  2. **Mouse sin blur**: JS-locate → `page.mouse.click(cx, cy)` (sin `blur()` previo) → wait 1200ms → `_is_compose_visible()` → `return True` inmediato.
  3. **Guard compose**: antes del loop Playwright, si `_is_compose_visible()` → `return True` sin ejecutar ninguna estrategia adicional.
  4. **Playwright fallback**: timeout reducido de 9000ms → 4000ms + check compose post-click.
  5. **ArrowDown final**: solo si `not _is_compose_visible()` para no interrumpir chat abierto.
### Added
- Skill `/debug-wa-click`: diagnóstico estructurado del flujo completo de selección de contacto en WA Web — identifica regresiones en blur/Escape/ArrowDown-guard, verifica selectores del panel lateral y composer, reporta con recomendaciones concretas.
### Docs
- SDD (`.claude/specs/project-spec.md`) actualizado a V8.7.3 con detalle de todas las versiones 8.7.x y los cambios de estrategia.

## [v8.7.1] — 2026-06-06
### Fixed
- Bug crítico: `_click_contact_js` hacía click en spans de subtítulo de grupos ("Albert Osorio is also in this group") antes que en el contacto directo. Nuevo filtro `isSecondarySpan()` detecta ancestros con data-testid/class indicando posición secundaria y los descarta; solo si no hay span primario se intenta con secundarios.
- Bug crítico: el click JS (`.click()` + `dispatchEvent`) desplazaba el elemento durante la animación de WA Web ANTES de que `page.mouse.click()` ejecutara, causando que el mouse cayera en coordenadas incorrectas (área vacía). Eliminados los clicks sintéticos del JS — ahora `_click_contact_js` **solo localiza y devuelve coordenadas**, y `_select_contact` hace un único `page.mouse.click()` limpio.
- Agregado `page.keyboard.press("Escape")` post-click para cerrar el overlay de búsqueda sin cerrar el chat, permitiendo que WA Web confirme la selección.

## [v8.7.0] — 2026-06-06
### Fixed
- Bug crítico: click JS abría el chat pero WA Web 2026 lo revertía inmediatamente al estado de búsqueda. Solución: `_click_contact_js` ahora devuelve las coordenadas del elemento (getBoundingClientRect), y `_select_contact` hace `page.mouse.move + page.mouse.click` con esas coordenadas para disparar la cadena completa de eventos de puntero (pointerdown, pointerup, mouseover) que WA Web requiere para mantener el chat abierto — exactamente lo que hace el mouse físico.
- `_is_context_alive`: `len(self.context.pages) >= 0` era siempre True independiente del estado CDP; corregido a `self.context.pages is not None` que realmente detecta conexión muerta.
- Guardia doble redundante en `_maybe_keepalive` eliminada.
- Variable muerta `self._we_started` eliminada (asignada en 3 lugares, nunca leída en condiciones).
- Import local `shutil` movido a nivel de módulo en `config_store.py`.
- Import local `datetime` redundante eliminado en `gui.py` (`_show_about`).
### Added
- Soporte WA Web 2026: selectores `[aria-label="Chats"]` y `[data-testid="chat-list"]` en `_click_contact_js` para localizar el panel lateral.
- Detección de resultados WA Web 2026 en `_type_search_variants`: `span[title]:visible` como cuarto check.
### Performance
- Startup ~0.8s más rápido: eliminado `time.sleep(0.008)` del loop de animación del splash (100 pasos × 8ms = animación puramente artificial).
- `bind_whatsapp_tab` diferido a `root.after(450)` para no competir con el renderizado inicial de la ventana principal.
### Refactor
- `_verify_message_sent`: lambda de normalización interna reemplazada por `_normalized_text` (ya existía como staticmethod).
- Comentarios redundantes eliminados en `_exec_cmd`, `run()` y `_launch_browser_proc`.

## [v8.6.2] — 2026-06-06
### Added
- Nuevos skills: `/annotate-code` (documenta módulos Python) y `/verify-selectors` (verifica selectores WA Web)
### Docs
- `browser_worker.py`: docstrings en 7 funciones de módulo, dataclass BrowserRuntimeSettings y 30 métodos del worker
- `config_store.py`: docstring de módulo, docstrings en todas las funciones y métodos públicos
- `logging_service.py`: docstring de módulo, docstrings en todos los métodos de la clase
- `whatsapp_backend.py`: docstring de módulo e `__init__`

## [v8.6.1] — 2026-06-06
### Fixed
- Bug raíz selección de contacto: click en `span` no abría el chat porque el XPath de ancestro fallaba en WA Web 2025
- Nuevo método `_click_contact_js`: usa JavaScript con DOM-walking (hasta 12 niveles) para encontrar el contenedor clickeable real; restringe búsqueda a `#pane-side` para no confundir spans del chat abierto
- `_get_header_name`: fallback JavaScript con `querySelector('#main header')` + `TreeWalker` de texto; independiente de data-testid que WA Web puede cambiar; ahora `_wait_header` puede confirmar el chat correctamente
- `_select_contact`: JS-click como estrategia primaria; XPath de ancestro ampliado con `@role='row'`, `@role='listitem'`, `@tabindex='0'` en el fallback Playwright

## [v8.6.0] — 2026-06-06
### Fixed
- Seleccion de contacto: bot escribia nombre en busqueda pero no abria el chat ni enviaba el mensaje
- `_collect_candidates`: agrega selectores de alta prioridad para panel de busqueda WA Web 2025 (`search-composition-list`, `default-search-results`, `pane-side`) y soporte para `role='row'`/`role='listitem'`
- `_type_search_variants`: aumenta espera de resultados de 550 ms a 900 ms; agrega deteccion de `role='row'`/`role='listitem'` para confirmar que resultados aparecieron
- `_get_header_name`: nuevos selectores `conversation-header`, `#main header span[title]`, `#main header [title]` y barrido de `[title]` en header para WA Web 2025
### Added
- Fallback de teclado en `_select_contact`: si ningun click confirmo apertura del chat, presiona ArrowDown+Enter para seleccionar el primer resultado de busqueda antes de limpiar el campo

## [v8.5.0] — 2026-06-03
### Fixed
- Keepalive "ciego": ahora detecta QR / sesion expirada de WhatsApp ademas de desconexion CDP; dispara hard-recover automatico al detectar pantalla de login tras dias de ejecucion
- Mensajes repetitivos ya no se abandonan permanentemente al agotar 20 reintentos; se reprograman con cooldown de 5 min para que el ciclo continue indefinidamente
- Cuadro de busqueda de contacto: presiona Escape antes de enfocar para cerrar paneles/overlays abiertos; usa triple_click como limpieza mas robusta junto a Ctrl+A+Delete
- Instancia Playwright validada con health-check antes de reusar; si esta stale tras dias de uso se recrea automaticamente evitando bloqueos silenciosos
### Added
- Skill /diagnose-bot: diagnostica el estado de la conexion WhatsApp (keepalive, retries, search-box, playwright) y produce reporte de salud con recomendaciones de accion

## [v8.4.0] — 2026-05-30
### Added
- Migracion a CustomTkinter: botones Programar, Salir y Donar con esquinas redondeadas
- Modo oscuro/claro real via ctk.set_appearance_mode() en todos los CTkButton
- Toggle de tema actualiza simultaneamente widgets tk (color) y CTk (apariencia)
- ctk.set_default_color_theme("green") para tema verde coherente con la marca

## [v8.3.3] — 2026-05-30
### Fixed
- Selectores del compositor WA Web 2025: aria-label sin nombre de contacto
- Boton Send: data-testid=send como selector prioritario sobre aria-label
### Added
- Sistema de temas light/dark con toggle en la barra superior
- Tema oscuro: fondo #1A1A2E, logs #0D1117 con texto verde, tabs verde WhatsApp
- Preferencia de tema persistida en config.json
- Funcion _theme_children() para restyle recursivo de todos los widgets

## [v8.3.2] — 2026-05-30
### Added
- Tema visual WhatsApp Pro: paleta de colores verde/blanco consistente
- Barra superior diferenciada con botones estilizados en verde teal
- Area de logs con fondo oscuro (terminal style) y fuente Consolas
- Reloj prominente en verde primario con fuente Segoe UI Bold
- Barra de estado con fondo blanco y padding mejorado
- Botones Programar y Salir con colores, flat relief y cursor hand2
- Tabs del Notebook activos en verde oscuro con texto blanco
- Agente gui-designer y skill /modernize-gui para mejoras futuras

## [v8.3.1] — 2026-05-30
### Added
- Barra de menús con opcion Ayuda > Acerca de y Cómprame una cerveza
- Dialogo About modal con nombre, version, autor y copyright
- Skill /fix-errors para QA, debugging y versionado profesional
- Claves i18n menu_help y menu_about en ES, EN y PT

## [v8.3.0] — 2026-05-30
### Added
- Botón "Cómprame una cerveza" con enlace de donación PayPal
- Soporte de idioma Portugués (PT-BR) con todas las traducciones
- Nuevo patrón i18n para key btn_donate en ES, EN y PT

## [v8.1.4] - 2026-04-14

### Correcciones de estabilidad y robustez

- **fix(config_store):** captura `json.JSONDecodeError` / `OSError` en `_load()` para que un `config.json` corrupto no crashee la aplicacion al iniciar. Se genera un backup `.bak` y se reinicia con valores por defecto.
- **fix(gui):** `_schedule_message` sincroniza el `datetime` del container de grupo al item mas proximo (`min(item_dts)`). Sin esto, containers con `datetime` en el pasado se disparaban en 1s aunque sus items fueran futuros, causando envios prematuros tras hibernacion.
- **fix(gui):** `_process_scheduled_message` (path de grupos) filtra items con `datetime > now + 30s` antes de agregarlos a `runnable`. Evita enviar items de un grupo que aun no son debidos cuando el container se dispara por el item mas proximo (grupos con modos de repeticion distintos entre items).
- **fix(logging_service):** `log_app` captura `_ui_callback` en variable local antes del check `if` para eliminar race condition donde otro hilo podia poner el callback a `None` entre la verificacion y la llamada, causando `TypeError`.
- **fix(logging_service):** rutas de archivos de log y patron de rotacion ahora usan directorio absoluto (`sys.executable` en modo frozen, `os.getcwd()` en desarrollo). Corrige logs creados en directorio incorrecto cuando el `.exe` se lanza desde un path distinto.
- **refactor(browser_worker):** eliminado dead code `and self._last_loop_time > 0` en `_maybe_keepalive` (condicion siempre `True` porque `_last_loop_time = now` se asigna en la linea anterior).

## [v8.1.3] - 2026-04-14

### Correcciones de race condition post-hibernacion (mensajes enviados al contacto equivocado)

- **fix(whatsapp_backend):** `send_message` ahora acepta parametro `contact` explicito. Antes dependia de `_selected_contact` (estado compartido), lo que causaba que cuando dos hilos ejecutaban `select_contact`+`send_message` concurrentemente, el segundo hilo sobreescribia `_selected_contact` antes de que el primero llamara `send_message`, enviando el mensaje al contacto incorrecto.
- **fix(whatsapp_backend):** agrega `_delivery_lock` (threading.Lock) para serializar el par `select_contact`+`send_message`. Impide que dos hilos de entrega ejecuten operaciones de browser simultaneamente.
- **fix(gui):** `_process_scheduled_message` ahora adquiere `backend._delivery_lock` antes de `select_contact`+`send_message`, y pasa el contacto explicitamente a `send_message` en ambos paths (grupos e individuales).
- **fix(gui):** `_reschedule_past_due_repeating_messages` solo actualiza el `datetime` del container del grupo si al menos un item interno fue efectivamente reprogramado. Antes siempre se actualizaba si el container tenia datetime en el pasado, causando envios inesperados a contactos cuyos proximos mensajes estaban en el futuro.
- **fix(browser_worker):** agrega cooldown de 30s en `_post_sleep_recover` para evitar doble recuperacion secuencial. El flag `_recovering_from_sleep` ya protegia ejecucion paralela; el nuevo campo `_last_sleep_recover_at` protege el caso donde el worker y el watchdog de la GUI encolan dos recuperaciones seguidas.

## [v8.1.2] - 2026-04-13

- **fix(gui):** corrige NameError critico — `repeat_value` se leia despues de ser usado en la validacion de fecha pasada; movido antes del bloque condicional
- **fix(browser_worker):** agrega flag `_recovering_from_sleep` para evitar recuperacion post-hibernacion doble cuando el worker y el watchdog de la GUI detectan el salto de tiempo simultaneamente
- **fix(gui):** `_reschedule_past_due_repeating_messages` itera sobre snapshots (`list(...)`) de la lista y los items para evitar RuntimeError si hilos de fondo modifican la coleccion
- **fix(gui):** escalonar cierre del splash (350ms) con apertura de la ventana principal (420ms) para evitar parpadeo visual

## [v8.1.1] - 2026-04-13

- **feat(gui):** agrega splash screen al iniciar la aplicacion con barra de progreso animada que refleja las etapas reales de carga (config → ventana → UI → backend → servicios)

## [v8.1.0] - 2026-04-13

### Correcciones de hibernacion del sistema (problema principal)
- **fix(browser_worker):** agrega deteccion de salto de tiempo en `_maybe_keepalive` para identificar cuando el sistema regresa de hibernacion/suspension. Al detectar un salto > 30s entre ciclos del worker, se dispara reconexion forzada con timeout extendido.
- **fix(browser_worker):** `_launch_browser_proc` ahora verifica si el navegador ya esta corriendo antes de lanzar uno nuevo. Si detecta PIDs activos, espera el timeout completo para que el puerto CDP se restaure, evitando perder la sesion de WhatsApp tras hibernar.
- **fix(browser_worker):** el timeout rapido de deteccion de browser existente se eleva de 2s a 12s durante la recuperacion post-hibernacion (`_quick_cdp_check_timeout`).
- **feat(browser_worker):** nuevo metodo `_post_sleep_recover()` que ejecuta reconexion completa con timeout extendido, especificamente disenado para el escenario de retorno de hibernacion.
- **feat(browser_worker):** nuevo comando `post_sleep_recover` en la cola del worker para que el backend pueda disparar la recuperacion desde la GUI.
- **feat(whatsapp_backend):** nuevo metodo `trigger_post_sleep_recovery()` para que la GUI llame la recuperacion post-hibernacion de forma segura desde un hilo separado.
- **feat(gui):** nuevo hilo vigilante `SleepWatchdog` que detecta retorno de hibernacion comparando tiempo real entre iteraciones. Al detectar suspension, dispara reconexion del browser y reprogramacion de mensajes pendientes.
- **fix(gui):** nuevo metodo `_reschedule_past_due_repeating_messages()` que al despertar de hibernacion, reprograma mensajes con repeticion cuya fecha quedo en el pasado para enviarlos en ~10 segundos.

### Otras mejoras de estabilidad
- **fix(whatsapp_backend):** todos los metodos `worker.call()` ahora tienen timeouts explicitos (120s para bind/send, 60s para select_contact, 90s para post_sleep_recover) evitando bloqueos indefinidos del hilo de programacion.
- **fix(gui):** mensajes con modo de repeticion cuya fecha base ya paso al re-programar ahora se avanzan al siguiente ciclo futuro en lugar de descartarse silenciosamente (nuevo metodo `_advance_to_next_occurrence`).
- **chore:** se agregan comentarios explicativos en todas las funciones nuevas y modificadas.

## [v8.0.3] - 2026-03-18

- se convierten a absolutas las rutas de build para `VERSION`, `enviar_whatsapp.ico` y `enviar_whatsapp.py`, dejando estable el release automatico en GitHub Actions

## [v8.0.2] - 2026-03-18

- se corrige la ruta del archivo `VERSION` en el build de PyInstaller para que el release automatico de GitHub Actions funcione en `main`

## [v8.0.1] - 2026-03-18

- se publica el proyecto en GitHub por primera vez
- se centraliza el versionado en el archivo `VERSION`
- se agrega build reproducible de `enviar_whatsapp.exe` con version incrustada
- se documenta el proyecto y se agrega configuracion segura de ejemplo
- se automatiza el release de GitHub para cada push a `main`
