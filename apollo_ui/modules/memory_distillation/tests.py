from module import Module
def run_tests():
 m=Module({'base_dir':'.'}); return m.self_test()
if __name__=='__main__': print(run_tests())
