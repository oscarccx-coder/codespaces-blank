import html
import ipaddress
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124 Safari/537.36 Apollo/2.0"
)


class _ReadableHTMLParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "canvas", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag == "title":
            self.title_depth += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag in {"p", "div", "li", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        text = " ".join((data or "").split())
        if not text:
            return
        if self.title_depth:
            self.title_parts.append(text)
        self.parts.append(text + " ")

    def result(self):
        title = " ".join(self.title_parts).strip()
        body = "".join(self.parts)
        lines = []
        for line in body.splitlines():
            line = " ".join(line.split())
            if line:
                lines.append(line)
        return title, "\n".join(lines)


class _DuckDuckGoParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.current = None
        self.capture_title = False
        self.capture_snippet = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())

        if tag == "a" and "result__a" in classes:
            href = attrs.get("href", "")
            self.current = {
                "title": "",
                "url": href,
                "snippet": "",
            }
            self.capture_title = True

        elif self.current is not None and (
            "result__snippet" in classes
            or "result__body" in classes
        ):
            self.capture_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self.capture_title:
            self.capture_title = False
            if self.current:
                self.results.append(self.current)
                self.current = None

        if tag in {"a", "div", "span"} and self.capture_snippet:
            self.capture_snippet = False

    def handle_data(self, data):
        text = " ".join((data or "").split())
        if not text:
            return

        if self.current is not None:
            if self.capture_title:
                self.current["title"] += (" " if self.current["title"] else "") + text
            elif self.capture_snippet:
                self.current["snippet"] += (" " if self.current["snippet"] else "") + text


def _clean_ddg_url(url):
    url = html.unescape(url or "")
    if url.startswith("//"):
        url = "https:" + url

    parsed = urllib.parse.urlparse(url)

    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)

    return url


class Module:
    def __init__(self, context=None):
        self.context = context or {}

    def tools(self):
        return [
            {
                "name": "search_web",
                "description": (
                    "Search the public web using DuckDuckGo and return result titles, "
                    "URLs and snippets. Use this for current/public information."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "fetch_url",
                "description": (
                    "Fetch a public HTTP/HTTPS webpage and extract readable text, title "
                    "and final URL. Does not execute JavaScript."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "max_chars": {"type": "integer"}
                    },
                    "required": ["url"]
                }
            }
        ]

    @staticmethod
    def _public_url(url):
        url = str(url or "").strip()
        if not url:
            raise ValueError("URL cannot be empty.")

        if "://" not in url:
            url = "https://" + url

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only http:// and https:// URLs are allowed.")
        if not parsed.hostname:
            raise ValueError("URL has no hostname.")

        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"}:
            raise PermissionError("Localhost URLs are blocked by Web Explorer.")

        # Block literal private/loopback/link-local IP addresses.
        try:
            ip = ipaddress.ip_address(host)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            ):
                raise PermissionError("Private/local IP addresses are blocked.")
        except ValueError:
            # Hostname. We intentionally do not require DNS during self-test.
            pass

        return urllib.parse.urlunparse(parsed)

    @staticmethod
    def _request(url, timeout=15):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            },
        )
        return urllib.request.urlopen(req, timeout=timeout)

    def _fetch_url(self, url, max_chars=30000):
        url = self._public_url(url)

        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = 30000
        max_chars = max(1000, min(max_chars, 120000))

        with self._request(url) as response:
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(2_000_000)

        charset = "utf-8"
        match = None
        try:
            import re
            match = re.search(r"charset=([^\s;]+)", content_type, re.I)
        except Exception:
            match = None

        if match:
            charset = match.group(1).strip("\"'")

        text = raw.decode(charset, errors="replace")

        if "html" in content_type.lower() or "<html" in text[:1000].lower():
            parser = _ReadableHTMLParser()
            parser.feed(text)
            title, readable = parser.result()
        else:
            title = ""
            readable = text

        readable = readable.strip()

        return {
            "title": title or final_url,
            "url": final_url,
            "content_type": content_type,
            "text": readable[:max_chars],
            "truncated": len(readable) > max_chars,
            "characters": len(readable),
        }

    def _search_web(self, query, limit=8):
        query = str(query or "").strip()
        if not query:
            raise ValueError("Search query cannot be empty.")

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 8
        limit = max(1, min(limit, 12))

        url = (
            "https://html.duckduckgo.com/html/?q="
            + urllib.parse.quote_plus(query)
        )

        with self._request(url) as response:
            raw = response.read(1_500_000)

        text = raw.decode("utf-8", errors="replace")
        parser = _DuckDuckGoParser()
        parser.feed(text)

        results = []
        seen = set()

        for item in parser.results:
            result_url = _clean_ddg_url(item.get("url", "")).strip()
            title = item.get("title", "").strip()

            if not result_url or not title or result_url in seen:
                continue

            seen.add(result_url)
            results.append({
                "title": title,
                "url": result_url,
                "snippet": item.get("snippet", "").strip(),
            })

            if len(results) >= limit:
                break

        return {
            "query": query,
            "results": results,
            "count": len(results),
        }

    def self_test(self):
        assert self._public_url("example.com") == "https://example.com"
        assert self._public_url("https://example.com/test").startswith("https://")

        blocked = False
        try:
            self._public_url("http://127.0.0.1")
        except PermissionError:
            blocked = True

        assert blocked is True
        assert _clean_ddg_url(
            "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com"
        ) == "https://example.com"

        return "Web Explorer URL/parser safety tests passed."

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "search_web":
            return self._search_web(
                arguments.get("query"),
                arguments.get("limit", 8),
            )

        if action in {"fetch_url", "explore_web"}:
            return self._fetch_url(
                arguments.get("url"),
                arguments.get("max_chars", 30000),
            )

        raise KeyError(action)
