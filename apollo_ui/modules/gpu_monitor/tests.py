from module import Module


def main():
    module = Module({"validation": True})
    assert module.self_test()
    print("GPU Monitor tests passed.")


if __name__ == "__main__":
    main()
