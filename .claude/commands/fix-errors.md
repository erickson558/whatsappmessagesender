# Fix Errors — QA + Debugging + Versionado

Actúa como un ingeniero senior Python + QA + DevOps especializado en debugging, estabilidad y control de versiones.

Objetivo específico: $ARGUMENTS

Si no se especifica objetivo, ejecuta el Análisis completo del proyecto.

---

## ⚠️ REGLAS CRÍTICAS

- **NO romper funcionalidades** — el sistema ya funciona
- **NO eliminar features existentes**
- **NO hacer fixes a ciegas** — analizar primero, luego corregir
- **NO sobre-ingenierizar** — priorizar estabilidad sobre refactorización agresiva
- **Si hay duda → explicar antes de cambiar**
- **Comentar cada parte del código** para saber qué hace

---

## 🔍 FASE 1 — ANÁLISIS (OBLIGATORIA)

Lee y analiza estos archivos del proyecto WhatsApp Message Sender:
- frontend/gui.py
- backend/browser_worker.py
- backend/whatsapp_backend.py
- backend/config_store.py
- backend/logging_service.py
- backend/i18n.py
- VERSION
- CHANGELOG.md

Identifica errores o problemas potenciales:
- Bugs funcionales
- Errores de lógica
- Manejo incorrecto de excepciones
- Problemas de rendimiento
- Problemas de concurrencia (GUI congelada, race conditions, etc.)
- Importaciones incorrectas o faltantes
- Variables no inicializadas
- Recursos no liberados

Para cada problema encontrado, explica:
1. Causa raíz
2. Impacto en el usuario
3. Riesgo de corrección

---

## 🛠️ FASE 2 — CORRECCIÓN

- Corregir errores detectados
- Aplicar mejoras sin romper compatibilidad
- Mejorar: manejo de errores, validaciones, estabilidad
- Mantener código limpio, legible y comentado
- Usar el Edit tool para cambios quirúrgicos (no reescribir archivos completos)

---

## 🧪 FASE 3 — VALIDACIÓN

Antes del commit, verificar:
- Sintaxis Python: `python -c "import ast; ast.parse(open('frontend/gui.py', encoding='utf-8').read()); print('OK')"`
- Importaciones: `python -c "from frontend.gui import WhatsAppSchedulerApp; from backend.browser_worker import BrowserWorker; print('OK')"`
- Que todas las funcionalidades existentes siguen presentes

---

## 🔢 FASE 4 — VERSIONADO

Determinar nueva versión Vx.x.x:
- **patch** → fix de bugs, correcciones menores
- **minor** → mejoras de estabilidad significativas
- **major** → cambios arquitecturales grandes

Ejecutar: `python scripts/bump_version.py [major|minor|patch]`

Actualizar CHANGELOG.md con nueva entrada de versión.

---

## 📝 FASE 5 — COMMIT

Generar mensaje profesional siguiendo Conventional Commits:

Ejemplos:
- `fix: resolve race condition in delivery lock and improve exception handling (V8.x.x)`
- `fix: prevent GUI freeze during browser reconnection (V8.x.x)`

---

## 🚀 FASE 6 — PUSH Y RELEASE

Subir cambios a GitHub (cuenta erickson558, ya autenticada):

```
git add backend/... frontend/... VERSION CHANGELOG.md
git commit -m "fix: descripción del fix (Vx.x.x)"
git push origin main
git tag Vx.x.x
git push origin Vx.x.x
gh release create Vx.x.x --title "Vx.x.x" --notes "changelog"
```

---

## 📦 ENTREGABLES (en este orden)

1. **Análisis de errores** — lista de problemas, causa raíz, impacto
2. **Cambios realizados** — qué se corrigió y cómo
3. **Nueva versión** — número y justificación (patch/minor/major)
4. **Validación** — resultado de checks de sintaxis e importaciones
5. **Commit message** — mensaje profesional listo para copiar
6. **Comandos paso a paso** — git add, commit, tag, push, release

---

## ℹ️ Contexto del Proyecto
- Raíz: d:\OneDrive\Regional\1 pendientes para analisis\proyectospython\whatsappmessagesender
- GitHub: https://github.com/erickson558/whatsappmessagesender (cuenta: erickson558)
- Build: .\build_exe.ps1 → enviar_whatsapp.exe
- Stack: Python 3.12, Tkinter, Playwright, PyInstaller, Windows 11
