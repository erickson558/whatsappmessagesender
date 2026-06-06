# Annotate Code — WhatsApp Message Sender

Agrega docstrings y comentarios inline a los módulos Python del proyecto.
El objetivo es que cualquier desarrollador pueda entender qué hace cada función
y POR QUÉ, sin necesidad de leer código externo ni el historial de git.

## Argumento opcional
Nombre del módulo a anotar (default: todos los módulos principales).
Ej: `backend/browser_worker.py` o `all` (default)

## Alcance por módulo

| Módulo | Qué anotar |
|--------|-----------|
| `backend/browser_worker.py` | Cada método público + bloques no obvios (JS eval, XPath, recuperación CDP) |
| `backend/whatsapp_backend.py` | Métodos de fachada, locks, flujos de reintento |
| `backend/config_store.py` | Merge strategy, migración de esquema, backup |
| `frontend/gui.py` | Scheduling loop, watchdog hibernación, tema |
| `backend/logging_service.py` | Configuración de handlers y rotación |

## Reglas de anotación

1. **Docstrings**: Formato triple-quote. Primera línea: qué hace (≤80 chars).
   Párrafo adicional solo si el comportamiento tiene restricciones o invariantes no obvios.
2. **Comentarios inline**: Solo cuando el WHY no es obvio del código.
   Preferir `# POR QUÉ:` sobre `# QUÉ:`. Máx 1 línea.
3. **Bloques JS**: Comentar qué DOM busca y por qué esa estrategia.
4. **NO comentar**: getters/setters triviales, código auto-descriptivo, imports.
5. **Idioma**: Español (coherente con el resto del proyecto).

## Pasos

1. Leer módulo objetivo completo
2. Identificar métodos sin docstring o con lógica compleja sin comentar
3. Agregar docstrings y comentarios respetando las reglas anteriores
4. Verificar sintaxis: `python -c "import ast; ast.parse(open('ruta').read())"`
5. Reportar: cuántos métodos documentados, cuántos comentarios agregados

## Flujo Post-Anotación
1. /bump-version patch — incrementar versión
2. /build-exe — compilar con cambios
3. /github-push — subir a GitHub

## Notas
- No refactorizar código al anotar; solo agregar texto explicativo
- No agregar type hints si no existen (scope creep)
- Preservar comentarios FIX/ADR existentes que documentan decisiones
