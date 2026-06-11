# Changelog

## [v8.9.9] — 2026-06-11
### Fixed
- **Selección de contacto — overlay WA Web 2026:** en versiones recientes de WhatsApp Web 2026, el panel de búsqueda puede permanecer activo como overlay sobre el chat recién abierto, ocultando el compositor y haciendo que `_is_compose_visible()` devuelva False aunque el chat ya estuviera abierto. Se agrega un paso `Escape` post-Strategy1 en `_select_contact` para descartar el overlay y re-verificar compose/header antes de continuar con estrategias más invasivas. Si no había chat abierto, Escape cierra el panel y Strategy 2 opera directamente sobre la lista de chats recientes.
- **`_wait_header` — detección 1-pass:** cambiada la lógica de 2 checks consecutivos de compose a 1 solo check (`compose_seen` removido). La lógica de 2-pass era demasiado estricta en WA Web 2026 donde el compositor puede quedar brevemente oculto entre ciclos de 140 ms, causando falsos negativos.

## [v8.9.8] — 2026-06-10
### Fixed
- **Scrollbar en campo de mensaje:** cada `tk.Text` de mensaje ahora tiene su propia scrollbar vertical. El campo se envuelve en un Frame contenedor (`_is_section=True`) con la scrollbar a la derecha; el borde visible es del Frame, no del Text.
- **Mouse wheel en campo de mensaje:** el handler `_on_mousewheel` del canvas ahora verifica `isinstance(event.widget, tk.Text)` y retorna sin hacer scroll del canvas, dejando que el widget Text maneje su propio scroll con la rueda del mouse.
- **Theming de Scrollbar en modo oscuro:** `_theme_children` ahora incluye el caso `Scrollbar` aplicando `bg`, `troughcolor` y `activebackground` del tema activo.

## [v8.9.7] — 2026-06-10
### Fixed
- **Campo de mensaje más grande:** aumentado `height=2` → `height=4` en los `tk.Text` de mensaje para mejor usabilidad y espacio de escritura.
- **Scroll automático al hacer focus:** al hacer clic en el campo de mensaje, el canvas principal ahora se desplaza automáticamente para mostrar el widget en pantalla. Se agregó binding `<FocusIn>` que calcula la posición del widget en el canvas y ejecuta `yview_moveto` cuando está fuera del área visible.

## [v8.9.6] — 2026-06-10
### Fixed
- **LabelFrame títulos con fondo incorrecto:** en Windows, el área de texto del título de `tk.LabelFrame` ignora el `bg` configurado y usa colores del sistema (blanco/gris), rompiendo el tema oscuro. Solución: los dos LabelFrame de "Programación" y "Repetición" fueron reemplazados por `tk.Frame` + `tk.Label` de título propio, que `_theme_children` puede controlar completamente. El borde visible se mantiene via `highlightthickness=1` con color `border` del tema activo.

## [v8.9.5] — 2026-06-10
### Fixed
- **Grises eliminados del modo oscuro:** raíz del problema eran los colores del sistema (gris de Windows) que se filtraban en: (a) bordes `relief=GROOVE` de tarjetas y LabelFrames, (b) botones de flechas de `Spinbox`/`Combobox` con `background=bg_top` (azul), (c) paleta oscura con colores muy similares entre sí.

### Improved
- **Paleta oscura — GitHub Dark Dimmed:** tres niveles claramente distintos: `bg_main #22272E` (ventana) / `bg_panel #2D333B` (tarjetas) / `bg_card #373E47` (campos). Texto `#ADBAC7` con contraste adecuado.
- **Bordes de tarjetas:** cambiado de `relief=GROOVE` (usa grises del sistema) a `relief=FLAT` + `highlightthickness=1` con color `border` del tema activo.
- **Spinbox y Combobox:** `background=bg_card` en lugar de `bg_top` para que los botones de flecha/dropdown tengan el mismo color oscuro que el campo de texto. Añadidos `lightcolor`, `darkcolor`, `bordercolor` para eliminar el borde gris del sistema.
- **LabelFrame:** añadido `highlightthickness=1` + `highlightbackground=border` para borde coloreado coherente con el tema.

## [v8.9.4] — 2026-06-10
### Fixed
- **Scroll con rueda del mouse:** el canvas central ahora responde a la rueda del mouse para desplazarse verticalmente y ver los mensajes inferiores. El scroll se activa solo cuando el cursor está sobre el área de mensajes para no interferir con otros controles.

### Improved
- **Tema oscuro con 3 niveles de contraste:** rediseño completo de la paleta oscura inspirado en GitHub Dark. Tres capas claramente diferenciadas: `bg_main` `#0D1117` (fondo de ventana), `bg_panel` `#161B22` (fondo de tarjetas), `bg_card` `#21262D` (campos de entrada). El texto usa `#E6EDF3` para máxima legibilidad.
- **Cards como área propia:** `_theme_children` ahora propaga `area="card"` al entrar en una tarjeta de mensaje (`_is_card=True`), garantizando que Labels, Checkbuttons y sub-frames internos usen el color de fondo correcto de la tarjeta en lugar del fondo principal.

## [v8.9.3] — 2026-06-10
### Improved
- **Selectores de hora rediseñados:** los tres `tk.Listbox` (hora, minuto, AM/PM) con scrollbar interna fueron reemplazados por `ttk.Spinbox` compactos. El selector de hora ahora ocupa una sola línea, es más claro y no muestra ítems apilados con scroll.
- **Colores tema oscuro mejorados:** `bg_main` → `#111827`, `bg_card` → `#1E2D3D`, `bg_top` → `#1A3A5C` para mayor contraste y legibilidad en modo oscuro.
- **LabelFrame con borde visible:** en modo oscuro los `LabelFrame` de Programación y Repetición ahora muestran borde `GROOVE` visible y título con color de texto del tema.
- **Altura de campo de mensaje reducida:** `height=3` → `height=2` en los `tk.Text` de mensaje para mayor densidad visual.
- **Spinbox con tema dinámico:** estilo `TSpinbox` aplicado via `ttk.Style` para que los nuevos Spinbox respeten los colores de fondo, texto y flechas del tema activo (claro/oscuro).

## [v8.9.2] — 2026-06-10
### Fixed
- **Canvas frame no llenaba el ancho completo:** el `main_frame` dentro del `tk.Canvas` central no se redimensionaba al ancho de la ventana, dejando la mitad derecha del área de tarjetas con fondo vacío (canvas background). Fix: se captura el ID retornado por `canvas.create_window()` y se vincula `<Configure>` en el canvas para llamar `itemconfig(width=event.width)`, forzando que el frame interno siempre ocupe todo el ancho disponible y el grid de dos columnas se expanda correctamente.

## [v8.8.1] — 2026-06-10
### Added
- **Checkbox "Agregar [Mensaje Programado Automáticamente]":** cada bloque de mensaje tiene un nuevo checkbox que, al estar marcado, antepone automáticamente el texto `[Mensaje Programado Automáticamente]` al inicio del mensaje enviado. Permite que el destinatario sepa que el mensaje fue generado automáticamente. La preferencia se guarda en `config.json` por mensaje (`auto_label`).

## [v8.8.0] — 2026-06-10
### Improved
- **Cursor invisible en campos de texto:** bug en `_theme_children()` aplicaba colores de fondo del área de log (`bg_log`/`text_log`) a todos los widgets `tk.Text`, incluyendo los campos de mensaje. Esto causaba fondo oscuro sin `insertbackground`, haciendo el cursor invisible en modo oscuro y claro. Fix: los campos de mensaje usan `bg_card`/`text` con `insertbackground=text` explícito; el log se estiliza por separado en `_apply_theme()`.
- **Entry con cursor invisible:** `tk.Entry` de contacto creados sin `insertbackground`, `highlightthickness` ni fuente. Ahora usan `font=_F_BODY`, `insertbackground=_C_TEXT`, `relief=FLAT`, `highlightthickness=1` con color de focus verde primario.
- **`tk.Text` de mensaje:** mismos fixes + `padx/pady` para mejor legibilidad interior.
- **Checkbuttons en modo oscuro:** `_theme_children()` ahora maneja `cls == "Checkbutton"` aplicando `bg`, `fg`, `activebackground` y `selectcolor` del tema activo.
- **Labels con tipografía consistente:** todos los labels de bloque de mensaje ahora usan `_F_BODY` o `_F_SMALL` (Segoe UI). Título del bloque usa `("Segoe UI", 12, "bold")`.
- **Botones "Hoy" y "Detener repetición":** estilizados con `_C_ACCENT`/`_C_PRIMARY`, cursor `hand2`, `relief=FLAT`.
- **Días de la semana:** checkbuttons usan `font=_F_SMALL` para coherencia visual.
- **Grid de bloques de mensaje:** `frame.columnconfigure(0/1, weight=1)` para que las dos columnas se expandan proporcionalmente al redimensionar la ventana.
- **`_THEMES`:** clave `"border"` agregada a ambos temas para color de borde de widgets con `highlightthickness`.

## [v8.7.8] — 2026-06-09
### Fixed
- Splash screen congelado en 30%: `tkcalendar.DateEntry` tardaba ~1s por widget; con 16 bloques de mensaje (4 grupos × 4 mensajes) el splash quedaba bloqueado sin respuesta durante 15-120 segundos según la velocidad del sistema. Fix: se pasa callback `splash_step` a `_build_ui()` para actualizar el progreso en 30%, 38%, 46%, 54% al terminar cada grupo; y se agrega `root.update_idletasks()` dentro del bucle de `_create_message_blocks()` para que el splash permanezca visible y responsive mientras se crean los DateEntry.
- `RequestsDependencyWarning` de `requests`: `chardet 6.0.0.post1` no es reconocido por `requests 2.32.3` (solo soporta chardet 3.x/4.x). El warning era inofensivo pero confuso. Fix: suprimido en `enviar_whatsapp.py` via `warnings.filterwarnings` antes de que se importen los módulos.

## [v8.7.7] — 2026-06-09
### Fixed
- Bug crítico: `_advance_to_next_occurrence` tenía un `+1` fijo en todos los modos de repetición que causaba que al reiniciar la app con mensajes en fecha pasada, se saltara un ciclo adicional innecesario. Impacto: mensajes "Diariamente" se programaban para el día siguiente en lugar de hoy si la app arrancaba antes de la hora configurada; mensajes "Cada hora" y "Cada minuto" perdían un turno extra después de reinicios. Fix: eliminado el `+1` incondicional; ahora se calcula el mínimo de intervalos con `ceil()` y se avanza un intervalo extra solo si el resultado sigue siendo ≤ reference.
- `_report_callback_exception`: las excepciones en callbacks de Tkinter solo se imprimían a stderr (invisibles en producción). Ahora también se escriben al log de aplicación (`logaplicacion*.txt`) para facilitar diagnóstico post-crash.
- `_on_exit_requested`: al cerrar la app no quedaba registro en el log. Ahora registra `[APP] Cierre solicitado por el usuario.` para distinguir cierres normales de crashes silenciosos en logs históricos.

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
