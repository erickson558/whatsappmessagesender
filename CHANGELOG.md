# Changelog

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
