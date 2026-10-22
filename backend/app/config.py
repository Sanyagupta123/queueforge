import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.getenv("QUEUEFORGE_DATABASE", str(BACKEND_DIR / "queueforge.sqlite"))).expanduser()
MAX_PAYLOAD_BYTES = 64 * 1024
MAX_RESULT_BYTES = 16 * 1024
MAX_ATTEMPTS = 10
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 300
ERROR_TEXT_LIMIT = 1000
