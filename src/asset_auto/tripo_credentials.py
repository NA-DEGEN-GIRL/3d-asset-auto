"""Read the opt-in remote provider credential without exposing its value."""

import os
from pathlib import Path


def api_key(root: Path) -> str:
    value = os.environ.get("TRIPO_API_KEY", "").strip()
    if not value:
        path = Path(os.environ.get("TRIPO_API_KEY_FILE", ".secrets/tripo_api_key")).expanduser()
        path = path if path.is_absolute() else root / path
        try:
            if path.stat().st_size > 16384:
                raise ValueError("Tripo credential file is unexpectedly large")
            value = path.read_text(encoding="utf-8-sig").strip()
        except FileNotFoundError:
            raise ValueError(
                "Tripo key missing: set TRIPO_API_KEY or save only the key in .secrets/tripo_api_key"
            ) from None
        except OSError:
            raise ValueError("Tripo credential file cannot be read") from None
        except UnicodeError:
            raise ValueError("Tripo credential file must be UTF-8 plain text") from None
    if not value or any(not 33 <= ord(character) <= 126 for character in value):
        raise ValueError("Tripo credential must contain only the plain ASCII API key, without whitespace or controls")
    return value


def key_configured(root: Path) -> bool:
    try:
        api_key(root)
        return True
    except (ValueError, UnicodeError):
        return False
