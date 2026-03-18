# WhatsApp Message Sender

Aplicacion de escritorio en Python para programar y enviar mensajes por WhatsApp Web desde Windows, usando un navegador Chromium existente y una interfaz grafica construida con Tkinter.

## Que hace el programa

- Programa mensajes individuales o repetitivos en hasta 4 grupos de trabajo.
- Reutiliza una pestana existente de `web.whatsapp.com` cuando esta disponible.
- Permite trabajar con Opera, Brave, Chrome y Edge.
- Guarda la configuracion local del usuario para reutilizar horarios, mensajes y rutas del navegador.
- Genera un ejecutable `.exe` para distribucion en Windows.

## Tecnologias y dependencias

- Python 3.12
- Tkinter
- `playwright`
- `requests`
- `tkcalendar`
- `pyinstaller`

Dependencias instalables:

```powershell
python -m pip install -r requirements.txt
```

## Estructura relevante

- `enviar_whatsapp.py`: punto de entrada de la aplicacion.
- `frontend/gui.py`: interfaz grafica y logica de programacion.
- `backend/browser_worker.py`: control del navegador y comunicacion con WhatsApp Web.
- `backend/whatsapp_backend.py`: fachada de operaciones de envio.
- `backend/config_store.py`: persistencia de configuracion local.
- `VERSION`: fuente unica de verdad para la version actual.
- `build_exe.ps1`: compilacion local del `.exe`.
- `.github/workflows/release.yml`: build y release automatico en GitHub Actions.

## Configuracion local

No subas tu `config.json` real porque puede contener contactos, mensajes y rutas privadas.

Para iniciar desde cero:

```powershell
Copy-Item config.example.json config.json
```

Si `config.json` no existe, la app genera uno automaticamente con valores por defecto.

## Ejecucion local

```powershell
python enviar_whatsapp.py
```

## Compilar el ejecutable

El script compila `enviar_whatsapp.exe` en la misma carpeta donde vive `enviar_whatsapp.py` y reutiliza el icono `enviar_whatsapp.ico`.

```powershell
.\build_exe.ps1
```

Salida esperada:

- `.\enviar_whatsapp.exe`

## Versionado

Se usa versionado semantico con formato `vX.Y.Z`.

- `X`: cambios incompatibles.
- `Y`: funcionalidades nuevas compatibles.
- `Z`: correcciones, ajustes menores y cambios de publicacion.

La fuente principal para GitHub es el archivo `VERSION`.

Antes de cada commit debes incrementar la version:

```powershell
python .\scripts\bump_version.py patch
```

Tambien puedes usar:

```powershell
python .\scripts\bump_version.py minor
python .\scripts\bump_version.py major
python .\scripts\bump_version.py --set 8.1.0
```

Ese script sincroniza:

- `VERSION`
- `config.example.json`
- `config.json` si existe localmente

Con eso mantienes alineada la version que ve la app, la del release en GitHub y la documentacion del proyecto.

## Release automatico en GitHub

Cada `push` a `main` ejecuta el workflow `release.yml`:

- valida la version actual del archivo `VERSION`
- compila `enviar_whatsapp.exe` en Windows
- crea un release con tag `vX.Y.Z`
- adjunta el `.exe` y su hash SHA-256

Si haces push sin cambiar `VERSION`, el workflow falla para obligar a mantener una version nueva por commit en `main`.

## Flujo manual recomendado

```powershell
python .\scripts\bump_version.py patch
git add VERSION
git add .gitignore .github\workflows\release.yml LICENSE README.md config.example.json build_exe.ps1 enviar_whatsapp.py frontend backend scripts requirements.txt
git commit -m "chore: release vX.Y.Z"
git push origin main
```

## Licencia

Este proyecto se distribuye bajo [Apache License 2.0](LICENSE).
