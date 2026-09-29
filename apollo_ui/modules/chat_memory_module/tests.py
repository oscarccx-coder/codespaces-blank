from module import Module


def main():
    module = Module({"validation": True})
    tool_names = {tool["name"] for tool in module.tools()}
    assert "conversation_context" in tool_names
    assert "previous_user_request" in tool_names

    module.run("save_chat_memory", {
        "user_text": "Build GravityLab and calculate gravitational force.",
        "assistant_text": "GravityLab was created.",
    })
    module.run("save_chat_memory", {
        "user_text": "Add input validation to GravityLab.",
        "assistant_text": "The update failed because files was empty.",
    })
    module.run("save_chat_memory", {
        "user_text": "try again",
        "assistant_text": "Let's try again.",
    })

    previous = module.run("previous_user_request", {"limit": 20})
    assert previous["found"] is True
    assert previous["user_text"] == "Add input validation to GravityLab."

    context = module.run("conversation_context", {
        "query": "GravityLab validation",
        "recent_limit": 3,
        "related_limit": 3,
        "max_chars": 5000,
    })
    assert len(context["recent"]) == 3
    assert context["recent"][0]["user_text"].startswith("Build GravityLab")
    assert context["recent"][-1]["user_text"] == "try again"
    assert module.self_test()
    module.close()
    print("Chat Memory Module 2.2 tests passed.")


if __name__ == "__main__":
    main()
