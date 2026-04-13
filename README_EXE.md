# Compilar y usar el `.exe`

## 1) Compilar

En PowerShell, dentro de esta carpeta:

```powershell
.\build_exe.ps1
```

El ejecutable queda en:

- `dist\enviar_whatsapp.exe`

## 2) Llevarlo a otra PC

Copiar estos archivos:

- `dist\enviar_whatsapp.exe`
- `config.json` (opcional; si no existe, la app crea uno nuevo)

## 3) Requisitos en la PC destino

- Windows 10/11
- Python no es necesario para ejecutar el `.exe`
- Debe existir al menos un navegador Chromium instalado (Opera, Brave, Chrome o Edge)
- Si la ruta del navegador cambia, se configura desde la app con `Ruta navegador`

## 4) Comportamiento clave

- Antes de enviar mensajes, la app intenta encontrar primero una pestaña ya abierta de `web.whatsapp.com` en el navegador seleccionado.
- Si no existe, abre una pestaña nueva de WhatsApp Web en ese navegador.

