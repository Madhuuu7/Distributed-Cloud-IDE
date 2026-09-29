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

# --- AI providers -----------------------------------------------------------
# "mock" is the default on purpose: the application, its tests, and a live demo
# all run with no API key and no spend. Switch it once you have a key.
AI_PROVIDER = os.getenv("AI_PROVIDER", "mock").lower()

# Resolved separately from AI_PROVIDER because the best generation model often
# comes from a vendor that sells no embeddings endpoint at all.
AI_EMBEDDING_PROVIDER = os.getenv("AI_EMBEDDING_PROVIDER", "mock").lower()

# Deliberately below the 16k the SDK suggests: this is a student project on a
# metered key, and every feature here produces a bounded answer. Raise it if a
# review starts getting truncated.
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "4096"))
AI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "120"))

AI_CACHE_MAX_ENTRIES = int(os.getenv("AI_CACHE_MAX_ENTRIES", "512"))
AI_CACHE_TTL_SECONDS = int(os.getenv("AI_CACHE_TTL_SECONDS", "3600"))

# Per-user ceiling on AI calls. An unbounded assistant endpoint in front of a
# metered API is a way to lose money to a loop in someone's client code.
AI_RATE_LIMIT_PER_MINUTE = int(os.getenv("AI_RATE_LIMIT_PER_MINUTE", "20"))

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

# Published rates change. Override these to keep /ai/usage honest, or to price
# a model other than the default.
_prompt_price = os.getenv("AI_PRICE_PROMPT_PER_MTOK")
_completion_price = os.getenv("AI_PRICE_COMPLETION_PER_MTOK")
AI_PRICE_PROMPT_PER_MTOK = float(_prompt_price) if _prompt_price else None
AI_PRICE_COMPLETION_PER_MTOK = float(_completion_price) if _completion_price else None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

# --- Retrieval --------------------------------------------------------------
# Structural chunking splits on function and class boundaries; these bound the
# fallback line-window path and stop one huge file from dominating an index.
RAG_MAX_CHUNK_LINES = int(os.getenv("RAG_MAX_CHUNK_LINES", "60"))
RAG_CHUNK_OVERLAP_LINES = int(os.getenv("RAG_CHUNK_OVERLAP_LINES", "10"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "6"))

# Weighting between the two rankers. Vector search generalises; keyword search
# nails exact identifiers. Neither is sufficient alone.
RAG_KEYWORD_WEIGHT = float(os.getenv("RAG_KEYWORD_WEIGHT", "0.3"))
RAG_VECTOR_WEIGHT = float(os.getenv("RAG_VECTOR_WEIGHT", "0.7"))

# --- Agentic fix loop -------------------------------------------------------
# A hard ceiling that the request body cannot exceed. A model that misreads a
# failure can otherwise retry until the budget is gone.
FIX_MAX_ITERATIONS = int(os.getenv("FIX_MAX_ITERATIONS", "3"))
FIX_ITERATION_CEILING = int(os.getenv("FIX_ITERATION_CEILING", "10"))
