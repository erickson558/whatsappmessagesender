# Verify Selectors — WhatsApp Message Sender

Verifica que los selectores CSS/ARIA usados en `browser_worker.py` siguen
funcionando en la versión actual de WhatsApp Web. Los selectores son la causa
más frecuente de fallos silenciosos cuando WA Web actualiza su UI.

## Prerequisito
El bot debe estar conectado a WhatsApp Web (ejecutar la app y conectar primero).

## Pasos

1. Leer todos los selectores del archivo:
   Grep pattern: `locator\(|get_by_role\(|evaluate\(` en `backend/browser_worker.py`

2. Agrupar por categoría:
   - Búsqueda global (search box)
   - Panel de resultados / chat list
   - Header del chat activo
   - Compositor de mensajes (footer)
   - Botón de enviar
   - Botones de nueva conversación

3. Para cada selector, verificar via Playwright evaluate():
   ```python
   page.evaluate("document.querySelector('SELECTOR') !== null")
   ```

4. Clasificar resultados:
   - ✅ Funciona: selector retorna elemento
   - ⚠️  Fallback: selector principal falla pero hay alternativa funcionando
   - ❌ Roto: todos los selectores de esa categoría fallan

5. Generar reporte:
   ```
   === Reporte de Selectores WA Web ===
   Fecha: YYYY-MM-DD
   Versión WA Web: (leer del DOM si está disponible)

   [CATEGORÍA] Estado: ✅/⚠️/❌
     Funcionando: selector_que_funciona
     Roto: selector_roto
   ```

6. Si hay selectores rotos (❌):
   - Inspeccionar el DOM actual para encontrar el selector correcto
   - Proponer fix en `browser_worker.py`
   - Invocar /fix-errors si es necesario

## Selectores críticos a verificar siempre

| Categoría | Selector actual | Versión |
|-----------|----------------|---------|
| Search box | `[aria-label="Search input textbox"]` | V8.5.0+ |
| Chat list panel | `#pane-side`, `[aria-label="Chats"]`, `[data-testid="chat-list"]` | V8.7.0+ |
| Chat list item | `[data-testid='cell-frame-container']`, `role='gridcell'`, `tabindex='0'` | V8.6.1+ |
| Header title | `#main header span[title]` | V8.6.0+ |
| Composer (chat abierto) | `footer div[contenteditable='true']` | V8.7.2+ |
| Composer (por aria-label) | `footer div[aria-label^='Type']`, `footer div[aria-label^='Escribe']` | V8.7.0+ |
| Send button | `button[data-testid='send']`, `span[data-testid='send']` | V8.3.3+ |
| New chat | `button[data-testid='chat-list-new-chat']` | V8.6.0+ |

## Selectores de _is_compose_visible() — verificar siempre

`_is_compose_visible()` es el detector primario de chat abierto en V8.7.2+. Verificar que al menos uno funcione:
```
footer div[contenteditable='true']
footer [data-testid='conversation-compose-box-input']
#main footer
```

## Notas
- Ejecutar después de cada actualización de WhatsApp Web detectada
- Si el bot falla silenciosamente, este diagnóstico es el primer paso
- Los selectores JS en `_click_contact_js` (retorna coordenadas, no hace click) y `_get_header_name` también deben verificarse
- En WA Web 2026, el header puede cambiar de selector; `_is_compose_visible()` es más estable como confirmación de chat abierto
- `_clear_global_search()` verifica compose antes de presionar Escape (V8.7.4) — verificar que este guard esté presente
