# Web Explorer

Apollo's public-web module.

Tools:
- `search_web`
- `fetch_url`

The module uses only Python's standard library. It does not require `requests`
or BeautifulSoup.

The Web tab in Apollo uses this module directly, and Apollo chat can call the
same tools when it needs current/public web information.

Private/localhost literal IP targets are blocked.
