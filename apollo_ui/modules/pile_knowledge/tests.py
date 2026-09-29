from module import (
    Module,
    _normalize_query,
)


def main():
    module = Module({
        "base_dir": ".",
        "validation": True,
    })

    try:
        assert module.self_test()

        assert (
            _normalize_query(
                "advanced ai codeing"
            )
            == "advanced ai coding"
        )

        original_remote = (
            module._remote_search
        )
        original_cache = (
            module._search_local_cache
        )

        try:
            # Simulate the exact user's current failure: Hugging Face's
            # Dataset Viewer returns HTTP 500.
            module._remote_search = (
                lambda query, limit: {
                    "results": [],
                    "errors": [
                        {
                            "query_variant": query,
                            "error": (
                                "HTTPError: HTTP Error 500: "
                                "Internal Server Error"
                            ),
                        }
                    ],
                    "rejected": 0,
                    "partial": False,
                    "variants": [query],
                }
            )

            module._search_local_cache = (
                lambda query, limit: {
                    "results": [
                        {
                            "dataset": (
                                "monology/"
                                "pile-uncopyrighted"
                            ),
                            "dataset_label": (
                                "Local Pile Cache "
                                "(Github)"
                            ),
                            "config": "default",
                            "split": (
                                "partial-train"
                            ),
                            "row_idx": None,
                            "pile_set_name": (
                                "Github"
                            ),
                            "text": (
                                "Advanced AI coding in "
                                "Python uses machine "
                                "learning models, "
                                "software testing, "
                                "debugging and neural "
                                "network implementation."
                            ),
                            "characters": 150,
                            "meta": {
                                "pile_set_name": (
                                    "Github"
                                )
                            },
                            "relevance": 0.9,
                            "access_method": (
                                "local_parquet_cache"
                            ),
                            "cache_file": (
                                "0000.parquet"
                            ),
                        }
                    ],
                    "errors": [],
                    "rejected": 0,
                    "partial": True,
                    "cache_used": True,
                }
            )

            result = module.search_pile(
                "advanced ai codeing",
                limit=5,
            )

            assert result["count"] == 1
            assert (
                result["access_method"]
                == "local_parquet_cache"
            )
            assert (
                result["query"]
                == "advanced ai coding"
            )

        finally:
            module._remote_search = (
                original_remote
            )
            module._search_local_cache = (
                original_cache
            )

        assert module._all_remote_service_errors([
            {
                "error": (
                    "HTTPError: HTTP Error 500: "
                    "Internal Server Error"
                )
            }
        ])

        assert module._all_remote_service_errors([
            {
                "error": (
                    "TimeoutError: "
                    "The read operation timed out"
                )
            }
        ])

        test_dynamic_parquet_discovery()

        print(
            "Pile Knowledge v1.7 tests passed."
        )

    finally:
        module.close()



def test_dynamic_parquet_discovery():
    module = Module({
        "base_dir": ".",
        "validation": True,
    })

    try:
        payload = {
            "parquet_files": [
                {
                    "dataset": "monology/pile-uncopyrighted",
                    "config": "default",
                    "split": "partial-train",
                    "url": (
                        "https://huggingface.co/datasets/"
                        "monology/pile-uncopyrighted/"
                        "resolve/refs%2Fconvert%2Fparquet/"
                        "default/partial-train/0000.parquet"
                    ),
                    "filename": "0000.parquet",
                    "size": 265000000,
                },
                {
                    "dataset": "monology/pile-uncopyrighted",
                    "config": "default",
                    "split": "partial-train",
                    "url": (
                        "https://huggingface.co/datasets/"
                        "monology/pile-uncopyrighted/"
                        "resolve/refs%2Fconvert%2Fparquet/"
                        "default/partial-train/0001.parquet"
                    ),
                    "filename": "0001.parquet",
                    "size": 264000000,
                },
            ]
        }

        entries = module._extract_parquet_entries(
            payload
        )

        assert len(entries) == 2
        entries.sort(
            key=module._parquet_sort_key
        )
        assert entries[0]["filename"] == "0000.parquet"

        # Hub-API-style nested response is also accepted.
        nested = {
            "default": {
                "partial-train": [
                    (
                        "https://huggingface.co/api/datasets/"
                        "monology/pile-uncopyrighted/"
                        "parquet/default/partial-train/0.parquet"
                    )
                ]
            }
        }

        nested_entries = (
            module._extract_parquet_entries(
                nested
            )
        )

        assert nested_entries
        assert (
            "0.parquet"
            in nested_entries[0]["filename"]
        )

        assert module._all_remote_service_errors([
            {
                "error": (
                    "HTTPError: HTTP Error 404: "
                    "Not Found"
                )
            }
        ])

    finally:
        module.close()


if __name__ == "__main__":
    main()
