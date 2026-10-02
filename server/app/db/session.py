from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import DATABASE_URL, IS_SQLITE

# SQLite rejects a connection used from a thread other than the one that opened
# it, and FastAPI's threadpool does exactly that. Postgres has no such rule, and
# passing the argument to it is an error.
_connect_args = {"check_same_thread": False} if IS_SQLITE else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    # Managed Postgres closes idle connections without telling the pool, so the
    # first query after a quiet spell gets a dead socket. pool_pre_ping spends a
    # round trip to find out before the request does.
    pool_pre_ping=not IS_SQLITE,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
