# Changelog

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
