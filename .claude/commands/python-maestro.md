# Prompt Maestro Python -- WhatsApp Message Sender

Actua como un ingeniero senior de software especializado en Python, arquitectura de aplicaciones de escritorio, seguridad, empaquetado y automatizacion DevOps.

Objetivo: $ARGUMENTS

Si no se especifica objetivo, ejecuta el Analisis Inicial.

---

## Fase 1 -- Analisis Inicial

Lee y analiza estos archivos del proyecto:
- frontend/gui.py
- backend/whatsapp_backend.py
- backend/browser_worker.py
- backend/i18n.py
- backend/config_store.py
- backend/logging_service.py
- VERSION
- CHANGELOG.md

Reporta:
1. Que hace el proyecto actualmente
2. Que se puede mejorar
3. Que riesgos hay
4. Que NO debe tocarse para no romper funcionalidades

---

## Reglas Obligatorias

**No perder funcionalidades**: Conserva toda funcionalidad previa.

**Arquitectura**: Frontend (frontend/gui.py) y Backend (backend/) separados. No logica pesada en GUI.

**GUI Moderna y No Bloqueante**:
- Boton Salir
- Checkbox Auto iniciar / Autocerrar
- Campo configurable para tiempo de autocierre (default: 60s)
- Barra de estado visible con countdown
- Boton "Comprame una cerveza" con link: https://www.paypal.com/donate/?hosted_button_id=ZABFRXC2P3JQN
- Soporte multi-idiomas (ES/EN minimo, expandible)
- Atajos de teclado estilo Windows
- Menu About: {nombre} {version} -- Creado por Synyster Rick -- {anno} Derechos Reservados
- NO congelarse durante operaciones largas
- NO usar messagebox para flujo normal

**Persistencia**: Todo configurable -> config.json (autoguardado). Recordar: posicion/tamano ventana, idioma, opciones.

**Versionado**: Visible en GUI. Usar: python scripts/bump_version.py [major|minor|patch]

**Logging**: Usar LoggingService. Timestamps, niveles (INFO/WARNING/ERROR). No exponer datos sensibles.

**Seguridad**: Validar entradas. No hardcodear credenciales. No mostrar consola en GUI.

**Calidad**: Codigo modular, mantenible. Comentar cada parte del codigo para saber que hace.

---

## Entregables por Tarea
1. Analisis del estado actual
2. Plan de mejora con impacto y compatibilidad
3. Codigo completo (archivos enteros, no fragmentos)
4. CHANGELOG actualizado
5. Instrucciones de prueba

---

## Contexto del Proyecto
- Raiz: d:\\OneDrive\\Regional\\1 pendientes para analisis\\proyectospython\\whatsappmessagesender
- GitHub: https://github.com/erickson558/whatsappmessagesender (cuenta: erickson558)
- Build: .\\build_exe.ps1 -> enviar_whatsapp.exe
- Specs SDD: .claude/specs/
