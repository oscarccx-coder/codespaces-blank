"""Bounded documentation discovery after repeated Foundry generation failures.

Search queries contain ONLY a fixed technical category, never project text,
source code, filenames, secrets or raw error messages. Results are untrusted.
This never downloads packages or executes code.
"""
from __future__ import annotations

DOC_HOSTS = ("docs.python.org", "doc.qt.io", "docs.sympy.org", "numpy.org", "matplotlib.org", "docs.pytest.org")
QUERIES = {
    "syntax": "site:docs.python.org/3/reference python syntax error",
    "qt": "site:doc.qt.io/qtforpython-6 PySide6 signals widgets tutorial",
    "math": "site:docs.sympy.org symbolic differentiation integrals",
    "plot": "site:matplotlib.org stable embedding in Qt",
    "test": "site:docs.python.org/3/library/unittest.html testing errors",
}

def query_for_failure(message):
    description = str(message).lower()
    if "qt" in description or "signal" in description or "pyside" in description:
        return QUERIES["qt"]
    if "sympy" in description or "calculus" in description:
        return QUERIES["math"]
    if "matplotlib" in description or "plot" in description:
        return QUERIES["plot"]
    if "test" in description or "assertion" in description:
        return QUERIES["test"]
    return QUERIES["syntax"]

def collect_research(failure, search=None):
    """Use Apollo's existing public search only after an explicit UI opt-in."""
    from urllib.parse import urlsplit
    if search is None:
        from modules.web_explorer.module import Module
        search = Module()._search_web
    query = query_for_failure(failure)
    output = search(query, limit=5)
    items = []
    for item in output.get("results", []):
        try:
            url = str(item["url"])
            parts = urlsplit(url)
            if parts.scheme != "https" or not any(
                parts.hostname == host or parts.hostname.endswith("." + host)
                for host in DOC_HOSTS
            ):
                continue
            items.append({
                "title": str(item.get("title", ""))[:120],
                "url": url[:400],
                "snippet": str(item.get("snippet", ""))[:300],
            })
        except (KeyError, AttributeError, TypeError):
            continue
        if len(items) == 3:
            break
    return {"query": query, "sources": items}
