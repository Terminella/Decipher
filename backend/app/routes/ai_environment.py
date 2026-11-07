from fastapi import APIRouter

from ..services import ollama_runtime


router = APIRouter(
    prefix="/ai",
    tags=["AI Environment"],
)


@router.get("/environment")
def get_ai_environment():
    return ollama_runtime.detect_environment()


@router.get("/models")
def list_ollama_models():
    environment = ollama_runtime.detect_environment()
    return {
        "status": environment["status"],
        "endpoint": environment["endpoint"],
        "models": environment["models"],
        "recommendation": environment["recommendation"],
        "error": environment["error"],
    }
