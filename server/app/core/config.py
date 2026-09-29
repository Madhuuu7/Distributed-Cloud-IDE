import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "app.db"))

# SQLite will not create missing directories on its own.
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Comma-separated list of browser origins allowed to call the API.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

# Code execution sandbox.
# "docker" runs each submission in a throwaway container (the safe default).
# "local" falls back to a bare subprocess on this host - development only.
EXECUTION_BACKEND = os.getenv("EXECUTION_BACKEND", "docker").lower()
EXECUTION_TIMEOUT_SECONDS = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "10"))
EXECUTION_MEMORY_LIMIT = os.getenv("EXECUTION_MEMORY_LIMIT", "256m")
EXECUTION_CPU_LIMIT = float(os.getenv("EXECUTION_CPU_LIMIT", "0.5"))
EXECUTION_MAX_OUTPUT_BYTES = int(os.getenv("EXECUTION_MAX_OUTPUT_BYTES", "65536"))
EXECUTION_PIDS_LIMIT = int(os.getenv("EXECUTION_PIDS_LIMIT", "64"))
