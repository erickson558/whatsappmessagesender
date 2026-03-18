from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = PROJECT_ROOT / "VERSION"
CONFIG_PATHS = (
    PROJECT_ROOT / "config.example.json",
    PROJECT_ROOT / "config.json",
)
SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_version(raw: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(raw.strip())
    if not match:
        raise ValueError(f"Version invalida: {raw!r}. Usa el formato X.Y.Z.")
    return tuple(int(part) for part in match.groups())


def write_version(version: str) -> None:
    VERSION_PATH.write_text(f"{version}\n", encoding="utf-8")


def sync_config_version(version: str) -> None:
    for config_path in CONFIG_PATHS:
        if not config_path.exists():
            continue
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        payload.setdefault("global", {})["version"] = version
        config_path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Incrementa la version semantica del proyecto.")
    parser.add_argument(
        "part",
        nargs="?",
        default="patch",
        choices=("major", "minor", "patch"),
        help="Segmento a incrementar. Por defecto: patch.",
    )
    parser.add_argument(
        "--set",
        dest="set_version",
        help="Establece una version especifica en formato X.Y.Z en lugar de incrementarla.",
    )
    args = parser.parse_args()

    current_version = VERSION_PATH.read_text(encoding="utf-8").strip()

    if args.set_version:
        parse_version(args.set_version)
        new_version = args.set_version.strip()
    else:
        major, minor, patch = parse_version(current_version)
        if args.part == "major":
            major += 1
            minor = 0
            patch = 0
        elif args.part == "minor":
            minor += 1
            patch = 0
        else:
            patch += 1
        new_version = f"{major}.{minor}.{patch}"

    write_version(new_version)
    sync_config_version(new_version)
    print(f"Version actualizada: v{current_version} -> v{new_version}")


if __name__ == "__main__":
    main()
