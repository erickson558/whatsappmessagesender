# GitHub Push -- WhatsApp Message Sender

Sube cambios actuales a GitHub con la cuenta erickson558.

Argumento opcional: $ARGUMENTS (pista para el mensaje de commit)

## Pasos

1. Revisar cambios:
   git status
   git diff --stat

2. Determinar tipo de commit:
   - feat: nueva funcionalidad
   - fix: correccion de bug
   - docs: documentacion
   - chore: mantenimiento
   - refactor: refactorizacion

3. Stagear archivos (EXCLUIR siempre: config.json, window_state.json, *.txt logs, build/, build_dist/, build_artifacts/, whats_profile/, *.exe)

4. Crear commit con Conventional Commits:
   git commit -m "tipo(scope): descripcion en espanol"

5. Push: git push origin main

6. Reportar archivos commiteados y URL del commit

## Cuenta GitHub
- Usuario: erickson558
- Repo: https://github.com/erickson558/whatsappmessagesender
- Autenticado via: gh CLI
- Rama: main

## Reglas
- NUNCA --no-verify ni --force
- NUNCA force-push a main
- No amend commits ya publicados
- Crear nuevo commit siempre
