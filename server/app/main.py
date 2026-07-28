from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, projects, files
from app.db.session import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Distributed Cloud IDE API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(projects.router, prefix="/projects", tags=["projects"])
app.include_router(files.router, prefix="/projects", tags=["files"])

@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
