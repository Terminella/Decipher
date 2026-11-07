import json

import pytest

from app.config import settings
from app.services import ollama_runtime


def _response(data):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(data).encode("utf-8")

    return Response()


def test_detect_environment_discovers_models_and_details(monkeypatch):
    monkeypatch.setattr(settings, "ollama_base_url", "http://localhost:11434/")
    monkeypatch.setattr(settings, "ollama_timeout", 1.5)
    monkeypatch.setattr(ollama_runtime.shutil, "which", lambda _name: "ollama")
    monkeypatch.setattr(
        ollama_runtime,
        "get_hardware_profile",
        lambda: {
            "memory": {
                "total_bytes": 16 * 1024**3,
                "available_bytes": 8 * 1024**3,
            },
            "gpus": [],
        },
    )
    requests = []

    def request_json(url, timeout):
        requests.append((url, timeout))
        if url.endswith("/api/version"):
            return {"version": "0.5.0"}
        return {
            "models": [{
                "name": "local-model:latest",
                "size": 2 * 1024**3,
                "digest": "abc123",
                "modified_at": "2026-11-07T10:00:00Z",
                "details": {
                    "parameter_size": "3B",
                    "quantization_level": "Q4_K_M",
                    "family": "llama",
                },
            }],
        }

    monkeypatch.setattr(ollama_runtime, "_request_json", request_json)

    result = ollama_runtime.detect_environment()

    assert result["status"] == "available"
    assert result["ollama_installed"] is True
    assert result["version"] == "0.5.0"
    assert result["models"][0]["quantization_level"] == "Q4_K_M"
    assert result["models"][0]["parameter_size"] == "3B"
    assert result["recommendation"]["model_name"] == "local-model:latest"
    assert requests == [
        ("http://localhost:11434/api/version", 1.5),
        ("http://localhost:11434/api/tags", 1.5),
    ]


def test_detect_environment_reports_unavailable_without_crashing(monkeypatch):
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(ollama_runtime.shutil, "which", lambda _name: None)
    monkeypatch.setattr(
        ollama_runtime,
        "get_hardware_profile",
        lambda: {"memory": {"total_bytes": None, "available_bytes": None}, "gpus": []},
    )
    monkeypatch.setattr(
        ollama_runtime,
        "_request_json",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("Could not connect to Ollama.")),
    )

    result = ollama_runtime.detect_environment()

    assert result["status"] == "unavailable"
    assert result["ollama_installed"] is False
    assert result["models"] == []
    assert result["recommendation"] is None
    assert "does not require Ollama" in result["guidance"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:password@localhost:11434",
        "http://localhost:11434?token=secret",
        "http://[",
    ],
)
def test_invalid_endpoint_is_rejected_without_request(monkeypatch, url):
    monkeypatch.setattr(settings, "ollama_base_url", url)
    monkeypatch.setattr(
        ollama_runtime,
        "get_hardware_profile",
        lambda: {"memory": {"total_bytes": None, "available_bytes": None}, "gpus": []},
    )
    monkeypatch.setattr(
        ollama_runtime,
        "_request_json",
        lambda *_args: pytest.fail("Invalid endpoint must not be requested"),
    )

    result = ollama_runtime.detect_environment()

    assert result["status"] == "invalid_configuration"
    assert result["models"] == []
    assert "OLLAMA_BASE_URL" in result["error"]


def test_invalid_model_payload_is_reported(monkeypatch):
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    monkeypatch.setattr(
        ollama_runtime,
        "get_hardware_profile",
        lambda: {"memory": {"total_bytes": None, "available_bytes": None}, "gpus": []},
    )
    monkeypatch.setattr(
        ollama_runtime,
        "_request_json",
        lambda url, _timeout: (
            {"version": "0.5.0"}
            if url.endswith("/api/version")
            else {"models": "not-a-list"}
        ),
    )

    result = ollama_runtime.detect_environment()

    assert result["status"] == "unavailable"
    assert result["error"] == "Ollama returned an invalid model list."


def test_recommendation_does_not_claim_model_compatibility():
    models = [
        {"name": "small", "size_bytes": 2 * 1024**3},
        {"name": "large", "size_bytes": 7 * 1024**3},
    ]
    hardware = {
        "memory": {"available_bytes": 8 * 1024**3},
        "gpus": [],
    }

    result = ollama_runtime._model_recommendation(models, hardware)

    assert result["model_name"] == "small"
    assert "does not guarantee compatibility" in result["basis"]


def test_recommendation_accounts_for_detected_gpu_memory():
    models = [
        {"name": "small", "size_bytes": 5 * 1024**3},
        {"name": "gpu-fit", "size_bytes": 4 * 1024**3},
    ]
    hardware = {
        "memory": {"available_bytes": 16 * 1024**3},
        "gpus": [{"dedicated_memory_bytes": 6 * 1024**3}],
    }

    result = ollama_runtime._model_recommendation(models, hardware)

    assert result["model_name"] == "gpu-fit"
    assert result["execution_path"].startswith("GPU candidate")
