"""Load explicit JSON journey definitions."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ghost_hunter.models import Journey


def load_journey(path: Path) -> Journey:
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("journey file exceeds the 2 MB size limit")
        content = json.loads(path.read_text(encoding="utf-8"))
        return Journey.model_validate(content)
    except FileNotFoundError as exc:
        raise ValueError(f"Journey file not found: {path}") from exc
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ValueError(f"Invalid journey {path}: {exc}") from exc
