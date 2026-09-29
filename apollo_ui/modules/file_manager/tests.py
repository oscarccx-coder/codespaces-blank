from module import Module


def run_tests():
    module = Module({'base_dir': '.', 'runtime': None})
    names = {tool['name'] for tool in module.tools()}
    assert 'move_item' in names
    assert 'copy_item' in names
    assert 'import_external' in names
    assert module._protected(module.base / 'main.py')
    return module.self_test()


if __name__ == '__main__':
    print(run_tests())
