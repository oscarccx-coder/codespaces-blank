from module import Module


def main():
    module = Module({"validation": True})

    names = {tool["name"] for tool in module.tools()}
    assert "add_training_example" in names
    assert "train_network" in names
    assert "predict_label" in names

    result = module.self_test()
    assert result

    status = module.run("neural_status", {})
    assert status["trained"] is True
    assert "ready_for_use" in status
    assert "last_training" in status
    assert status["backend"] == "pure_python_mlp_v2"

    print("Neural Learning Module tests passed.")


if __name__ == "__main__":
    main()
