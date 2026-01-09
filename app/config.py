import os
import time
from typing import Any, Dict, Optional

import yaml


class ConfigLoader:
    """Loads YAML config with lightweight mtime-based reloading."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._cache: Optional[Dict[str, Any]] = None
        self._last_mtime: float = 0.0

    def load(self) -> Dict[str, Any]:
        try:
            mtime = os.path.getmtime(self.path)
        except FileNotFoundError:
            raise RuntimeError(f"Config file not found at {self.path}")

        if self._cache is None or mtime > self._last_mtime:
            with open(self.path, "r", encoding="utf-8") as f:
                self._cache = yaml.safe_load(f) or {}
            self._last_mtime = mtime
        return self._cache


def resolve_logging_path(config: Dict[str, Any]) -> str:
    log_path = (
        config.get("logging", {}).get("file")
        or os.environ.get("LOG_PATH")
        or "/var/log/llm-proxy/requests.log"
    )
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    return log_path
