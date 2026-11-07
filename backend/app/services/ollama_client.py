import json
import logging
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from ..config import settings


log = logging.getLogger(__name__)
_semaphores: dict[int, threading.BoundedSemaphore] = {}
_semaphore_lock = threading.Lock()


class OllamaInferenceError(RuntimeError):
    pass


def _inference_semaphore() -> threading.BoundedSemaphore:
    try:
        limit = int(settings.ollama_max_concurrency)
    except (TypeError, ValueError) as exc:
        raise OllamaInferenceError(
            "OLLAMA_MAX_CONCURRENCY must be a positive integer."
        ) from exc
    if limit < 1:
        raise OllamaInferenceError(
            "OLLAMA_MAX_CONCURRENCY must be greater than zero."
        )
    with _semaphore_lock:
        if limit not in _semaphores:
            _semaphores[limit] = threading.BoundedSemaphore(limit)
        return _semaphores[limit]


def _validate_settings() -> tuple[str, float, int]:
    try:
        endpoint = settings.ollama_base_url.rstrip("/")
        parsed = urlsplit(endpoint)
    except ValueError as exc:
        raise OllamaInferenceError("OLLAMA_BASE_URL is invalid.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise OllamaInferenceError("OLLAMA_BASE_URL is invalid.")

    try:
        timeout = float(settings.ollama_inference_timeout)
    except (TypeError, ValueError) as exc:
        raise OllamaInferenceError(
            "OLLAMA_INFERENCE_TIMEOUT must be a positive number."
        ) from exc
    try:
        context_window = int(settings.ollama_context_window)
    except (TypeError, ValueError) as exc:
        raise OllamaInferenceError(
            "OLLAMA_CONTEXT_WINDOW must be a positive integer."
        ) from exc
    if timeout <= 0:
        raise OllamaInferenceError(
            "OLLAMA_INFERENCE_TIMEOUT must be greater than zero."
        )
    if context_window < 512:
        raise OllamaInferenceError(
            "OLLAMA_CONTEXT_WINDOW must be at least 512 tokens."
        )
    return endpoint, timeout, context_window


class OllamaClient:
    def chat_json(
        self,
        model: str,
        system_prompt: str,
        user_payload: dict,
        *,
        timeout: float | None = None,
        context_window: int | None = None,
        max_output_tokens: int = 1024,
        think: bool | None = None,
    ) -> dict:
        endpoint, configured_timeout, configured_context_window = _validate_settings()
        timeout = configured_timeout if timeout is None else timeout
        context_window = (
            configured_context_window
            if context_window is None else context_window
        )
        if timeout <= 0:
            raise OllamaInferenceError(
                "Inference timeout must be greater than zero."
            )
        if context_window < 512:
            raise OllamaInferenceError(
                "Inference context window must be at least 512 tokens."
            )
        if max_output_tokens < 1:
            raise OllamaInferenceError(
                "Maximum output tokens must be greater than zero."
            )
        semaphore = _inference_semaphore()
        if not semaphore.acquire(timeout=timeout):
            raise OllamaInferenceError(
                "Timed out waiting for the local model inference slot."
            )

        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "keep_alive": "5m",
            "options": {
                "temperature": 0.1,
                "num_ctx": context_window,
                "num_predict": max_output_tokens,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        user_payload,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
        }
        if think is not None:
            payload["think"] = think
        request = urllib.request.Request(
            f"{endpoint}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            log.warning("Ollama inference returned HTTP %s.", exc.code)
            raise OllamaInferenceError(
                f"Ollama inference failed with HTTP {exc.code}."
            ) from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise OllamaInferenceError(
                    "Ollama inference timed out."
                ) from exc
            raise OllamaInferenceError(
                "Could not connect to Ollama for inference."
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise OllamaInferenceError(
                "Could not connect to Ollama for inference."
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaInferenceError(
                "Ollama returned invalid JSON."
            ) from exc
        finally:
            semaphore.release()

        if not isinstance(data, dict):
            raise OllamaInferenceError(
                "Ollama returned an unexpected response."
            )
        if data.get("done_reason") == "length":
            raise OllamaInferenceError(
                "Ollama reached the configured output token limit."
            )
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaInferenceError(
                "Ollama returned an empty inference response."
            )
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaInferenceError(
                "The model did not return valid JSON."
            ) from exc
        if not isinstance(result, dict):
            raise OllamaInferenceError(
                "The model returned an invalid JSON object."
            )
        return result
