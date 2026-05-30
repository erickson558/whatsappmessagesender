# Build EXE -- WhatsApp Message Sender

Compila la aplicacion a ejecutable Windows (.exe).

## Pasos

1. Leer version actual:
   Get-Content VERSION

2. Generar version info para Windows:
   python scripts/build_windows_version_file.py

3. Compilar con PyInstaller:
   .\\build_exe.ps1

4. Verificar resultado:
   Test-Path ".\\enviar_whatsapp.exe"
   Reportar tamano en MB si existe

5. Calcular SHA256 para el release:
   Get-FileHash ".\\enviar_whatsapp.exe" -Algorithm SHA256

6. Reportar: ruta, tamano, hash SHA256, version compilada

## Requisitos
- Python 3.12 instalado
- PyInstaller 6.11.1+ (ver requirements.txt)
- Icono: enviar_whatsapp.ico en la raiz
- Playwright chromium descargado

## Configuracion
- Output: enviar_whatsapp.exe en raiz del proyecto
- Modo: windowed (sin consola adicional)
- Icono: enviar_whatsapp.ico
