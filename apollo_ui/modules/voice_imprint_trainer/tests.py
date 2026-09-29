from module import Module


def run_tests():
    module = Module({'base_dir': '.', 'runtime': None, 'validation': True})
    return module.self_test()


if __name__ == '__main__':
    print(run_tests())
