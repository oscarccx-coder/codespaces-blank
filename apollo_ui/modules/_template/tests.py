from module import Module


def main():
    module = Module({"validation": True})

    # Add assertions that exercise safe behavior exposed by your module.
    tools = module.tools()
    assert isinstance(tools, list)

    result = module.self_test()
    assert result is not False

    print("Apollo module tests passed.")


if __name__ == "__main__":
    main()
