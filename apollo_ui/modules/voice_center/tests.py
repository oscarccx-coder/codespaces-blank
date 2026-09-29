def run(module):
    result = module.self_test()
    assert "Voice Center" in result
    return result
