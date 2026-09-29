import re


def extract(text):
    patterns = [
        (
            r"(?i)^\s*(?:please\s+)?"
            r"(?:learn|study|research|remember|absorb)\s+"
            r"(?:about\s+)?(?:from\s+)?(?:the\s+)?pile"
            r"(?:\s+online)?"
            r"(?:\s+(?:about|on|for))?"
            r"\s*[:,-]?\s*"
        ),
        (
            r"(?i)^\s*(?:please\s+)?"
            r"(?:search|query|access|use|look\s+in|look\s+through)\s+"
            r"(?:the\s+)?pile"
            r"(?:\s+online)?"
            r"(?:\s+(?:about|on|for))?"
            r"\s*[:,-]?\s*"
        ),
    ]

    value = " ".join(text.split()).strip()

    for pattern in patterns:
        new = re.sub(
            pattern,
            "",
            value,
            count=1,
        ).strip()

        if new != value:
            value = new
            break

    value = re.sub(
        r"(?i)^\s*(?:about|on|for)\s+",
        "",
        value,
        count=1,
    ).strip(" :,-")

    return value


def main():
    assert extract(
        "learn from The Pile advanced ai coding"
    ) == "advanced ai coding"

    assert extract(
        "search The Pile for transformer core saturation"
    ) == "transformer core saturation"

    assert extract(
        "access the pile online about neural networks"
    ) == "neural networks"

    print(
        "Pile intent routing tests passed."
    )


if __name__ == "__main__":
    main()
