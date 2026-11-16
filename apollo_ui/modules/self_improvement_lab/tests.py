from module import Module

def run_tests():
    module = Module({'base_dir': '.', 'runtime': None, 'validation': True})
    try:
        assert module.source_learning.worker is None
        assert module.run('source_learning_status', {})['mode'] == 'active'
        return module.self_test()
    finally:
        module.close()

if __name__ == '__main__':
    print(run_tests())
