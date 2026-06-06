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

| Categoría | Selector actual |
|-----------|----------------|
| Search box | `[aria-label="Search input textbox"]` |
| Chat list item | `[data-testid='cell-frame-container']` |
| Header title | `#main header span[title]` |
| Composer | `footer div[contenteditable='true']` |
| Send button | `button[data-testid='send']` |
| New chat | `button[data-testid='chat-list-new-chat']` |

## Notas
- Ejecutar después de cada actualización de WhatsApp Web detectada
- Si el bot falla silenciosamente, este diagnóstico es el primer paso
- Los selectores JS en `_click_contact_js` y `_get_header_name` también deben verificarse
