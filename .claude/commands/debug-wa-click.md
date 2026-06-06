# Debug WA Click — WhatsApp Message Sender

Diagnostica el flujo completo de selección de contacto en WA Web para identificar
por qué la automatización falla en abrir el chat o enviar el mensaje.

## Cuándo usar

- El bot escribe el nombre pero el chat no se abre
- El chat se abre brevemente pero revierte al estado de búsqueda
- El mensaje nunca se envía aunque el contacto aparece en la búsqueda
- Hay errores en los logs relacionados con `_select_contact`, `_click_contact_js` o `_wait_header`

## Argumento opcional

Nombre del contacto a diagnosticar (default: primer contacto del grupo 1 en config.json)

## Pasos de diagnóstico

### 1. Leer el estado actual del código

Leer las siguientes secciones en `backend/browser_worker.py`:
- `_type_search_variants` (cómo escribe el nombre)
- `_click_contact_js` (cómo localiza el elemento DOM)
- `_select_contact` (estrategia de click completa)
- `_is_compose_visible` (detección del composer)
- `_wait_header` (confirmación de chat abierto)
- `_is_in_chat` y `_get_active_chat_from_composer`

### 2. Identificar regresiones

Buscar en `_select_contact`:
- ¿Se llama `blur()` antes del click? (PROBLEMA: oculta resultados antes de que el click llegue)
- ¿Se usa `page.keyboard.press("Escape")`? (PROBLEMA en WA Web 2026: cierra el chat recién abierto)
- ¿Se presiona ArrowDown cuando el compose ya es visible? (PROBLEMA: navega a otro chat)
- ¿El timeout de `_wait_header` es > 5000ms sin check intermedio de compose? (PROBLEMA: demora demasiado antes de detectar éxito)

### 3. Verificar selectores WA Web

Revisar que `_click_contact_js` incluya selectores actualizados para WA Web 2026:
```javascript
// Panel lateral — al menos uno debe existir en WA Web 2026:
'#pane-side'
'[data-testid="pane-side"]'
'[aria-label="Chat list"]'
'[aria-label="Chats"]'
'[data-testid="chat-list"]'

// Contenedor clickeable — al menos uno debe existir:
role="gridcell" | role="row" | role="listitem" | role="option"
data-testid="cell-frame-container" | data-testid="conversation-item"
tabindex="0"
```

Revisar que `_is_compose_visible` incluya selectores del compositor WA Web 2026:
```
"footer div[contenteditable='true']"
"footer [data-testid='conversation-compose-box-input']"
"#main footer"
```

### 4. Verificar la secuencia de estrategias en `_select_contact`

La secuencia correcta para WA Web 2026 es:
1. **Teclado primero**: ArrowDown → Enter → check compose (1200ms) → return True si visible
2. **Mouse sin blur**: JS-locate → page.mouse.click() → check compose (1200ms) → return True si visible
3. **Guard compose**: si compose visible antes del fallback Playwright → return True
4. **Playwright fallback**: solo si compose NO es visible

### 5. Diagnóstico de timing

Si los logs muestran el sequence correcto pero el chat igual revierte, verificar:
- ¿Cuánto tiempo entre el click y la verificación de compose? (debe ser ≤1200ms)
- ¿Se intenta una estrategia de fallback MIENTRAS el chat ya está abierto?

### 6. Generar reporte

Reportar:
- Versión actual del código (grep `V8\.`)
- ¿Existe `blur()` en `_select_contact`? ✓/✗
- ¿Existe `Escape` post-click? ✓/✗
- ¿`ArrowDown` tiene guard de compose? ✓/✗
- ¿`_is_compose_visible` es la primera confirmación tras click? ✓/✗
- Selectores de panel lateral presentes: lista
- Selectores de composer presentes: lista
- Recomendación concreta de corrección si se detecta algún problema

## Fix de referencia (V8.7.3)

La corrección validada en V8.7.3 usa:
1. `page.keyboard.press("ArrowDown")` → `page.keyboard.press("Enter")` → `page.wait_for_timeout(1200)` → `_is_compose_visible()` → `return True` si visible
2. `page.mouse.click(cx, cy)` (SIN blur previo) → `page.wait_for_timeout(1200)` → `_is_compose_visible()` → `return True` si visible
3. Guard: `if self._is_compose_visible(): return True` antes de cualquier Playwright fallback

## Notas

- `_is_compose_visible()` es más fiable que `_wait_header` en WA Web 2026 porque el header puede cambiar de selector pero el composer siempre tiene `contenteditable='true'` en el footer.
- Nunca llamar `blur()` en el search input antes de un click basado en coordenadas DOM — el blur cierra el panel de resultados, haciendo que las coordenadas apunten a área vacía.
- `Escape` cierra el chat en WA Web 2026 — solo usar para limpiar el search box antes de escribir, no después de un click.
