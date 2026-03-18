from __future__ import annotations

import argparse
from pathlib import Path


def parse_version(raw: str) -> tuple[int, int, int]:
    parts = raw.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Version invalida: {raw!r}. Usa el formato X.Y.Z.")
    return int(parts[0]), int(parts[1]), int(parts[2])


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el archivo de version para PyInstaller.")
    parser.add_argument("--version", required=True, help="Version semantica en formato X.Y.Z.")
    parser.add_argument("--output", required=True, help="Ruta del archivo de salida.")
    args = parser.parse_args()

    major, minor, patch = parse_version(args.version)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, 0),
    prodvers=({major}, {minor}, {patch}, 0),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [
            StringStruct('CompanyName', 'whatsappmessagesender'),
            StringStruct('FileDescription', 'Programador de Mensajes WhatsApp'),
            StringStruct('FileVersion', '{args.version}'),
            StringStruct('InternalName', 'enviar_whatsapp'),
            StringStruct('LegalCopyright', 'Apache License 2.0'),
            StringStruct('OriginalFilename', 'enviar_whatsapp.exe'),
            StringStruct('ProductName', 'Programador de Mensajes WhatsApp'),
            StringStruct('ProductVersion', '{args.version}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    output_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
