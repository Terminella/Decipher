from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import sys

BACKEND_PATH = Path(__file__).resolve().parents[1]
BACKEND_DIR = str(BACKEND_PATH)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _start_server() -> int:
    environment_path = BACKEND_PATH / ".venv"
    environment_python = environment_path / "Scripts" / "python.exe"
    if not environment_python.exists():
        subprocess.run(
            [sys.executable, "-m", "venv", str(environment_path)],
            cwd=BACKEND_PATH,
            check=True,
        )

    subprocess.run(
        [
            str(environment_python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--disable-pip-version-check",
            "-r",
            str(BACKEND_PATH / "requirements.txt"),
        ],
        cwd=BACKEND_PATH,
        check=True,
    )
    try:
        return subprocess.run(
            [
                str(environment_python),
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=BACKEND_PATH,
            check=False,
        ).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(_start_server())


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import (
    ai_environment,
    ai_analysis,
    ai_interactions,
    ai_investigations,
    documents,
    investigations,
    reports,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)

    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered document forensics and verification API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(investigations.router)
app.include_router(reports.router)
app.include_router(ai_environment.router)
app.include_router(ai_investigations.router)
app.include_router(ai_analysis.router)
app.include_router(ai_interactions.router)


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "frontend_url": "http://127.0.0.1:5173",
        "documentation": "/docs",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": settings.app_name,
    }
