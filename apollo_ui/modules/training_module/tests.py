from module import Module


def test_storage(module):
    result = module.save_to_file(
        "Test content",
        "test.txt",
    )
    assert result["saved"] is True

    content = module.read_from_file(
        "test.txt"
    )
    assert content == "Test content"


def test_research_save_without_live_network(module):
    original_search = module.search_web
    original_fetch = module.fetch_page

    try:
        module.search_web = lambda query, limit=5: [
            {
                "title": "Circuit Board Guide",
                "url": "https://example.com/circuit-board",
                "snippet": "A test result about circuit board design.",
            },
            {
                "title": "PCB Basics",
                "url": "https://example.com/pcb-basics",
                "snippet": "Copper traces, components and board layers.",
            },
        ]
        module.fetch_page = lambda url, max_chars=30000: {
            "title": "Fetched PCB Source",
            "url": url,
            "content_type": "text/html",
            "text": (
                "Circuit board design uses copper traces, components, vias, "
                "ground planes and controlled power distribution."
            ),
            "truncated": False,
        }

        result = module.explore_web_and_save(
            "circuit board",
            "circuit_board_research.md",
            limit=5,
        )
        assert result["saved"]["saved"] is True
        assert result["source_pages_fetched"] == 2

        content = module.read_from_file("circuit_board_research.md")
        assert "circuit board" in content.lower()
        assert "copper traces" in content.lower()

        matches = module.search_local_research("copper traces circuit board", 3)
        assert matches
        assert matches[0]["filename"] == "circuit_board_research.md"
    finally:
        module.search_web = original_search
        module.fetch_page = original_fetch


def main():
    module = Module({
        "validation": True
    })

    try:
        names = {
            tool["name"]
            for tool in module.tools()
        }

        assert "search_web" in names
        assert "save_to_file" in names
        assert "read_from_file" in names
        assert "explore_web_and_save" in names

        assert module.self_test()

        test_storage(module)
        test_research_save_without_live_network(
            module
        )

        print(
            "Training Module tests passed."
        )

    finally:
        module.close()


if __name__ == "__main__":
    main()
