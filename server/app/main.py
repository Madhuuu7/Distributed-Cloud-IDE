import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, auth, execute, files, projects, search, workspaces
from app.core.config import AI_PROVIDER, CORS_ORIGINS, EXECUTION_BACKEND
from app.db.session import Base, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Importing the routers above pulls in every model module, so every table is
# registered on Base by the time this runs. Adding a model that no router
# imports would silently skip its table - import it here if that happens.
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if EXECUTION_BACKEND != "docker":
        logger.warning(
            "EXECUTION_BACKEND=%s - user code runs directly on this host with no "
            "isolation. Never use this outside local development.",
            EXECUTION_BACKEND,
        )

    if AI_PROVIDER == "mock":
        logger.info(
            "AI_PROVIDER=mock - responses are generated locally and cost "
            "nothing. Set a real provider for genuine output."
        )

    yield


app = FastAPI(
    title="AI Developer Collaboration Platform API",
    version="0.3.0",
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
app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
app.include_router(ai.router, prefix="/ai", tags=["ai"])
# No prefix: this router owns both /search and /projects/{id}/index, which
# belong to different resource trees.
app.include_router(search.router, tags=["search"])


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "execution_backend": EXECUTION_BACKEND,
        "ai_provider": AI_PROVIDER,
    }
