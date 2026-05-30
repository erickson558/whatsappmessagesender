# Bump Version -- WhatsApp Message Sender

Incrementa la version del proyecto (Semantic Versioning).

Argumento: $ARGUMENTS -- "major", "minor", o "patch" (default: patch)

## Pasos

1. Leer version actual:
   Get-Content VERSION

2. Determinar tipo desde $ARGUMENTS:
   - major: cambios incompatibles (X.0.0)
   - minor: nueva funcionalidad compatible (x.Y.0)
   - patch: correcciones de bugs (x.y.Z)
   - Sin argumento -> usar patch

3. Ejecutar script de bump:
   python scripts/bump_version.py {tipo}

4. Leer nueva version:
   Get-Content VERSION

5. Actualizar CHANGELOG.md con entrada para la nueva version:
   ## [X.Y.Z] -- YYYY-MM-DD
   ### Changed / Fixed / Added
   - Descripcion de los cambios

6. Reportar: version anterior -> nueva version

## Flujo Post-Bump
1. /build-exe -- compilar nueva version
2. /github-push -- subir cambios
3. /github-release -- crear release oficial

## Convencion de Versionado
- MAJOR: cambios arquitecturales o incompatibilidades
- MINOR: nuevas features, mejoras significativas de UI
- PATCH: bug fixes, mejoras menores, optimizaciones
