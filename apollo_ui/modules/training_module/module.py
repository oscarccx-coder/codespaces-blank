import html
import ipaddress
import json
import re
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124 Safari/537.36 ApolloTraining/2.0"
)


class _SearchParser(HTMLParser):
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
            self.current = {
                "title": "",
                "url": attrs.get("href", ""),
                "snippet": "",
            }
            self.capture_title = True
            return

        if self.current is not None and (
            "result__snippet" in classes
            or "result__body" in classes
        ):
            self.capture_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self.capture_title:
            self.capture_title = False
            if self.current is not None:
                self.results.append(self.current)
                self.current = None

        if tag in {"a", "div", "span"} and self.capture_snippet:
            self.capture_snippet = False

    def handle_data(self, data):
        text = " ".join((data or "").split())
        if not text or self.current is None:
            return

        if self.capture_title:
            self.current["title"] += (
                (" " if self.current["title"] else "") + text
            )
        elif self.capture_snippet:
            self.current["snippet"] += (
                (" " if self.current["snippet"] else "") + text
            )


class _ReadableParser(HTMLParser):
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

        if tag in {
            "p", "div", "br", "li", "h1", "h2", "h3", "h4",
            "article", "section"
        }:
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

        lines = []
        for line in "".join(self.parts).splitlines():
            line = " ".join(line.split())
            if line:
                lines.append(line)

        return title, "\n".join(lines)


def _clean_search_url(url):
    url = html.unescape(str(url or ""))

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
    """
    Apollo research/training module.

    Runtime storage:
        <Apollo>/storage/training/research/

    Validation storage:
        temporary directory, automatically removed on close.
    """

    def __init__(self, context=None):
        self.context = context or {}
        self.base_dir = Path(
            self.context.get("base_dir", ".")
        ).resolve()
        self.validation = bool(
            self.context.get("validation", False)
        )

        self._temp_dir = None

        if self.validation:
            self._temp_dir = tempfile.TemporaryDirectory(
                prefix="apollo_training_validation_"
            )
            self.storage_dir = Path(self._temp_dir.name).resolve()
        else:
            self.storage_dir = (
                self.base_dir / "storage" / "training" / "research"
            ).resolve()
            self.storage_dir.mkdir(parents=True, exist_ok=True)

    def tools(self):
        return [
            {
                "name": "search_web",
                "description": (
                    "Search the public web for research sources and return "
                    "titles, URLs and snippets."
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
                "name": "fetch_page",
                "description": (
                    "Fetch readable text from a public HTTP/HTTPS webpage."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "max_chars": {"type": "integer"}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "save_to_file",
                "description": (
                    "Save research text into Apollo's protected local "
                    "training-module storage."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "filename": {"type": "string"}
                    },
                    "required": ["content", "filename"]
                }
            },
            {
                "name": "read_from_file",
                "description": (
                    "Read a saved research note from Apollo's training-module storage."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"}
                    },
                    "required": ["filename"]
                }
            },
            {
                "name": "list_research_files",
                "description": "List locally saved research/training files.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "search_local_research",
                "description": (
                    "Search Apollo's locally saved research files and return relevant "
                    "snippets. Use this before re-researching a topic Apollo may already know."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                        "max_chars": {"type": "integer"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "explore_web_and_save",
                "description": (
                    "Perform real research: search the web, fetch readable text from several "
                    "source pages, then save the source-backed research locally."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "filename": {"type": "string"},
                        "limit": {"type": "integer"}
                    },
                    "required": ["query", "filename"]
                }
            }
        ]

    @staticmethod
    def _limit(value, default=5, maximum=12):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default

        return max(1, min(value, maximum))

    @staticmethod
    def _public_url(url):
        url = str(url or "").strip()

        if not url:
            raise ValueError("URL cannot be empty.")

        if "://" not in url:
            url = "https://" + url

        parsed = urllib.parse.urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS URLs are allowed.")

        if not parsed.hostname:
            raise ValueError("URL has no hostname.")

        host = parsed.hostname.lower()

        if host in {"localhost", "localhost.localdomain"}:
            raise PermissionError("Localhost URLs are blocked.")

        try:
            ip = ipaddress.ip_address(host)

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            ):
                raise PermissionError(
                    "Private/local IP addresses are blocked."
                )
        except ValueError:
            pass

        return urllib.parse.urlunparse(parsed)

    @staticmethod
    def _request(url, timeout=15):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "text/plain;q=0.9,*/*;q=0.5"
                ),
            },
        )

        return urllib.request.urlopen(
            request,
            timeout=timeout,
        )

    def _safe_file(self, filename):
        filename = str(filename or "").strip().replace("\\", "/")

        if not filename:
            raise ValueError("filename cannot be empty.")

        relative = Path(filename)

        if relative.is_absolute():
            raise PermissionError("Absolute paths are not allowed.")

        target = (self.storage_dir / relative).resolve()

        if (
            target != self.storage_dir
            and self.storage_dir not in target.parents
        ):
            raise PermissionError(
                "Research file path escapes training storage."
            )

        return target

    def _search_wikipedia(self, query, limit=5):
        params = urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "utf8": 1,
            "format": "json",
        })

        url = (
            "https://en.wikipedia.org/w/api.php?"
            + params
        )

        with self._request(url, timeout=20) as response:
            raw = response.read(2_000_000)

        data = json.loads(
            raw.decode("utf-8", errors="replace")
        )

        output = []

        for item in (
            data.get("query", {})
            .get("search", [])
        ):
            title = str(
                item.get("title", "")
            ).strip()

            if not title:
                continue

            snippet = re.sub(
                r"<[^>]+>",
                "",
                html.unescape(
                    str(
                        item.get("snippet", "")
                    )
                ),
            )

            page_url = (
                "https://en.wikipedia.org/wiki/"
                + urllib.parse.quote(
                    title.replace(" ", "_")
                )
            )

            output.append({
                "title": title,
                "url": page_url,
                "snippet": snippet,
                "provider": "wikipedia_fallback",
            })

        return output

    def search_web(self, query, limit=5):
        query = str(query or "").strip()

        if not query:
            raise ValueError("query cannot be empty.")

        limit = self._limit(limit)
        output = []

        # Primary provider: DuckDuckGo HTML.
        try:
            search_url = (
                "https://html.duckduckgo.com/html/?q="
                + urllib.parse.quote_plus(query)
            )

            with self._request(
                search_url,
                timeout=18,
            ) as response:
                raw = response.read(1_500_000)

            text = raw.decode(
                "utf-8",
                errors="replace",
            )

            parser = _SearchParser()
            parser.feed(text)

            seen = set()

            for item in parser.results:
                url = _clean_search_url(
                    item.get("url", "")
                ).strip()

                title = str(
                    item.get("title", "")
                ).strip()

                if (
                    not title
                    or not url
                    or url in seen
                ):
                    continue

                seen.add(url)

                output.append({
                    "title": title,
                    "url": url,
                    "snippet": str(
                        item.get("snippet", "")
                    ).strip(),
                    "provider": "duckduckgo",
                })

                if len(output) >= limit:
                    break

        except Exception:
            output = []

        # Automated search engines sometimes block local scripts. Fall back to a
        # stable public knowledge API so research does not simply die.
        if not output:
            output = self._search_wikipedia(
                query,
                limit=limit,
            )

        return output

    def fetch_page(self, url, max_chars=30000):
        url = self._public_url(url)

        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = 30000

        max_chars = max(
            1000,
            min(max_chars, 120000)
        )

        with self._request(url) as response:
            final_url = response.geturl()
            content_type = response.headers.get(
                "Content-Type",
                ""
            )
            raw = response.read(2_000_000)

        charset = "utf-8"
        match = re.search(
            r"charset=([^\s;]+)",
            content_type,
            re.I,
        )

        if match:
            charset = match.group(1).strip("\"'")

        source = raw.decode(
            charset,
            errors="replace"
        )

        if (
            "html" in content_type.lower()
            or "<html" in source[:1000].lower()
        ):
            parser = _ReadableParser()
            parser.feed(source)
            title, readable = parser.result()
        else:
            title = final_url
            readable = source

        readable = readable.strip()

        return {
            "title": title or final_url,
            "url": final_url,
            "content_type": content_type,
            "text": readable[:max_chars],
            "truncated": len(readable) > max_chars,
        }

    def save_to_file(self, content, filename):
        target = self._safe_file(filename)
        content = str(content or "")

        if len(content.encode("utf-8")) > 2_000_000:
            raise ValueError(
                "Research file exceeds the 2 MB limit."
            )

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        target.write_text(
            content,
            encoding="utf-8"
        )

        return {
            "saved": True,
            "filename": str(
                target.relative_to(
                    self.storage_dir
                )
            ).replace("\\", "/"),
            "path": str(target),
            "characters": len(content),
        }

    def read_from_file(self, filename):
        target = self._safe_file(filename)

        if not target.exists() or not target.is_file():
            raise FileNotFoundError(filename)

        return target.read_text(
            encoding="utf-8",
            errors="replace"
        )

    def list_research_files(self):
        files = []

        if not self.storage_dir.exists():
            return files

        for path in sorted(
            self.storage_dir.rglob("*")
        ):
            if not path.is_file():
                continue

            files.append(
                str(
                    path.relative_to(
                        self.storage_dir
                    )
                ).replace("\\", "/")
            )

            if len(files) >= 500:
                break

        return files

    @staticmethod
    def _research_terms(text):
        return set(re.findall(r"[a-zA-Z0-9']+", str(text or "").lower()))

    def search_local_research(self, query, limit=3, max_chars=5000):
        query = str(query or "").strip()
        if not query:
            raise ValueError("query cannot be empty.")
        limit = self._limit(limit, default=3, maximum=10)
        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = 5000
        max_chars = max(500, min(max_chars, 15000))
        wanted = self._research_terms(query)
        if not wanted:
            return []

        ranked = []
        for filename in self.list_research_files():
            if filename.startswith("self_test/"):
                continue
            try:
                content = self.read_from_file(filename)
            except Exception:
                continue
            terms = self._research_terms(filename + " " + content)
            overlap = len(wanted & terms)
            if not overlap:
                continue
            phrase_bonus = 2 if query.lower() in content.lower() else 0
            score = overlap + phrase_bonus
            ranked.append((score, filename, content))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            {
                "filename": filename,
                "score": score,
                "content": content[:max_chars],
                "truncated": len(content) > max_chars,
            }
            for score, filename, content in ranked[:limit]
        ]

    def explore_web_and_save(
        self,
        query,
        filename,
        limit=5,
    ):
        """
        Real research pass: search, then fetch several source pages.

        This deliberately takes longer than the old snippet-only version because
        Apollo is actually reading source text before it writes the local file.
        """
        query = str(query or "").strip()
        if not query:
            raise ValueError("query cannot be empty.")

        limit = self._limit(limit, default=5, maximum=8)
        results = self.search_web(query, limit=limit)
        source_limit = min(5, len(results))
        source_records = []

        for result in results[:source_limit]:
            record = {
                "title": result.get("title", "Untitled"),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
                "text": "",
                "error": "",
            }
            try:
                page = self.fetch_page(record["url"], max_chars=14000)
                record["title"] = page.get("title") or record["title"]
                record["url"] = page.get("url") or record["url"]
                record["text"] = page.get("text", "")
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            source_records.append(record)

        lines = [
            f"# Apollo Research: {query}",
            "",
            f"Search results found: {len(results)}",
            f"Source pages fetched: {sum(1 for x in source_records if x['text'])}",
            "",
            "This file is Apollo's local research memory. It contains source URLs,",
            "search snippets, and readable text fetched from the source pages.",
            "",
        ]

        for index, source in enumerate(source_records, 1):
            lines.extend([
                f"## Source {index}: {source['title']}",
                f"URL: {source['url']}",
                "",
                "### Search snippet",
                source["snippet"] or "(No search snippet returned.)",
                "",
            ])
            if source["text"]:
                lines.extend([
                    "### Readable source text",
                    source["text"],
                    "",
                ])
            else:
                lines.extend([
                    "### Fetch error",
                    source["error"] or "Page text could not be fetched.",
                    "",
                ])

        # Keep unfetched search results as references too.
        if len(results) > source_limit:
            lines.extend(["## Additional search references", ""])
            for result in results[source_limit:]:
                lines.extend([
                    f"- {result.get('title', 'Untitled')}",
                    f"  {result.get('url', '')}",
                    f"  {result.get('snippet', '')}",
                ])

        content = "\n".join(lines).rstrip() + "\n"
        saved = self.save_to_file(content, filename)
        return {
            "query": query,
            "results": results,
            "sources": source_records,
            "source_pages_attempted": len(source_records),
            "source_pages_fetched": sum(1 for x in source_records if x["text"]),
            "saved": saved,
        }

    def self_test(self):
        # No live internet is required for validation.
        saved = self.save_to_file(
            "Apollo training module self-test.",
            "self_test/test.txt",
        )

        assert saved["saved"] is True

        content = self.read_from_file(
            "self_test/test.txt"
        )

        assert content == (
            "Apollo training module self-test."
        )

        files = self.list_research_files()
        assert "self_test/test.txt" in files

        assert (
            self._public_url("example.com")
            == "https://example.com"
        )

        blocked = False

        try:
            self._public_url(
                "http://127.0.0.1"
            )
        except PermissionError:
            blocked = True

        assert blocked is True

        return (
            "Training module storage, path safety "
            "and URL safety tests passed."
        )

    def build_ui(
        self,
        parent=None,
        ui_context=None,
    ):
        # Imported lazily so headless validator runs do not require Qt.
        from PySide6.QtCore import (
            QObject,
            QRunnable,
            QThreadPool,
            Signal,
            Slot,
            QUrl,
        )
        from PySide6.QtGui import (
            QDesktopServices,
        )
        from PySide6.QtWidgets import (
            QWidget,
            QVBoxLayout,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QTextBrowser,
            QMessageBox,
        )

        module = self

        class Signals(QObject):
            finished = Signal(object)
            failed = Signal(str)

        class Task(QRunnable):
            def __init__(self, fn):
                super().__init__()
                self.fn = fn
                self.signals = Signals()
                self.setAutoDelete(True)

            @Slot()
            def run(self):
                try:
                    self.signals.finished.emit(
                        self.fn()
                    )
                except Exception as exc:
                    self.signals.failed.emit(
                        f"{type(exc).__name__}: {exc}"
                    )

        page = QWidget(parent)
        layout = QVBoxLayout(page)

        title = QLabel(
            "Research & Training"
        )
        title.setStyleSheet(
            "font-size:22px;"
            "font-weight:700;"
            "color:#e7fffb;"
        )

        info = QLabel(
            "Search public web sources and save "
            "research notes into Apollo's local storage."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#91bdb6;"
        )

        query_input = QLineEdit()
        query_input.setPlaceholderText(
            "Research topic — e.g. circuit board design"
        )

        filename_input = QLineEdit()
        filename_input.setPlaceholderText(
            "Save filename — e.g. electronics/circuit_boards.md"
        )

        buttons = QHBoxLayout()

        search_button = QPushButton(
            "Search Web"
        )
        research_button = QPushButton(
            "Deep Research + Save"
        )
        files_button = QPushButton(
            "List Saved Files"
        )
        folder_button = QPushButton(
            "Open Research Folder"
        )

        buttons.addWidget(
            search_button
        )
        buttons.addWidget(
            research_button
        )
        buttons.addWidget(
            files_button
        )
        buttons.addWidget(
            folder_button
        )
        buttons.addStretch()

        output = QTextBrowser()
        output.setOpenExternalLinks(True)

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(query_input)
        layout.addWidget(filename_input)
        layout.addLayout(buttons)
        layout.addWidget(output, 1)

        pool = QThreadPool.globalInstance()
        active_tasks = []

        def keep(task):
            active_tasks.append(task)

            def release(*_):
                try:
                    active_tasks.remove(task)
                except ValueError:
                    pass

            task.signals.finished.connect(
                release
            )
            task.signals.failed.connect(
                release
            )

        def show_error(message):
            output.setPlainText(
                "Research error:\n\n"
                + message
            )

        def show_results(results):
            pieces = []

            for index, item in enumerate(
                results,
                1
            ):
                title_text = html.escape(
                    str(
                        item.get(
                            "title",
                            "Untitled",
                        )
                    )
                )
                url = html.escape(
                    str(
                        item.get(
                            "url",
                            "",
                        )
                    ),
                    quote=True,
                )
                snippet = html.escape(
                    str(
                        item.get(
                            "snippet",
                            "",
                        )
                    )
                )

                pieces.append(
                    "<div style='margin:12px 0;'>"
                    f"<b>{index}. "
                    f"<a href='{url}'>{title_text}</a>"
                    "</b><br>"
                    f"{snippet}"
                    "</div>"
                )

            if not pieces:
                pieces.append(
                    "No search results returned."
                )

            output.setHtml(
                "\n".join(pieces)
            )

        def search():
            query = query_input.text().strip()

            if not query:
                QMessageBox.information(
                    page,
                    "Research & Training",
                    "Enter a research topic first.",
                )
                return

            output.setPlainText(
                f"Searching for: {query}\n\nPlease wait..."
            )

            task = Task(
                lambda: module.search_web(
                    query,
                    limit=8,
                )
            )
            task.signals.finished.connect(
                show_results
            )
            task.signals.failed.connect(
                show_error
            )
            keep(task)
            pool.start(task)

        def research_and_save():
            query = query_input.text().strip()
            filename = filename_input.text().strip()

            if not query:
                QMessageBox.information(
                    page,
                    "Research & Training",
                    "Enter a research topic first.",
                )
                return

            if not filename:
                safe = re.sub(
                    r"[^a-zA-Z0-9_-]+",
                    "_",
                    query,
                ).strip("_").lower()

                filename = (
                    safe[:60]
                    or "research"
                ) + ".md"

                filename_input.setText(
                    filename
                )

            output.setPlainText(
                f"Researching: {query}\n"
                f"Saving to: {filename}\n\n"
                "Please wait..."
            )

            task = Task(
                lambda: module.explore_web_and_save(
                    query,
                    filename,
                    limit=8,
                )
            )

            def finished(result):
                saved = result.get(
                    "saved",
                    {}
                )
                output.setPlainText(
                    f"Research saved.\n\n"
                    f"Topic: {result.get('query')}\n"
                    f"Search results: {len(result.get('results', []))}\n"
                    f"Source pages read: {result.get('source_pages_fetched', 0)} / {result.get('source_pages_attempted', 0)}\n"
                    f"File: {saved.get('filename')}\n"
                    f"Path: {saved.get('path')}"
                )

            task.signals.finished.connect(
                finished
            )
            task.signals.failed.connect(
                show_error
            )
            keep(task)
            pool.start(task)

        def list_files():
            files = module.list_research_files()

            output.setPlainText(
                "Saved research files:\n\n"
                + (
                    "\n".join(files)
                    if files
                    else "No saved research yet."
                )
            )

        def open_folder():
            module.storage_dir.mkdir(
                parents=True,
                exist_ok=True
            )
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(module.storage_dir)
                )
            )

        search_button.clicked.connect(
            search
        )
        research_button.clicked.connect(
            research_and_save
        )
        files_button.clicked.connect(
            list_files
        )
        folder_button.clicked.connect(
            open_folder
        )

        return page

    def run(self, action, arguments):
        arguments = arguments or {}

        if action == "search_web":
            return self.search_web(
                arguments.get("query"),
                arguments.get("limit", 5),
            )

        if action == "fetch_page":
            return self.fetch_page(
                arguments.get("url"),
                arguments.get(
                    "max_chars",
                    30000,
                ),
            )

        if action == "save_to_file":
            return self.save_to_file(
                arguments.get("content"),
                arguments.get("filename"),
            )

        if action == "read_from_file":
            return {
                "filename": arguments.get(
                    "filename"
                ),
                "content": self.read_from_file(
                    arguments.get(
                        "filename"
                    )
                ),
            }

        if action == "list_research_files":
            return {
                "files": self.list_research_files()
            }

        if action == "search_local_research":
            return {
                "matches": self.search_local_research(
                    arguments.get("query"),
                    arguments.get("limit", 3),
                    arguments.get("max_chars", 5000),
                )
            }

        if action == "explore_web_and_save":
            return self.explore_web_and_save(
                arguments.get("query"),
                arguments.get("filename"),
                arguments.get("limit", 5),
            )

        raise KeyError(
            f"Unknown action: {action}"
        )

    def close(self):
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
            except Exception:
                pass
            self._temp_dir = None
