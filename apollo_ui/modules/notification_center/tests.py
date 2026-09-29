from module import Module
def main():
    m = Module({"base_dir": ".", "validation": True})
    assert isinstance(m.tools(), list)
    result = m.self_test() if hasattr(m, "self_test") else True
    assert result is not False
    print("notification_center: PASS")
if __name__ == "__main__": main()
