from module import Module, _clean_ddg_url


def main():
    module = Module({"validation": True})

    names = {tool["name"] for tool in module.tools()}
    assert "search_web" in names
    assert "fetch_url" in names

    assert module.self_test()

    assert _clean_ddg_url(
        "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fhello"
    ) == "https://example.com/hello"

    print("Web Explorer tests passed.")


if __name__ == "__main__":
    main()
