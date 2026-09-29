import json

from tool_call_parser import extract_text_tool_calls


def fingerprint(call):
    return (
        call["name"],
        json.dumps(
            call.get("arguments", {}),
            sort_keys=True,
            ensure_ascii=False,
        ),
    )


def test_duplicate_fingerprint():
    call_a = {
        "name": "file_builder__write_file",
        "arguments": {
            "path": "demo/main.py",
            "content": "print('hello')",
        },
    }

    call_b = {
        "name": "file_builder__write_file",
        "arguments": {
            "content": "print('hello')",
            "path": "demo/main.py",
        },
    }

    assert fingerprint(call_a) == fingerprint(call_b)


def test_text_call_parser():
    allowed = {
        "file_builder__write_files",
    }

    text = (
        '{"name":"file_builder__write_files","arguments":'
        '{"project":"demo","files":[{"path":"index.html","content":"hello"}]}}'
    )

    calls = extract_text_tool_calls(
        text,
        allowed,
    )

    assert len(calls) == 1
    assert calls[0]["name"] == "file_builder__write_files"
    assert calls[0]["arguments"]["project"] == "demo"


def main():
    test_duplicate_fingerprint()
    test_text_call_parser()
    print("Tool loop regression helpers passed.")


if __name__ == "__main__":
    main()
