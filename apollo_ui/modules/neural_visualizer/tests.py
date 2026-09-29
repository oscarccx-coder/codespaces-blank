from module import Module


def main():
    module = Module({
        "base_dir": ".",
        "validation": True,
    })

    names = {
        tool["name"]
        for tool in module.tools()
    }

    assert "visual_neural_status" in names
    assert "visualize_input" in names
    assert module.self_test()

    status = module.run(
        "visual_neural_status",
        {},
    )

    assert "trained" in status
    assert "state_file" in status

    print(
        "Neural Visualizer tests passed."
    )


if __name__ == "__main__":
    main()
