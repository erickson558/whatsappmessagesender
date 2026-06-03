# Especificacion del Proyecto: WhatsApp Message Sender

> Documento vivo de Spec-Driven Development. Actualizar con cada cambio de version mayor o menor.
> Version del documento alineada con: `VERSION` — **v8.5.0**

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
| Version | **v8.5.0** |
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

### Capacidades actuales (v8.5.0)

- Hasta **4 grupos de trabajo** con hasta **4 mensajes cada uno** (16 mensajes configurables en total).
- Modos de repeticion por mensaje: Ninguno, Diario, Semanal (dias seleccionables), Mensual.
- Navegadores soportados: Opera, Brave, Chrome, Edge.
- Reconexion automatica al browser tras cierre o hibernacion del sistema.
- Watchdog de hibernacion (`SleepWatchdog`) que reprograma mensajes vencidos al despertar.
- Lock de entrega (`_delivery_lock`) que evita envios al contacto equivocado bajo concurrencia.
- Splash screen con barra de progreso en el arranque.
- Soporte multi-idioma inicial (base implementada en v8.2.0).
- Boton de donacion (v8.2.0).
- Logs rotativos con rutas absolutas, tolerantes al path de lanzamiento del `.exe`.
- **[V8.5.0]** Keepalive detecta QR/sesion-expirada ademas de desconexion CDP.
- **[V8.5.0]** Mensajes repetitivos no se abandonan permanentemente al agotar retries: se reprograman con cooldown de 5 min.
- **[V8.5.0]** Cuadro de busqueda de contacto: Escape previo + triple_click para limpieza robusta.
- **[V8.5.0]** Instancia Playwright validada antes de reusar (deteccion de instancia stale tras dias de uso).
- **[V8.5.0]** Skill `/diagnose-bot` para diagnosticar y verificar el estado de la conexion WhatsApp.

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

### 6.1 Boton "Comprame una cerveza"

**Descripcion:** Agregar un boton de donacion voluntaria con el texto "Comprame una cerveza" en la interfaz, que abra el navegador del sistema con el enlace de PayPal del autor.

**Enlace:** `https://www.paypal.com/donate/?hosted_button_id=ZABFRXC2P3JQN`

**Criterios de aceptacion:**

- El boton es visible en la ventana principal sin ocupar espacio prominente (ubicacion secundaria: pie de ventana o menu Ayuda).
- Al hacer clic abre el enlace en el navegador predeterminado del sistema (`webbrowser.open`).
- El boton respeta el idioma activo: el texto cambia segun el idioma seleccionado (p. ej. "Buy me a beer" en ingles).
- No interfiere con la logica de envio ni con el ciclo de vida del browser worker.
- El boton es visible en ambos estados de la app: browser conectado y desconectado.

**Notas de implementacion:**

- Usar `webbrowser.open(url)` de la stdlib; no abrir con el browser controlado por Playwright.
- El enlace debe estar en una constante nombrada en el modulo de configuracion o en un archivo de constantes dedicado.

---

### 6.2 Soporte Multi-Idiomas Expandido

**Descripcion:** Expandir el sistema de internacionalizacion (i18n) introducido en v8.2.0 para cubrir todos los textos de la interfaz y soportar idiomas adicionales.

**Idiomas objetivo (prioridad):**

1. Espanol (es) — idioma base, ya parcialmente implementado
2. Ingles (en) — segunda prioridad
3. Portugues (pt) — tercera prioridad

**Criterios de aceptacion:**

- El 100 % de los textos visibles al usuario (etiquetas, botones, mensajes de error, logs en GUI, splash) estan externalizados en archivos de traduccion (`.json` o `.po`/`.mo`).
- El cambio de idioma desde la GUI recarga los textos sin necesidad de reiniciar la aplicacion.
- Si falta una clave de traduccion para el idioma activo, se usa el texto en espanol como fallback sin crashear.
- La seleccion de idioma se persiste en `config.json`.
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
