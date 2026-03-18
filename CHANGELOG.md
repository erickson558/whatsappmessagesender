# Changelog

## [v8.0.3] - 2026-03-18

- se convierten a absolutas las rutas de build para `VERSION`, `enviar_whatsapp.ico` y `enviar_whatsapp.py`, dejando estable el release automatico en GitHub Actions

## [v8.0.2] - 2026-03-18

- se corrige la ruta del archivo `VERSION` en el build de PyInstaller para que el release automatico de GitHub Actions funcione en `main`

## [v8.0.1] - 2026-03-18

- se publica el proyecto en GitHub por primera vez
- se centraliza el versionado en el archivo `VERSION`
- se agrega build reproducible de `enviar_whatsapp.exe` con version incrustada
- se documenta el proyecto y se agrega configuracion segura de ejemplo
- se automatiza el release de GitHub para cada push a `main`
