import json
import urllib.error
import urllib.request
import http.client
import socket
import threading
import queue
from contextlib import contextmanager
from urllib.parse import urlsplit

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
        self.strict_model = False
        self.last_metrics = {}
        self.num_predict = None
        self.think = None
        self._cancel_event = threading.Event()
        self._connection_lock = threading.Lock()
        self._chat_connection = None
        self._chat_socket = None

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

    @property
    def openai_compatible(self):
        return self.base_url.endswith("/v1")

    def is_running(self):
        try:
            self._request_json("/models" if self.openai_compatible else "/api/tags", timeout=3)
            return True
        except Exception:
            return False

    def models(self):
        if self.openai_compatible:
            data = self._request_json("/models", timeout=5)
            return [str(item["id"]) for item in data.get("data", [])]
        data = self._request_json("/api/tags", timeout=5)
        out = []
        for item in data.get("models", []):
            name = item.get("name") or item.get("model")
            if name:
                out.append(name)
        return out

    def loaded_models(self):
        """Report Ollama model/RAM/VRAM residency, without loading models."""
        if self.openai_compatible:
            return [{"name":name,"residency_unavailable":True} for name in self.models()]
        result = self._request_json("/api/ps", timeout=4)
        return [{
            "name": str(model.get("name") or model.get("model") or ""),
            "size_bytes": int(model.get("size", 0) or 0),
            "vram_bytes": int(model.get("size_vram", 0) or 0),
            "ram_estimate_bytes": max(0, int(model.get("size", 0) or 0) - int(model.get("size_vram", 0) or 0)),
        } for model in result.get("models", []) if isinstance(model, dict)]

    def best_model(self):
        if self.strict_model:
            return self.model
        models = self.models()
        if self.model in models:
            return self.model
        if models:
            return models[0]
        return self.model

    @staticmethod
    def _openai_messages(messages):
        converted = []; pending = []
        for index, original in enumerate(messages):
            item = dict(original)
            if item.get("images"):
                raise OllamaError("Vision attachments require a separately validated llama.cpp vision configuration")
            if item.get("tool_calls"):
                calls=[]
                for number, call in enumerate(item["tool_calls"]):
                    call=dict(call); fn=dict(call["function"])
                    if not isinstance(fn.get("arguments"),str): fn["arguments"]=json.dumps(fn.get("arguments") or {})
                    call.update(id=call.get("id") or f"call_{index}_{number}",type="function",function=fn)
                    calls.append(call);pending.append((call["id"],fn["name"]))
                item["tool_calls"]=calls
            if item.get("role")=="tool":
                if not item.get("tool_call_id"):
                    name=item.get("tool_name") or item.get("name")
                    match=next((c for c in pending if c[1]==name),pending[0] if pending else None)
                    if match is None: raise OllamaError("Tool reply has no matching model tool call")
                    item["tool_call_id"]=match[0];pending.remove(match)
                item.pop("tool_name",None)
            converted.append(item)
        return converted

    def _chat_payload(self, messages, stream, tools=None):
        if self.openai_compatible:
            payload={"model":self.best_model(),"messages":self._openai_messages(messages),"stream":bool(stream),
                     "temperature":self.temperature,"max_tokens":int(self.num_predict or 1024)}
            if tools: payload["tools"]=tools
            if stream: payload["stream_options"]={"include_usage":True}
            return payload
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
        if self.num_predict is not None:
            payload["options"]["num_predict"] = int(self.num_predict)
        if self.think is not None:
            payload["think"] = self.think
        return payload

    def chat_once(self, messages, tools=None):
        return self._cancellable(lambda: self._chat_once_blocking(messages, tools))

    def _cancellable(self, fn):
        results = queue.Queue()
        def receive():
            try: results.put((True, fn()))
            except Exception as exc: results.put((False, exc))
        threading.Thread(target=receive, daemon=True).start()
        while not self._cancel_event.is_set():
            try: ok, result = results.get(timeout=0.1)
            except queue.Empty: continue
            if ok: return result
            raise result
        raise OllamaError("Generation stopped.")

    def _chat_once_blocking(self, messages, tools=None):
        """One non-streaming chat call. Used to detect native tool calls."""
        payload = self._chat_payload(messages, False, tools=tools)
        with self._chat_response(payload) as response:
            result = json.loads(response.read().decode("utf-8"))
            self.last_metrics = self._metrics(result)
            if self.openai_compatible:
                message=dict(result["choices"][0]["message"])
                for call in message.get("tool_calls",[]):
                    fn=call["function"]
                    if isinstance(fn.get("arguments"),str): fn["arguments"]=json.loads(fn["arguments"] or "{}")
                return {"message":message,"done":True,"model":result.get("model",self.model),**self.last_metrics}
            return result

    @staticmethod
    def _metrics(result):
        if "usage" in result:
            usage=result["usage"] or {}
            return {"model":result.get("model",""),"eval_count":usage.get("completion_tokens",0),
                    "prompt_eval_count":usage.get("prompt_tokens",0),"timings":result.get("timings",{})}
        return {key: result[key] for key in ("model", "eval_count", "prompt_eval_count",
                "eval_duration", "total_duration", "load_duration", "prompt_eval_duration",
                "prompt_eval_cached_count") if key in result}

    def model_info(self):
        if self.openai_compatible:
            return {"capabilities":["completion","tools"],"backend":"llama.cpp-compatible server", "vision_validated":False}
        return self._cancellable(lambda: self._request_json("/api/show", {"model": self.model}, timeout=8))

    def cancel_generation(self):
        """Interrupt this per-turn client's socket; never cancel another app's client."""
        self._cancel_event.set()
        with self._connection_lock:
            connection = self._chat_connection
            if self._chat_socket is not None:
                try:
                    self._chat_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if connection is not None:
                connection.close()

    @contextmanager
    def _chat_response(self, payload):
        parts = urlsplit(self.base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise OllamaError("Ollama requires an HTTP or HTTPS server address.")
        connection_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        connection = connection_cls(parts.hostname, parts.port, timeout=10)
        with self._connection_lock:
            self._chat_connection = connection
        try:
            if self._cancel_event.is_set():
                raise OllamaError("Generation stopped.")
            connection.connect()
            with self._connection_lock:
                # HTTP/1.0 getresponse() may close the connection's socket object
                # while its response file still owns the underlying stream.
                # Keep an independent handle so Stop can interrupt that read on
                # Windows as well as POSIX, including HTTPS transport sockets.
                live = connection.sock
                raw = socket.socket(live.family, live.type, live.proto, fileno=live.fileno())
                try:
                    self._chat_socket = raw.dup()
                finally:
                    raw.detach()
            if self._cancel_event.is_set():
                raise OllamaError("Generation stopped.")
            connection.sock.settimeout(600)
            connection.request("POST", parts.path.rstrip("/") + ("/chat/completions" if self.openai_compatible else "/api/chat"),
                body=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status >= 400:
                raise OllamaError(f"Ollama error {response.status}: " + response.read(4000).decode("utf-8", "replace"))
            yield response
        except (OSError, http.client.HTTPException) as exc:
            if self._cancel_event.is_set():
                raise OllamaError("Generation stopped.") from exc
            raise OllamaError("Ollama connection failed: " + str(exc)) from exc
        finally:
            with self._connection_lock:
                if self._chat_connection is connection:
                    self._chat_connection = None
                    if self._chat_socket is not None:
                        self._chat_socket.close()
                    self._chat_socket = None
            connection.close()

    def stream_chat(self, messages, tools=None):
        # Response delivery must stay interruptible even when a platform's
        # socket wrapper does not promptly wake a blocked network read.
        results = queue.Queue()
        def receive():
            try:
                for part in self._stream_chat_blocking(messages, tools):
                    if self._cancel_event.is_set(): break
                    results.put(("part", part))
            except Exception as exc:
                results.put(("error", exc))
            finally:
                results.put(("done", None))
        threading.Thread(target=receive, daemon=True).start()
        while not self._cancel_event.is_set():
            try: kind, result = results.get(timeout=0.1)
            except queue.Empty: continue
            if kind == "done": return
            if kind == "error": raise result
            yield result

    def _stream_chat_blocking(self, messages, tools=None):
        payload = self._chat_payload(messages, True, tools=tools)
        with self._chat_response(payload) as response:
                while not self._cancel_event.is_set():
                    raw = response.readline()
                    if not raw:
                        break
                    if self.openai_compatible:
                        line=raw.decode("utf-8").strip()
                        if not line.startswith("data:"): continue
                        line=line[5:].strip()
                        if line=="[DONE]": break
                        item=json.loads(line)
                        if item.get("usage"): self.last_metrics=self._metrics(item)
                        choices=item.get("choices") or []
                        chunk=(choices[0].get("delta",{}).get("content","") if choices else "")
                        if chunk: yield chunk
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
                        self.last_metrics = self._metrics(item)
                        break
