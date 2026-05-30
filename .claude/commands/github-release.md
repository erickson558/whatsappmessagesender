# GitHub Release -- WhatsApp Message Sender

Crea un release en GitHub para la version actual.

Argumento opcional: $ARGUMENTS (notas adicionales)

## Pasos

1. Leer version actual:
   Get-Content VERSION

2. Verificar si tag existe:
   git tag -l "V{version}"

3. Si NO existe el tag, crearlo y pushearlo:
   git tag V{version}
   git push origin V{version}

4. Leer notas de CHANGELOG.md para esta version

5. Crear release:
   gh release create V{version} --title "WhatsApp Message Sender V{version}" --notes "{changelog-notes}"

6. Verificar resultado:
   gh release view V{version}

7. Reportar URL del release y artefactos incluidos

## Cuenta
- erickson558 autenticado via gh CLI
- Repo: https://github.com/erickson558/whatsappmessagesender/releases
- CI/CD crea el .exe automaticamente al hacer push a main (ver .github/workflows/release.yml)
