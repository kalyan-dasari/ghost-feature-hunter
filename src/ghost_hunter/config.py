"""Project configuration with conservative defaults."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator

from ghost_hunter.models import StrictModel

CONFIG_NAME = "ghost-hunter.json"


class HunterConfig(StrictModel):
    schema_version: str = "1.0"
    environment: Literal["development", "test", "staging", "production"] = "development"
    base_url: str | None = None
    allowed_hosts: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    allow_writes: bool = False
    production_approved: bool = False
    report_dir: str = "ghost-reports"
    database_url_env: str | None = None
    allowed_database_dirs: list[str] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def safe_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("base_url must be an HTTP(S) origin without credentials, query, or fragment")
        return value


def load_config(project_root: Path) -> HunterConfig:
    config_path = project_root / CONFIG_NAME
    if not config_path.exists():
        return HunterConfig()
    try:
        if config_path.stat().st_size > 100_000:
            raise ValueError("config file exceeds the 100 KB size limit")
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        config = HunterConfig.model_validate(raw)
        return config
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid {CONFIG_NAME}: {exc}") from exc


def write_default_config(project_root: Path) -> Path:
    config_path = project_root / CONFIG_NAME
    if config_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {config_path}")
    config_path.write_text(
        json.dumps(HunterConfig().model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path
