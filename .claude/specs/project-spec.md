# Especificacion del Proyecto: WhatsApp Message Sender

> Documento vivo de Spec-Driven Development. Actualizar con cada cambio de version mayor o menor.
> Version del documento alineada con: `VERSION` — **v8.9.13**

---

## 1. Vision General

**WhatsApp Message Sender** es una aplicacion de escritorio para Windows que permite a usuarios no tecnicos programar y enviar mensajes de WhatsApp de forma automatica, reutilizando una sesion de navegador Chromium ya autenticada en `web.whatsapp.com`. No requiere API oficial de WhatsApp ni numero de telefono adicional.

### Propuesta de valor

- Programacion de mensajes individuales y repetitivos sin depender de servicios en la nube.
- Cero friccion de autenticacion: usa la sesion existente del usuario en su navegador habitual.
- Distribucion como `.exe` unico sin necesidad de instalar Python.
- Gratuita, de codigo abierto y autocontenida.

### Usuarios objetivo

Usuarios individuales o de pequenas empresas en Windows que necesitan automatizar recordatorios, avisos o comunicaciones periodicas por WhatsApp sin herramientas empresariales.

---

## 2. Estado Actual

| Campo | Valor |
|---|---|
| Version | **v8.9.13** |
| Rama principal | `main` |
| Plataforma soportada | Windows 10 / 11 (x64) |
| Python requerido (dev) | 3.12 |
| Distribucion | `enviar_whatsapp.exe` (PyInstaller, single-file) |
| Release CI | GitHub Actions — `release.yml` (push a `main`) |
| Licencia | Apache License 2.0 |

### Modulos principales

| Archivo | Responsabilidad |
|---|---|
| `enviar_whatsapp.py` | Punto de entrada |
| `frontend/gui.py` | Interfaz grafica (Tkinter), logica de programacion y watchdog de hibernacion |
| `backend/browser_worker.py` | Control del navegador via CDP/Playwright, keepalive, recuperacion post-hibernacion |
| `backend/whatsapp_backend.py` | Fachada de operaciones: seleccion de contacto, envio, lock de entrega |
| `backend/config_store.py` | Persistencia de configuracion en `config.json` con proteccion ante corrupcion |
| `scripts/bump_version.py` | Sincronizacion de version entre `VERSION`, `config.example.json` y `config.json` |
| `build_exe.ps1` | Compilacion local del ejecutable |

### Capacidades actuales (v8.9.13)

- Hasta **4 grupos de trabajo** con hasta **4 mensajes cada uno** (16 mensajes configurables en total).
- Modos de repeticion por mensaje: Ninguno, Cada minuto, Cada hora, Diariamente, Semanalmente (dias seleccionables) y Mensualmente.
- Navegadores soportados: Opera, Brave, Chrome y Edge.
- Reconexion automatica al browser tras cierre, QR expirado o hibernacion del sistema.
- Watchdog de hibernacion (`SleepWatchdog`) que reconecta el browser y reprograma mensajes vencidos al despertar.
- Lock de entrega (`_delivery_lock`) que serializa `select_contact + send_message`.
- Confirmacion estricta del destinatario antes de escribir: el worker solo envia si puede verificar el contacto objetivo y ve el compositor listo.
- Splash screen con barra de progreso real durante el arranque.
- Idiomas disponibles: espanol, ingles y portugues.
- Tema claro/oscuro persistente, auto-label opcional por mensaje y mejoras de usabilidad en campos largos (scroll propio, auto-scroll al focus).
- Boton de donacion visible en la UI y en el menu contextual.
- Logs rotativos con rutas absolutas, tolerantes al path de lanzamiento del `.exe`.
- **[V8.5.0]** Keepalive detecta QR/sesion-expirada ademas de desconexion CDP.
- **[V8.5.0]** Mensajes repetitivos no se abandonan permanentemente al agotar retries: se reprograman con cooldown de 5 min.
- **[V8.6.x–V8.7.x]** Reescritura progresiva de la seleccion de contacto para WA Web 2025/2026: estrategia teclado-first, localizacion JS de coordenadas reales, filtros de spans secundarios y fallbacks de header/compose.
- **[V8.8.0]** Overhaul visual de la GUI: correcciones de cursor/foco, tipografia consistente y bordes tematizados.
- **[V8.9.4–V8.9.8]** Mejoras de ergonomia en el editor: rueda del mouse, scroll automatico al focus, scrollbars dedicadas y refinamiento del modo oscuro.
- **[V8.9.10]** Deteccion y descarte del panel de busqueda activo para que no intercepte el envio.
- **[V8.9.12]** Verificacion de envio acelerada para WA Web 2026 via compositor vacio y selectores actualizados de mensajes salientes.
- **[V8.9.13]** Endurecimiento del flujo de target-chat: `compose visible` ya no se acepta como evidencia suficiente del destinatario correcto; se agregan pruebas unitarias de regresion para cruce de contactos.

---

## 3. Stack Tecnologico

### Runtime y GUI

| Componente | Version / Restriccion | Rol |
|---|---|---|
| Python | 3.12 | Runtime de desarrollo |
| Tkinter | stdlib | Interfaz grafica de escritorio |
| tkcalendar | `>=1.6.1,<2` | Widget de seleccion de fecha |

### Automatizacion de navegador

| Componente | Version / Restriccion | Rol |
|---|---|---|
| Playwright (Python) | `==1.51.0` | Control del navegador via CDP |
| Chromium existente | Opera / Brave / Chrome / Edge | Sesion de WhatsApp Web del usuario |

### Distribucion y CI

| Componente | Version / Restriccion | Rol |
|---|---|---|
| PyInstaller | `>=6.11.1,<7` | Empaquetado en `.exe` single-file |
| GitHub Actions | — | Build y release automatico |
| requests | `>=2.31.0,<3` | HTTP utilitario (actualizaciones, diagnostico) |

### Persistencia

- `config.json` (local, excluido de git): configuracion de usuario, contactos, horarios y rutas.
- `config.example.json`: plantilla versionada y segura para nuevos usuarios.
- `VERSION`: fuente unica de verdad para el numero de version.

---

## 4. Requisitos No Funcionales

### Performance

- El ciclo de keepalive del browser worker debe ejecutarse cada `keepalive_interval_sec` (defecto: 60 s) sin bloquear el hilo principal de la GUI.
- La deteccion de retorno de hibernacion debe completarse en menos de 15 segundos desde que el sistema responde.
- El envio de cada mensaje (select_contact + send_message) no debe exceder 120 segundos de timeout; la seleccion de contacto no debe exceder 60 segundos.
- El arranque de la aplicacion (desde `.exe`) debe mostrar la ventana principal en menos de 5 segundos en hardware convencional.

### Seguridad

- `config.json` nunca debe subirse al repositorio (`.gitignore`). Puede contener contactos, mensajes y rutas privadas.
- La aplicacion no transmite credenciales: usa la sesion CDP del navegador del usuario sin interceptar tokens ni cookies.
- No se almacenan mensajes en servicios externos; todo queda local.
- El hash SHA-256 del `.exe` se publica junto con cada release para verificacion de integridad.

### Confiabilidad

- Un `config.json` corrupto no debe crashear la app: se genera backup `.bak` y se reinicia con valores por defecto.
- Ante desconexion del browser, la app debe intentar reconexion automatica (`relaunch_on_disconnect: true`).
- El `_delivery_lock` garantiza que dos hilos no ejecuten `select_contact`+`send_message` de forma concurrente.
- El browser worker no debe enviar un mensaje si no logra confirmar que el chat activo corresponde al contacto objetivo.
- Mensajes repetitivos cuya fecha quedo en el pasado por hibernacion se reprograman automaticamente al proximo ciclo futuro.
- Los logs utilizan rutas absolutas para funcionar correctamente independientemente del directorio de lanzamiento del `.exe`.

### Experiencia de Usuario (UX)

- La interfaz debe ser operable sin conocimientos tecnicos: etiquetas claras, flujo lineal.
- El splash screen debe reflejar el progreso real de carga (no ser decorativo).
- Los errores de configuracion deben mostrarse en lenguaje natural, sin stack traces visibles al usuario.
- La ventana debe recordar su geometria y posicion entre sesiones.
- El soporte multi-idioma debe permitir cambiar el idioma sin reiniciar la aplicacion (objetivo futuro; actualmente requiere reinicio).

---

## 5. Limites del Sistema

| Limite | Valor actual | Razon |
|---|---|---|
| Grupos de trabajo | 4 | Diseno de UI fijo; ampliable con refactor de GUI |
| Mensajes por grupo | 4 | Idem |
| Navegadores soportados | 4 (Opera, Brave, Chrome, Edge) | Probados con CDP; otros pueden funcionar pero no estan garantizados |
| Plataforma | Solo Windows | PyInstaller + rutas de browser hardcodeadas para Windows; sin soporte Linux/macOS |
| Puerto CDP | 9222 (configurable) | Un unico puerto por instancia; no soporta multiples perfiles simultaneos |
| Sesiones simultaneas | 1 browser, 1 cuenta WhatsApp | Arquitectura single-worker |
| Envios concurrentes | Serializados por `_delivery_lock` | No hay paralelismo intencionado en envios |
| Formato de mensaje | Solo texto plano | Sin adjuntos, imagenes, stickers ni mensajes de voz por ahora |

---

## 6. Features Pendientes

Las siguientes funcionalidades estan identificadas para versiones futuras. Ninguna tiene fecha comprometida.

### 6.1 Cambio de Idioma Sin Reinicio

**Descripcion:** Permitir que el selector de idioma aplique todos los textos de la interfaz sin requerir reiniciar la aplicacion.

**Estado actual:** el idioma se persiste en `config.json`, pero el usuario debe reiniciar para ver la UI completa en el nuevo idioma.

**Criterios de aceptacion:**

- El cambio de idioma desde la GUI recarga labels, botones, tabs, mensajes de estado y menu contextual sin reiniciar.
- Si falta una clave para el idioma activo, se usa espanol como fallback sin crashear.
- El cambio no rompe timers, hilos en ejecucion ni bindings de la ventana.
- El idioma seleccionado sigue persistido en `config.json`.

---

### 6.2 Soporte Multi-Idiomas Expandido

**Descripcion:** Consolidar el sistema de internacionalizacion actual para que todos los catalogos sean mas faciles de mantener y extender.

**Idiomas objetivo (prioridad):**

1. Espanol (es) — idioma base
2. Ingles (en)
3. Portugues (pt)

**Criterios de aceptacion:**

- El 100 % de los textos visibles al usuario siguen centralizados y auditables desde un unico modulo/catálogo.
- La incorporacion de un nuevo idioma no requiere tocar la logica de negocio del scheduler ni del browser worker.
- Los mensajes de log dirigidos a usuario y las etiquetas del splash quedan alineados con el idioma activo.
- Los archivos de traduccion son editables por colaboradores sin conocimiento de Python.
- El `.exe` incluye todos los archivos de traduccion empaquetados correctamente por PyInstaller.

**Notas de implementacion:**

- Evaluar uso de `gettext` (stdlib) o un esquema propio basado en diccionarios JSON por idioma.
- El modulo de i18n debe ser independiente de Tkinter para facilitar pruebas unitarias.
- Priorizar completitud del idioma espanol antes de agregar idiomas nuevos.

---

### 6.3 Otras Mejoras Identificadas (backlog)

| Feature | Descripcion breve |
|---|---|
| Adjuntos en mensajes | Soporte para enviar imagenes o archivos junto con el texto |
| Mas mensajes por grupo | Permitir configurar mas de 4 mensajes por grupo via scroll o paginacion |
| Mas de 4 grupos | Ampliar a N grupos con tabs dinamicos |
| Exportar/importar config | Exportar configuracion como `.json` e importarla en otra maquina |
| Notificaciones nativas | Mostrar notificacion de Windows al enviar cada mensaje |
| Modo bandeja (tray) | Minimizar a la bandeja del sistema en lugar de cerrar |
| Soporte macOS/Linux | Refactorizacion de rutas y empaquetado multiplataforma |

---

## 7. Fuera de Alcance

Las siguientes funcionalidades quedan **explicitamente excluidas** del proyecto en su estado actual y no deben implementarse sin una revision de arquitectura previa:

| Fuera de alcance | Justificacion |
|---|---|
| API oficial de WhatsApp Business | Requiere registro, aprobacion de Meta y costo; contradice la propuesta de valor de cero dependencias externas |
| Envio a multiples contactos simultaneos | La arquitectura single-worker y el `_delivery_lock` no estan disenados para paralelismo; riesgo de baneos por WhatsApp |
| Servidor o backend remoto | El proyecto es deliberadamente local y offline; agregar un servidor cambiaria el modelo de seguridad y privacidad |
| Almacenamiento de mensajes en la nube | Idem; los datos del usuario permanecen en su maquina |
| Soporte para WhatsApp Business App (distinto de Web) | CDP no funciona con la app de escritorio nativa de WhatsApp |
| Bot conversacional / respuestas automaticas | Fuera del alcance de un programador de mensajes salientes |
| Soporte para multiples cuentas de WhatsApp simultaneas | Requeriria multiples instancias de browser worker y una UI completamente distinta |
| Interfaz web o movil | El proyecto es una aplicacion de escritorio Windows; una interfaz web implicaria un servidor |
| Integraciones con CRM o herramientas de terceros | Agrega complejidad y dependencias externas fuera del caso de uso objetivo |
