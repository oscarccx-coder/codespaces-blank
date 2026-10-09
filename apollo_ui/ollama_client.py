import json
import urllib.error
import urllib.request

from apollo_model_memory import resolved_options


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url, model, temperature=0.65, num_ctx=8192,
                 num_batch=256, keep_alive="5m"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = float(temperature)
        options = resolved_options({
            "num_ctx": num_ctx, "num_batch": num_batch, "keep_alive": keep_alive,
        })
        self.num_ctx = options["num_ctx"]
        self.num_batch = options["num_batch"]
        self.keep_alive = options["keep_alive"]

    def _request_json(self, path, payload=None, timeout=20):
        url = self.base_url + path
        data = None
        headers = {"Content-Type": "application/json"}

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError("Could not connect to Ollama.") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama error {exc.code}: {detail}") from exc

    def is_running(self):
        try:
            self._request_json("/api/tags", timeout=3)
            return True
        except Exception:
            return False

    def models(self):
        data = self._request_json("/api/tags", timeout=5)
        out = []
        for item in data.get("models", []):
            name = item.get("name") or item.get("model")
            if name:
                out.append(name)
        return out

    def loaded_models(self):
        """Report Ollama model/RAM/VRAM residency, without loading models."""
        result = self._request_json("/api/ps", timeout=4)
        return [{
            "name": str(model.get("name") or model.get("model") or ""),
            "size_bytes": int(model.get("size", 0) or 0),
            "vram_bytes": int(model.get("size_vram", 0) or 0),
            "ram_estimate_bytes": max(0, int(model.get("size", 0) or 0) - int(model.get("size_vram", 0) or 0)),
        } for model in result.get("models", []) if isinstance(model, dict)]

    def best_model(self):
        models = self.models()
        if self.model in models:
            return self.model
        if models:
            return models[0]
        return self.model

    def _chat_payload(self, messages, stream, tools=None):
        payload = {
            "model": self.best_model(),
            "messages": messages,
            "stream": bool(stream),
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_batch": self.num_batch,
            },
        }
        if tools:
            payload["tools"] = tools
        return payload

    def chat_once(self, messages, tools=None):
        """One non-streaming chat call. Used to detect native tool calls."""
        payload = self._chat_payload(messages, False, tools=tools)
        return self._request_json("/api/chat", payload=payload, timeout=600)

    def stream_chat(self, messages, tools=None):
        payload = self._chat_payload(messages, True, tools=tools)

        req = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=600) as response:
                for raw in response:
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    if "error" in item:
                        raise OllamaError(item["error"])

                    message = item.get("message", {})
                    chunk = message.get("content", "")
                    if chunk:
                        yield chunk

                    if item.get("done"):
                        break

        except urllib.error.URLError as exc:
            raise OllamaError(
                "Cannot connect to Ollama. Start Ollama and try again."
            ) from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama error {exc.code}: {detail}") from exc
