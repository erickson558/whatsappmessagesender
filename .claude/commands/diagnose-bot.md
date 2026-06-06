# Skill: /diagnose-bot — Diagnóstico y Reparación de Conexión WhatsApp

## Cuando usar esta skill
- La app dejó de enviar mensajes sin razón aparente
- Necesitas verificar si el browser worker está activo y conectado a WhatsApp
- Quieres revisar si hay mensajes repetitivos que se perdieron (retries agotados)
- Sospechas un problema de QR, sesión expirada o browser zombie
- Antes de compilar un release para asegurarte que el core funciona

---

## Lo que hace esta skill

1. **Diagnóstico de código** — Revisa los archivos clave del proyecto en busca de síntomas:
   - `browser_worker.py` → estado del keepalive, recovery, search-box clearing
   - `whatsapp_backend.py` → timeouts, lock de entrega
   - `gui.py` → lógica de retry, watchdog, reprogram

2. **Análisis de problemas conocidos** — Compara el estado actual del código contra los 4 problemas raíz documentados en V8.5.0:
   - Keepalive ciego (¿detecta QR/desconexión?)
   - Max retries abandona mensajes (¿reprograma en lugar de abandonar?)
   - Search box no limpia correctamente (¿tiene Escape + triple_click?)
   - Playwright stale (¿valida la instancia antes de reusar?)

3. **Revisión de logs** — Si hay un archivo `debug.log` en el directorio raíz, lo escanea buscando errores recientes: `[KEEPALIVE]`, `[SLEEP]`, `[RECOVER]`, `[RETRY]`, `status_exhausted`.

4. **Reporte de salud** — Produce un resumen con:
   - ✅ / ❌ por cada check
   - Versión detectada vs. última conocida con los fixes
   - Recomendación: si está en V<8.5.0 → ejecutar `/bump-version patch` + `/build-exe`

---

## Instrucciones para el agente

Lee los archivos del proyecto como se indica y produce un reporte estructurado.

### Archivos a revisar

1. `VERSION` — ¿Es ≥ 8.5.0?
2. `backend/browser_worker.py`:
   - ¿`_maybe_keepalive` llama `_looks_like_login_required()`?  (FIX V8.5.0)
   - ¿`_focus_global_search` presiona Escape antes de hacer click?  (FIX V8.5.0)
   - ¿`_clear_global_search` verifica `_is_compose_visible()` ANTES de presionar Escape?  (FIX V8.7.4 — Escape cierra chat en WA Web 2026)
   - ¿`_send_message` llama `_clear_global_search()` DESPUES del envio, no antes?  (FIX V8.7.4 — antes cerraba el chat)
   - ¿`_select_contact` usa ArrowDown+Enter como estrategia primaria (sin blur previo al mouse.click)?  (FIX V8.7.3)
   - ¿`_ensure_chat_target` acepta `_is_compose_visible()` como confirmacion de chat abierto?  (FIX V8.7.4)
   - ¿`_connect_over_cdp` valida la instancia playwright con health-check?  (FIX V8.5.0)
3. `frontend/gui.py`:
   - ¿`_retry_message_delivery` verifica `has_repeating_items` y reprograma en lugar de abandonar?  (FIX V8.5.0)
4. `debug.log` (si existe) — buscar últimas 50 líneas con errores de keepalive, retry exhausted, o disconnected.

### Formato del reporte

```
## Reporte de Salud — WhatsApp Message Sender

**Versión:** X.Y.Z  [✅ ≥8.5.0 | ⚠️ <8.5.0 — aplicar fixes V8.5.0]

### Checks de código
| # | Check | Estado |
|---|-------|--------|
| 1 | Keepalive detecta QR/desconexión | ✅ / ❌ |
| 2 | Search box: Escape antes de enfocar | ✅ / ❌ |
| 3 | Search box: clear verifica compose antes de Escape (V8.7.4) | ✅ / ❌ |
| 4 | Playwright stale: health-check antes de reusar | ✅ / ❌ |
| 5 | Max retries: reprogram en lugar de abandonar | ✅ / ❌ |

### Errores recientes en logs
[Extracto de debug.log o "Sin log disponible"]

### Recomendación
[Acción sugerida con skill a ejecutar]
```

### Acción correctiva si se detectan problemas

Si algún check falla **y la versión es < 8.5.0**, describe exactamente qué cambiar y sugiere al usuario ejecutar los skills en orden:

```
/bump-version minor    # → V8.5.0
/build-exe             # Compilar .exe actualizado
/github-push           # Push al repo
/github-release        # Crear release oficial
```

Si la versión **ya es ≥ 8.5.0** pero los checks fallan, indica los archivos y líneas específicas a corregir.
