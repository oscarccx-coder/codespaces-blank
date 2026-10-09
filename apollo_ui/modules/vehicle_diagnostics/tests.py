from module import Module


def run_tests():
    m = Module({"base_dir": ".", "validation": True})
    assert m.self_test()
    result = m.run("obd_demo", {})
    assert result["snapshot"]["simulated"] and result["fault_codes"]["simulated"]
    assert "vehicle_obd_clear_codes" not in [x["name"] for x in m.tools()]
    return "Vehicle Diagnostics read-only module contracts passed."


if __name__ == "__main__":
    print(run_tests())
