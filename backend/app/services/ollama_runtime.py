import ctypes
import json
import logging
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from ..config import settings


log = logging.getLogger(__name__)


def _request_json(url: str, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError,)):
            raise RuntimeError("The Ollama request timed out.") from exc
        raise RuntimeError("Could not connect to Ollama.") from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError("Could not connect to Ollama.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Ollama returned invalid JSON.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned an unexpected response.")
    return data


def _validated_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise RuntimeError(
            "OLLAMA_BASE_URL must be a valid HTTP(S) URL."
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "OLLAMA_BASE_URL must be an HTTP(S) URL without credentials, "
            "query parameters, or a fragment."
        )
    return value.rstrip("/")


def _memory_bytes() -> tuple[Optional[int], Optional[int]]:
    if platform.system() == "Windows":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_size_t),
                ("available_physical", ctypes.c_size_t),
                ("total_page_file", ctypes.c_size_t),
                ("available_page_file", ctypes.c_size_t),
                ("total_virtual", ctypes.c_size_t),
                ("available_virtual", ctypes.c_size_t),
                ("available_extended_virtual", ctypes.c_size_t),
            ]

        try:
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(
                ctypes.byref(status)
            ):
                return status.total_physical, status.available_physical
        except (AttributeError, OSError):
            log.debug("Windows physical memory detection is unavailable.")
        return None, None

    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            values = {}
            for line in meminfo.read_text(encoding="ascii").splitlines():
                key, value = line.split(":", 1)
                if key in {"MemTotal", "MemAvailable"}:
                    values[key] = int(value.strip().split()[0]) * 1024
            return values.get("MemTotal"), values.get("MemAvailable")
        except (OSError, ValueError, IndexError):
            log.debug("Linux physical memory detection is unavailable.")
    return None, None


def _gpu_devices() -> list[dict]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []

    try:
        result = subprocess.run(
            [
                executable,
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.debug("NVIDIA GPU detection is unavailable.")
        return []

    if result.returncode != 0:
        return []

    devices = []
    for line in result.stdout.splitlines():
        name, separator, memory = line.partition(",")
        if not separator:
            continue
        try:
            memory_mib = int(memory.strip())
        except ValueError:
            continue
        devices.append({
            "name": name.strip(),
            "dedicated_memory_bytes": memory_mib * 1024 * 1024,
        })
    return devices


def get_hardware_profile() -> dict:
    total_memory, available_memory = _memory_bytes()
    gpus = _gpu_devices()
    return {
        "operating_system": platform.platform(),
        "cpu": platform.processor() or None,
        "cpu_cores": os.cpu_count(),
        "memory": {
            "total_bytes": total_memory,
            "available_bytes": available_memory,
        },
        "gpus": gpus,
        "gpu_detection": "detected" if gpus else "unknown",
        "gpu_detection_method": "nvidia-smi",
    }


def _model_recommendation(
    models: list[dict],
    hardware: dict,
) -> Optional[dict]:
    available_memory = hardware["memory"]["available_bytes"]
    if not available_memory:
        return None

    # Disk size is only a rough lower bound; the model runtime also needs
    # memory for context, KV cache, and runtime overhead.
    memory_budget = int(available_memory * 0.55)
    fitting_models = [
        model for model in models
        if model["size_bytes"] is not None
        and model["size_bytes"] <= memory_budget
    ]
    if not fitting_models:
        return None

    gpu_memory = [
        gpu.get("dedicated_memory_bytes")
        for gpu in hardware.get("gpus", [])
        if isinstance(gpu.get("dedicated_memory_bytes"), int)
    ]
    gpu_budget = int(max(gpu_memory) * 0.70) if gpu_memory else None
    gpu_fitting_models = (
        [
            model for model in fitting_models
            if model["size_bytes"] <= gpu_budget
        ]
        if gpu_budget else []
    )
    selected = min(
        gpu_fitting_models or fitting_models,
        key=lambda model: model["size_bytes"],
    )
    execution_path = (
        "GPU candidate; free VRAM and runtime overhead were not measured."
        if gpu_fitting_models
        else "CPU or mixed-GPU execution may be needed."
    )
    quantization = selected.get("quantization_level")
    quantization_note = (
        f" Reported quantization: {quantization}."
        if quantization else ""
    )
    return {
        "model_name": selected["name"],
        "execution_path": execution_path,
        "basis": (
            "Smallest installed model whose on-disk size is within 55% of "
            "detected available system memory. This conservative heuristic "
            "does not account for context size, concurrent workloads, or "
            "runtime overhead and does not guarantee compatibility."
            f"{quantization_note}"
        ),
    }


def detect_environment() -> dict:
    base_url = settings.ollama_base_url
    installed = shutil.which("ollama") is not None
    hardware = get_hardware_profile()
    version = None
    models = []
    warnings = []
    error = None

    try:
        try:
            timeout = float(settings.ollama_timeout)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "OLLAMA_TIMEOUT must be a positive number."
            ) from exc
        if timeout <= 0:
            raise RuntimeError("OLLAMA_TIMEOUT must be greater than zero.")
        base_url = _validated_base_url(base_url)
        try:
            version_data = _request_json(
                f"{base_url}/api/version",
                timeout,
            )
            version = version_data.get("version")
            if version is not None and not isinstance(version, str):
                warnings.append("Ollama returned an invalid version value.")
                version = None
        except RuntimeError as exc:
            warnings.append(f"Could not retrieve Ollama version: {exc}")

        tags = _request_json(f"{base_url}/api/tags", timeout)
        raw_models = tags.get("models")
        if not isinstance(raw_models, list):
            raise RuntimeError("Ollama returned an invalid model list.")

        for item in raw_models:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                warnings.append("An invalid model entry was ignored.")
                continue
            details = item.get("details")
            if not isinstance(details, dict):
                details = {}
            size = item.get("size")
            if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                size = None
            models.append({
                "name": item["name"],
                "size_bytes": size if isinstance(size, int) else None,
                "size_gib": round(size / (1024 ** 3), 2)
                if isinstance(size, int) else None,
                "digest": item.get("digest")
                if isinstance(item.get("digest"), str) else None,
                "modified_at": item.get("modified_at")
                if isinstance(item.get("modified_at"), str) else None,
                "parameter_size": details.get("parameter_size")
                if isinstance(details.get("parameter_size"), str) else None,
                "quantization_level": details.get("quantization_level")
                if isinstance(details.get("quantization_level"), str) else None,
                "family": details.get("family")
                if isinstance(details.get("family"), str) else None,
            })
    except RuntimeError as exc:
        error = str(exc)

    available = error is None
    if not available and error.startswith(("OLLAMA_BASE_URL", "OLLAMA_TIMEOUT")):
        status = "invalid_configuration"
    elif available:
        status = "available"
    else:
        status = "unavailable"

    return {
        "status": status,
        "endpoint": base_url,
        "ollama_installed": installed,
        "version": version,
        "models": models,
        "model_count": len(models),
        "hardware": hardware,
        "recommendation": _model_recommendation(models, hardware),
        "error": error,
        "warnings": warnings,
        "guidance": (
            None if available else
            "Install Ollama or start its local service, then retry detection. "
            "The standard investigation workflow does not require Ollama."
        ),
    }
