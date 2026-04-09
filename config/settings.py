from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_if_present() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    api_enabled: bool
    api_url: str
    api_key: str
    default_delay_min: float
    default_delay_max: float
    max_retries: int
    jsonld_wait_seconds: int
    # 0 = off. Otherwise recreate Chrome after every N listing pages (reduces long-session crashes).
    driver_restart_interval_pages: int


_load_dotenv_if_present()

settings = Settings(
    api_enabled=os.getenv("API_ENABLED", "false").lower() in {"1", "true", "yes", "y"},
    api_url=os.getenv("API_URL", "http://localhost:8000"),
    api_key=os.getenv("API_KEY", "change_me"),
    default_delay_min=float(os.getenv("DEFAULT_DELAY_MIN", "2")),
    default_delay_max=float(os.getenv("DEFAULT_DELAY_MAX", "5")),
    max_retries=int(os.getenv("MAX_RETRIES", "3")),
    jsonld_wait_seconds=int(os.getenv("JSONLD_WAIT_SECONDS", "25")),
    driver_restart_interval_pages=int(os.getenv("DRIVER_RESTART_INTERVAL_PAGES", "100")),
)

