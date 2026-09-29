from module import Module

def run_tests():
    return Module({'base_dir': '.'}).self_test()

if __name__ == '__main__':
    print(run_tests())
