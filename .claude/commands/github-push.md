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

5. Push: si la rama actual no es `main` y ya tiene un PR abierto (`gh pr list --head <rama-actual>`), push a esa misma rama (`git push origin <rama-actual>`) para actualizar el PR. Solo usar `git push origin main` si el trabajo se hizo directamente en `main` o el usuario pidio explicitamente mergear/publicar (recordar que cada push a `main` dispara `release.yml`: build + GitHub Release publico).

6. Reportar archivos commiteados y URL del commit (o del PR si se actualizo una rama de feature)

## Cuenta GitHub
- Usuario: erickson558
- Repo: https://github.com/erickson558/whatsappmessagesender
- Autenticado via: gh CLI
- Rama principal: main (push a main dispara release automatico -- confirmar con el usuario si no fue pedido)

## Reglas
- NUNCA --no-verify ni --force
- NUNCA force-push a main
- No amend commits ya publicados
- Crear nuevo commit siempre
