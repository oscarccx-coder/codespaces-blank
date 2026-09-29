import json


def normalize_tool_call(obj, allowed_names):
    """Return {'name': ..., 'arguments': {...}} for an allowed call, else None."""
    if not isinstance(obj, dict):
        return None

    if isinstance(obj.get("function"), dict):
        fn = obj.get("function") or {}
        name = str(fn.get("name", "")).strip()
        arguments = fn.get("arguments", {})
    else:
        name = str(
            obj.get("name")
            or obj.get("tool")
            or obj.get("tool_name")
            or ""
        ).strip()
        arguments = (
            obj.get("arguments")
            if "arguments" in obj
            else obj.get("args", {})
        )

    allowed = set(allowed_names or [])

    # Small local models often emit provider.action even though Apollo's canonical
    # Ollama name is provider__action. Accept that alias only if the canonical
    # tool is already allowed for this turn.
    if name not in allowed and "." in name:
        provider, action = name.split(".", 1)
        alias = f"{provider}__{action}"
        if alias in allowed:
            name = alias

    if name not in allowed:
        return None

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {"value": arguments}

    if not isinstance(arguments, dict):
        arguments = {}

    # Common Qwen File Builder contract repairs. Apollo reshapes only content the
    # model actually supplied; it does not invent code here.
    if name == "file_builder__write_files":
        if "project" not in arguments and arguments.get("project_name"):
            arguments["project"] = arguments.pop("project_name")

        files = arguments.get("files")
        if isinstance(files, dict):
            arguments["files"] = [
                {"path": str(path), "content": str(content)}
                for path, content in files.items()
            ]

        arguments.setdefault("overwrite", True)

    return {"name": name, "arguments": arguments}


def extract_text_tool_calls(content, allowed_names):
    """
    Extract tool-call JSON objects embedded in ordinary assistant prose.

    Supported examples:
      {"name":"file_builder__write_file","arguments":{...}}
      {"function":{"name":"calculator__calculate","arguments":{...}}}
      {"tool_calls":[{"function":{...}}]}
    """
    content = str(content or "")
    decoder = json.JSONDecoder()
    calls = []
    seen = set()

    i = 0
    while i < len(content):
        start = content.find("{", i)
        if start < 0:
            break

        try:
            obj, end = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            i = start + 1
            continue

        absolute_end = start + end
        candidates = []

        if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
            candidates.extend(obj["tool_calls"])
        else:
            candidates.append(obj)

        for candidate in candidates:
            call = normalize_tool_call(candidate, allowed_names)
            if not call:
                continue

            fingerprint = (
                call["name"],
                json.dumps(
                    call["arguments"],
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ),
            )
            if fingerprint not in seen:
                seen.add(fingerprint)
                calls.append(call)

        i = max(absolute_end, start + 1)

    return calls
