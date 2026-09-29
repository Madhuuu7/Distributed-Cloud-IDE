import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, execute, files, projects
from app.core.config import CORS_ORIGINS, EXECUTION_BACKEND
from app.db.session import Base, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if EXECUTION_BACKEND != "docker":
        logger.warning(
            "EXECUTION_BACKEND=%s - user code runs directly on this host with no "
            "isolation. Never use this outside local development.",
            EXECUTION_BACKEND,
        )

    yield


app = FastAPI(
    title="Distributed Cloud IDE API",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(files.router, prefix="/projects", tags=["files"])
app.include_router(execute.router, prefix="/execute", tags=["execute"])


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "execution_backend": EXECUTION_BACKEND}
