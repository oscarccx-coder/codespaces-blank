from tool_call_parser import extract_text_tool_calls


ALLOWED = {
    "file_builder__write_file",
    "module_factory__create_candidate",
}


def main():
    sample = r'''To create the file, I'll use the function now.
{"name": "file_builder__write_file", "arguments": {"path": "demo/main.py", "content": "print('hello')\\n"}}'''

    calls = extract_text_tool_calls(sample, ALLOWED)
    assert len(calls) == 1, calls
    assert calls[0]["name"] == "file_builder__write_file"
    assert calls[0]["arguments"]["path"] == "demo/main.py"

    wrapped = r'''{"tool_calls":[{"function":{"name":"module_factory__create_candidate","arguments":{"module_id":"demo","name":"Demo","description":"x","module_code":"class Module:\\n    pass\\n"}}}]}'''
    calls = extract_text_tool_calls(wrapped, ALLOWED)
    assert len(calls) == 1, calls
    assert calls[0]["name"] == "module_factory__create_candidate"

    print("Text tool-call parser tests passed.")


if __name__ == "__main__":
    main()
