"""Server settings from the environment and, for what it does not set, from a `.env` file.

The file is `backend/.env` or the repository's `.env` (first found). It is read once, here, so that the key, the model
and the limits are the same however the server is started: `uvicorn`, Docker Compose or a test runner that asks for it.
Secrets stay on the server: nothing here is sent to the browser.
"""
import os
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def load_dotenv() -> list[str]:
    """Put the variables of the first `.env` found into the environment, without replacing what is already set.
    Returns the names it set. `EVS_NO_DOTENV=1` skips the file (the tests)."""
    if os.getenv('EVS_NO_DOTENV'):
        return []
    path = next((p for p in (BACKEND / '.env', BACKEND.parent / '.env') if p.is_file()), None)
    if path is None:
        return []
    added = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = (x.strip() for x in line.split('=', 1))
        value = value.strip('"\'')
        if key and key not in os.environ:
            os.environ[key] = value
            added.append(key)
    return added


load_dotenv()
