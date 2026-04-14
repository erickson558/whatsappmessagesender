from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List


SUPPORTED_BROWSERS = ("Opera", "Brave", "Chrome", "Edge")

DEFAULT_BROWSER_PATHS = {
    "Opera": r"C:\Program Files\Opera\opera.exe",
    "Brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    "Chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "Edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
}


def _default_message_block() -> Dict[str, Any]:
    return {
        "contact": "",
        "message": "",
        "date": "",
        "hour": "",
        "minute": "",
        "ampm": "",
        "repeat": "Ninguno",
        "send": False,
        "days": [],
    }


def _ensure_len(items: List[Dict[str, Any]] | None, count: int) -> List[Dict[str, Any]]:
    data = list(items or [])[:count]
    while len(data) < count:
        data.append(_default_message_block())
    return data


def _deep_merge(target: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in defaults.items():
        if isinstance(value, dict):
            node = target.setdefault(key, {})
            if isinstance(node, dict):
                _deep_merge(node, value)
            else:
                target[key] = copy.deepcopy(value)
        else:
            target.setdefault(key, copy.deepcopy(value))
    return target


def _build_default_config() -> Dict[str, Any]:
    return {
        "global": {
            "browser": "Opera",
            "browser_paths": copy.deepcopy(DEFAULT_BROWSER_PATHS),
            "remote_debugging_port": 9222,
            "debug_port_timeout": 60,
            "cdp_timeout": 90000,
            "cdp_retries": 3,
            "extra_wait": 5,
            "keepalive_interval_sec": 60,
            "relaunch_on_disconnect": True,
            "user_data_dir": "whats_profile",
            "browser_extra_args": [],
            "opera_extra_args": [],
            "num_messages_group1": 4,
            "num_messages_group2": 4,
            "num_messages_group3": 4,
            "num_messages_group4": 4,
            "window_geometry": "1250x900",
            "window_state": "normal",
            "window_x": None,
            "window_y": None,
            "version": "8.0.0",
        },
        "messages_group1": [_default_message_block() for _ in range(4)],
        "messages_group2": [_default_message_block() for _ in range(4)],
        "messages_group3": [_default_message_block() for _ in range(4)],
        "messages_group4": [_default_message_block() for _ in range(4)],
    }


class ConfigStore:
    def __init__(self, path: str = "config.json") -> None:
        self.path = path
        self._defaults = _build_default_config()
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        # Si no existe el archivo de configuracion, se crea uno con los valores por defecto.
        if not os.path.exists(self.path):
            data = copy.deepcopy(self._defaults)
            self._write(data)
            return data

        # Fix V8.1.4: capturar errores de parsing para que un config.json
        # corrupto no crashee la aplicacion al iniciar. Se reinicia con defaults.
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (json.JSONDecodeError, OSError, ValueError):
            # Configuracion ilegible: crear backup y regenerar con valores por defecto
            backup_path = self.path + ".bak"
            try:
                import shutil
                shutil.copy2(self.path, backup_path)
            except Exception:
                pass
            data = copy.deepcopy(self._defaults)
            self._write(data)
            return data

        data = _deep_merge(loaded, copy.deepcopy(self._defaults))
        self._migrate_legacy_browser_paths(data)

        g = data["global"]
        data["messages_group1"] = _ensure_len(data.get("messages_group1"), int(g.get("num_messages_group1", 4)))
        data["messages_group2"] = _ensure_len(data.get("messages_group2"), int(g.get("num_messages_group2", 4)))
        data["messages_group3"] = _ensure_len(data.get("messages_group3"), int(g.get("num_messages_group3", 4)))
        data["messages_group4"] = _ensure_len(data.get("messages_group4"), int(g.get("num_messages_group4", 4)))
        self._write(data)
        return data

    @staticmethod
    def _migrate_legacy_browser_paths(data: Dict[str, Any]) -> None:
        global_config = data.setdefault("global", {})
        browser_paths = global_config.setdefault("browser_paths", copy.deepcopy(DEFAULT_BROWSER_PATHS))
        global_config.setdefault("keepalive_interval_sec", 60)
        global_config.setdefault("relaunch_on_disconnect", True)
        global_config.setdefault("user_data_dir", "whats_profile")
        if "browser_extra_args" not in global_config:
            legacy_extra = global_config.get("opera_extra_args", [])
            if isinstance(legacy_extra, list):
                global_config["browser_extra_args"] = list(legacy_extra)
            else:
                global_config["browser_extra_args"] = []

        legacy_map = {
            "opera_path": "Opera",
            "brave_path": "Brave",
            "chrome_path": "Chrome",
            "edge_path": "Edge",
        }
        for old_key, browser_name in legacy_map.items():
            old_value = global_config.get(old_key)
            if old_value:
                browser_paths[browser_name] = old_value
        for browser_name, default_path in DEFAULT_BROWSER_PATHS.items():
            browser_paths.setdefault(browser_name, default_path)

    def _write(self, data: Dict[str, Any] | None = None) -> None:
        payload = data if data is not None else self.data
        with open(self.path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=4, ensure_ascii=False)

    def save(self) -> None:
        self._write()

    def get_global(self, key: str, default: Any = None) -> Any:
        return self.data.get("global", {}).get(key, default)

    def set_global(self, key: str, value: Any) -> None:
        self.data.setdefault("global", {})[key] = value
        self.save()

    def get_browser_choice(self) -> str:
        choice = str(self.get_global("browser", "Opera"))
        return choice if choice in SUPPORTED_BROWSERS else "Opera"

    def set_browser_choice(self, choice: str) -> None:
        if choice not in SUPPORTED_BROWSERS:
            raise ValueError(f"Navegador no soportado: {choice}")
        self.set_global("browser", choice)

    def get_browser_paths(self) -> Dict[str, str]:
        return dict(self.get_global("browser_paths", {}))

    def get_browser_path(self, browser: str) -> str:
        return str(self.get_browser_paths().get(browser, "")).strip()

    def set_browser_path(self, browser: str, path: str) -> None:
        if browser not in SUPPORTED_BROWSERS:
            raise ValueError(f"Navegador no soportado: {browser}")
        global_config = self.data.setdefault("global", {})
        browser_paths = global_config.setdefault("browser_paths", copy.deepcopy(DEFAULT_BROWSER_PATHS))
        browser_paths[browser] = path

        legacy_key_map = {
            "Opera": "opera_path",
            "Brave": "brave_path",
            "Chrome": "chrome_path",
            "Edge": "edge_path",
        }
        global_config[legacy_key_map[browser]] = path
        self.save()

    def reset_default_browser_paths(self) -> None:
        global_config = self.data.setdefault("global", {})
        global_config["browser_paths"] = copy.deepcopy(DEFAULT_BROWSER_PATHS)
        global_config["opera_path"] = DEFAULT_BROWSER_PATHS["Opera"]
        global_config["brave_path"] = DEFAULT_BROWSER_PATHS["Brave"]
        global_config["chrome_path"] = DEFAULT_BROWSER_PATHS["Chrome"]
        global_config["edge_path"] = DEFAULT_BROWSER_PATHS["Edge"]
        self.save()

    def get_group_messages(self, group_id: int) -> List[Dict[str, Any]]:
        key = f"messages_group{group_id}"
        return list(self.data.get(key, []))

    def set_group_messages(self, group_id: int, messages: List[Dict[str, Any]]) -> None:
        key = f"messages_group{group_id}"
        self.data[key] = list(messages)
        self.save()
