import concurrent.futures
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path


PILE_DATASET = "monology/pile-uncopyrighted"
HF_API = "https://datasets-server.huggingface.co"
HF_PARQUET_API = (
    HF_API
    + "/parquet?dataset="
    + urllib.parse.quote(
        PILE_DATASET,
        safe="",
    )
)

HF_HUB_PARQUET_API = (
    "https://huggingface.co/api/datasets/"
    + PILE_DATASET
    + "/parquet"
)

# Cache catalog is discovered from Hugging Face at runtime. Generated Parquet
# paths for huge datasets are implementation details and must not be hard-coded.
PILE_CATALOG_FILENAME = "parquet_catalog.json"
PILE_CATALOG_TTL_SECONDS = 24 * 60 * 60

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/124 Safari/537.36 ApolloKnowledge/1.7"
)

TOKEN_RE = re.compile(r"[a-zA-Z0-9+#.'_-]+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "i", "in", "into", "is", "it", "learn", "learning", "of",
    "on", "online", "or", "the", "this", "to", "use", "using", "with",
    "about", "advanced", "more", "all", "that", "knowledge", "pile",
}

AI_ALIASES = {
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "neural", "neural network", "neural networks", "transformer",
    "language model", "language models", "llm", "llms", "model", "models",
    "ml",
}

CODING_ALIASES = {
    "coding", "code", "programming", "programmer", "software",
    "developer", "development", "python", "javascript", "typescript",
    "java", "c++", "rust", "function", "class", "debug", "debugging",
    "algorithm", "algorithms", "implementation",
}

AI_TECHNICAL_SIGNALS = {
    "machine learning", "deep learning", "neural network", "neural networks",
    "transformer", "transformers", "language model", "language models",
    "large language model", "llm", "llms", "model training", "training loop",
    "inference", "embedding", "embeddings", "attention", "backpropagation",
    "gradient", "gradients", "loss function", "optimizer", "optimizers",
    "fine tuning", "fine-tuning", "quantization", "pytorch", "tensorflow",
    "keras", "scikit-learn", "sklearn", "hugging face", "tokenizer",
    "tokenization", "vector database", "retrieval augmented generation", "rag",
}

AI_CORE_SIGNALS = {
    "machine learning", "deep learning", "neural network", "neural networks",
    "transformer", "transformers", "language model", "language models",
    "large language model", "model training", "training loop", "inference",
    "attention", "backpropagation", "loss function", "optimizer", "optimizers",
    "fine tuning", "fine-tuning", "quantization",
    "retrieval augmented generation",
}

AI_FRAMEWORK_SIGNALS = {
    "pytorch", "torch", "tensorflow", "keras", "scikit-learn", "sklearn",
    "hugging face", "transformers",
}

ADVANCED_ENGINEERING_SIGNALS = {
    "architecture", "data pipeline", "data pipelines", "evaluation", "benchmark",
    "benchmarks", "unit test", "unit tests", "integration test",
    "integration tests", "debugging", "profiling", "optimization",
    "memory management", "gpu", "cuda", "batching", "async", "concurrency",
    "multiprocessing", "distributed training", "checkpoint", "checkpoints",
    "api", "apis", "agent", "agents", "tool calling", "structured output",
    "vector", "cosine similarity", "numpy", "pandas",
}

MARKUP_BOILERPLATE_SIGNALS = {
    "<?xml", "<!doctype", "<html", "<doi_batch", "xmlns:", "schemalocation",
    "crossref.org/schema", "xsi:",
}

GENERIC_CAREER_SIGNALS = {
    "career", "salary", "job market", "online course", "degree program",
    "bootcamp", "become an ai professional",
}

IMPLEMENTATION_SIGNALS = {
    "implementation",
    "source code",
    "code example",
    "code examples",
    "repository",
    "pytorch",
    "tensorflow",
    "keras",
    "scikit-learn",
    "sklearn",
    "training loop",
    "inference",
    "evaluation",
    "unit test",
    "unit tests",
    "integration test",
    "integration tests",
    "debugging",
    "profiling",
    "data pipeline",
    "data pipelines",
    "architecture",
    "optimizer",
    "optimizers",
    "loss function",
    "attention",
    "embedding",
    "embeddings",
    "api",
    "apis",
    "cuda",
    "gpu",
    "batching",
    "async",
    "concurrency",
}

LIBRARY_SIGNALS = {
    "pytorch",
    "torch",
    "tensorflow",
    "keras",
    "scikit-learn",
    "sklearn",
    "numpy",
    "pandas",
    "transformers",
    "hugging face",
}

NOVICE_SIGNALS = {
    "complete beginner",
    "absolute beginner",
    "beginner in machine learning",
    "beginner in deep learning",
    "new to machine learning",
    "new to deep learning",
    "new to python",
    "no knowledge about",
    "no knowledge of",
    "i don't know how",
    "i do not know how",
    "how do i start",
    "for beginners",
    "beginner tutorial",
    "as a learning tool",
    "trying to do something simple",
    "i am trying to do something simple",
    "i'm trying to do something simple",
}

CODE_SYNTAX_PATTERNS = (
    r"\bdef\s+[a-zA-Z_]\w*\s*\(",
    r"\bclass\s+[a-zA-Z_]\w*\s*(?:\(|:)",
    r"\bimport\s+[a-zA-Z_][\w.]*",
    r"\bfrom\s+[a-zA-Z_][\w.]*\s+import\s+",
    r"\basync\s+def\s+",
    r"\btorch\.",
    r"\bnn\.",
    r"\btensorflow\.",
    r"\bsklearn\.",
    r"\bmodel\.(?:fit|predict|forward|eval|train)\s*\(",
    r"```(?:python|py)?",
)

QUERY_CORRECTIONS = {
    "codeing": "coding",
    "programing": "programming",
    "artifical": "artificial",
    "inteligence": "intelligence",
    "intellegence": "intelligence",
    "nural": "neural",
    "nuaral": "neural",
    "machiene": "machine",
}


def _normalize_query(text):
    words = str(text or "").strip().split()
    corrected = []

    for word in words:
        prefix = ""
        suffix = ""
        core = word

        while core and not core[0].isalnum():
            prefix += core[0]
            core = core[1:]

        while core and not core[-1].isalnum():
            suffix = core[-1] + suffix
            core = core[:-1]

        replacement = QUERY_CORRECTIONS.get(
            core.lower(),
            core,
        )

        corrected.append(
            prefix + replacement + suffix
        )

    return " ".join(corrected).strip()


def _tokens(text):
    return TOKEN_RE.findall(
        str(text or "").lower()
    )


def _cosine(a, b):
    aa = Counter(_tokens(a))
    bb = Counter(_tokens(b))

    if not aa or not bb:
        return 0.0

    dot = sum(
        aa[key] * bb[key]
        for key in set(aa) & set(bb)
    )

    mag_a = math.sqrt(
        sum(value * value for value in aa.values())
    )
    mag_b = math.sqrt(
        sum(value * value for value in bb.values())
    )

    if not mag_a or not mag_b:
        return 0.0

    return dot / (mag_a * mag_b)


class Module:
    """
    Apollo persistent compiled-knowledge + The Pile source module.

    Search order:
      1. Hugging Face Dataset Viewer /search
      2. local cached Pile Parquet shards, when present
      3. for explicit LEARN requests with auto_cache=True and only network
         timeouts, download one resumable ~266 MB Lite shard and search locally

    The entire hundreds-of-gigabytes corpus is never downloaded automatically.
    """

    def __init__(self, context=None):
        context = context or {}
        self.base_dir = Path(
            context.get("base_dir", ".")
        ).resolve()
        self.validation = bool(
            context.get("validation", False)
        )

        storage = self.base_dir / "storage"

        if not self.validation:
            storage.mkdir(
                parents=True,
                exist_ok=True,
            )

        self.cache_dir = (
            storage / "cache" / "pile"
        )
        self.cache_catalog_path = (
            self.cache_dir
            / PILE_CATALOG_FILENAME
        )

        if not self.validation:
            self.cache_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

        if self.validation:
            self.db_path = ":memory:"
        else:
            self.db_path = str(
                storage / "databases" / "compiled_knowledge.db"
            )

        self._db_lock = threading.RLock()

        # Remote Pile search health state. When Hugging Face's Dataset Viewer is
        # timing out or returning HTTP 5xx, Apollo temporarily stops hammering it
        # and uses the local Parquet cache instead.
        self._remote_unhealthy_until = 0.0
        self._last_remote_error = ""

        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=15.0,
        )
        self.conn.row_factory = sqlite3.Row

        self.fts_available = False
        self._setup()

    def tools(self):
        return [
            {
                "name": "search_knowledge",
                "description": (
                    "Search Apollo's persistent locally compiled knowledge."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "search_pile",
                "description": (
                    "Search The Pile. Apollo tries Hugging Face online first and "
                    "falls back to any locally cached Pile Parquet shards."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "learn_from_pile",
                "description": (
                    "Search The Pile, reject unrelated passages and compile relevant "
                    "passages into Apollo's persistent knowledge. auto_cache can "
                    "download one Lite shard if every remote request times out."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                        "auto_cache": {"type": "boolean"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "pile_cache_status",
                "description": (
                    "Show how many local Pile Parquet cache shards Apollo has."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "download_pile_cache",
                "description": (
                    "Download/resume local Pile cache shards. One shard is roughly "
                    "233-266 MB. shards=1 is the Lite cache."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "shards": {"type": "integer"},
                    },
                },
            },
            {
                "name": "sync_research_files",
                "description": (
                    "Import Apollo's saved Research & Training files into compiled "
                    "knowledge."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "add_knowledge",
                "description": (
                    "Add trusted text directly into Apollo's compiled knowledge."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                        "source": {"type": "string"},
                        "source_ref": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "knowledge_stats",
                "description": (
                    "Return statistics for Apollo's compiled knowledge database."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def _setup(self):
        with self._db_lock:
            cur = self.conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    source_ref TEXT DEFAULT '',
                    title TEXT DEFAULT '',
                    text TEXT NOT NULL,
                    meta_json TEXT DEFAULT '{}',
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS synced_sources (
                    source_ref TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    synced_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            self.fts_available = True

            try:
                cur.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
                    USING fts5(
                        title,
                        text,
                        source,
                        source_ref,
                        content='knowledge_chunks',
                        content_rowid='id'
                    )
                """)

                cur.executescript("""
                    CREATE TRIGGER IF NOT EXISTS knowledge_ai
                    AFTER INSERT ON knowledge_chunks
                    BEGIN
                        INSERT INTO knowledge_fts(
                            rowid, title, text, source, source_ref
                        )
                        VALUES(
                            new.id, new.title, new.text, new.source, new.source_ref
                        );
                    END;

                    CREATE TRIGGER IF NOT EXISTS knowledge_ad
                    AFTER DELETE ON knowledge_chunks
                    BEGIN
                        INSERT INTO knowledge_fts(
                            knowledge_fts, rowid, title, text, source, source_ref
                        )
                        VALUES(
                            'delete', old.id, old.title, old.text, old.source, old.source_ref
                        );
                    END;
                """)
            except sqlite3.OperationalError:
                self.fts_available = False

            self.conn.commit()

    @staticmethod
    def _limit(value, default=5, maximum=20):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default

        return max(
            1,
            min(value, maximum),
        )

    @staticmethod
    def _hash(text):
        return hashlib.sha256(
            str(text or "").encode(
                "utf-8",
                errors="replace",
            )
        ).hexdigest()

    @staticmethod
    def _chunks(
        text,
        size=2600,
        overlap=300,
    ):
        text = str(text or "").strip()

        if not text:
            return []

        if len(text) <= size:
            return [text]

        output = []
        start = 0

        while start < len(text):
            end = min(
                len(text),
                start + size,
            )

            chunk = text[
                start:end
            ].strip()

            if chunk:
                output.append(chunk)

            if end >= len(text):
                break

            start = max(
                start + 1,
                end - overlap,
            )

        return output

    def _insert_chunk(
        self,
        text,
        source="manual",
        source_ref="",
        title="",
        meta=None,
    ):
        text = str(text or "").strip()

        if not text:
            return None

        digest = self._hash(
            "\n".join([
                str(source),
                str(source_ref),
                str(title),
                text,
            ])
        )

        with self._db_lock:
            cur = self.conn.cursor()

            try:
                cur.execute(
                    """
                    INSERT INTO knowledge_chunks(
                        source,
                        source_ref,
                        title,
                        text,
                        meta_json,
                        content_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(source or "manual"),
                        str(source_ref or ""),
                        str(title or ""),
                        text,
                        json.dumps(
                            meta or {},
                            ensure_ascii=False,
                        ),
                        digest,
                    ),
                )

                self.conn.commit()
                return cur.lastrowid

            except sqlite3.IntegrityError:
                return None

    def add_knowledge(
        self,
        text,
        title="",
        source="manual",
        source_ref="",
        meta=None,
    ):
        chunks = self._chunks(text)
        inserted = 0

        for index, chunk in enumerate(
            chunks
        ):
            chunk_title = str(title or "")

            if len(chunks) > 1:
                chunk_title = (
                    f"{chunk_title} — part {index + 1}"
                    if chunk_title
                    else f"Knowledge part {index + 1}"
                )

            ident = self._insert_chunk(
                chunk,
                source=source,
                source_ref=source_ref,
                title=chunk_title,
                meta=meta,
            )

            if ident is not None:
                inserted += 1

        return {
            "added": inserted,
            "chunks_seen": len(chunks),
            "source": source,
            "source_ref": source_ref,
        }

    def _http_json(
        self,
        url,
        timeout=None,
    ):
        if timeout is None:
            try:
                timeout = int(
                    os.environ.get(
                        "APOLLO_PILE_TIMEOUT",
                        "55",
                    )
                )
            except ValueError:
                timeout = 55

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

        token = (
            os.environ.get("HF_TOKEN")
            or os.environ.get(
                "HUGGINGFACE_TOKEN"
            )
            or ""
        ).strip()

        if token:
            headers[
                "Authorization"
            ] = f"Bearer {token}"

        request = urllib.request.Request(
            url,
            headers=headers,
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout,
        ) as response:
            raw = response.read(
                10_000_000
            )

        return json.loads(
            raw.decode(
                "utf-8",
                errors="replace",
            )
        )

    @staticmethod
    def _extract_row(item):
        row = (
            item.get("row", {})
            if isinstance(item, dict)
            else {}
        )

        text = str(
            row.get("text", "")
            or ""
        )

        meta = row.get(
            "meta",
            {},
        )

        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {
                    "raw": meta
                }

        if not isinstance(meta, dict):
            meta = {
                "raw": str(meta)
            }

        return text, meta

    @staticmethod
    def _best_excerpt(
        text,
        query,
        max_chars=7500,
    ):
        text = str(text or "").strip()

        if len(text) <= max_chars:
            return text

        lower = text.lower()
        positions = []

        for token in _tokens(query):
            if len(token) < 3:
                continue

            pos = lower.find(token)

            if pos >= 0:
                positions.append(pos)

        center = (
            min(positions)
            if positions
            else 0
        )

        start = max(
            0,
            center - max_chars // 4,
        )

        end = min(
            len(text),
            start + max_chars,
        )

        return text[
            start:end
        ].strip()

    @staticmethod
    def _alias_pattern(alias):
        alias = str(alias or "").strip().lower()

        if not alias:
            return None

        escaped = re.escape(alias).replace(
            r"\ ",
            r"\s+",
        )

        return re.compile(
            r"(?<![a-z0-9_])"
            + escaped
            + r"(?![a-z0-9_])",
            re.IGNORECASE,
        )

    @classmethod
    def _contains_any(
        cls,
        text,
        aliases,
    ):
        value = str(text or "")

        return any(
            (
                cls._alias_pattern(alias)
                and cls._alias_pattern(alias).search(value)
            )
            for alias in aliases
        )

    @classmethod
    def _matched_aliases(
        cls,
        text,
        aliases,
    ):
        value = str(text or "")
        output = []

        for alias in aliases:
            pattern = cls._alias_pattern(alias)

            if pattern and pattern.search(value):
                output.append(alias)

        return output

    @staticmethod
    def _markup_quality(text):
        value = str(text or "")
        lower = value.lower()

        signals = [
            signal
            for signal in MARKUP_BOILERPLATE_SIGNALS
            if signal in lower
        ]

        matches = list(
            re.finditer(
                r"<[^>\n]{1,180}>",
                value[:20000],
            )
        )

        tag_count = len(matches)
        markup_chars = sum(
            len(match.group(0))
            for match in matches
        )
        markup_ratio = (
            markup_chars
            / max(1, len(value[:20000]))
        )

        return {
            "reject": (
                len(signals) >= 2
                or (
                    tag_count >= 18
                    and markup_ratio >= 0.08
                )
            ),
            "signals": signals,
            "tag_count": tag_count,
            "markup_ratio": round(markup_ratio, 4),
        }

    def _technical_quality(
        self,
        query,
        text,
        subset,
    ):
        query = str(query or "")
        value = str(text or "")
        lower_query = query.lower()

        markup = self._markup_quality(value)

        if markup["reject"]:
            return {
                "accepted": False,
                "reason": "markup_or_metadata",
                "score_bonus": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(lower_query, {"python"})
            and not self._contains_any(value, {"python"})
        ):
            return {
                "accepted": False,
                "reason": "missing_python",
                "score_bonus": 0.0,
                "signals": [],
            }

        ai_signals = self._matched_aliases(
            value,
            AI_TECHNICAL_SIGNALS,
        )
        engineering_signals = self._matched_aliases(
            value,
            ADVANCED_ENGINEERING_SIGNALS,
        )
        coding_signals = self._matched_aliases(
            value,
            CODING_ALIASES,
        )

        is_advanced = self._contains_any(
            lower_query,
            {"advanced"},
        )

        if is_advanced:
            if not ai_signals:
                return {
                    "accepted": False,
                    "reason": "no_advanced_ai_technical_signal",
                    "score_bonus": 0.0,
                    "signals": [],
                }

            technical_depth = len(
                set(
                    ai_signals
                    + engineering_signals
                )
            )

            if technical_depth < 2:
                return {
                    "accepted": False,
                    "reason": "insufficient_advanced_depth",
                    "score_bonus": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if not coding_signals:
                return {
                    "accepted": False,
                    "reason": "missing_coding_evidence",
                    "score_bonus": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

        else:
            if (
                self._contains_any(lower_query, AI_ALIASES)
                and not ai_signals
            ):
                return {
                    "accepted": False,
                    "reason": "weak_ai_relevance",
                    "score_bonus": 0.0,
                    "signals": [],
                }

            if (
                self._contains_any(lower_query, CODING_ALIASES)
                and not coding_signals
            ):
                return {
                    "accepted": False,
                    "reason": "weak_coding_relevance",
                    "score_bonus": 0.0,
                    "signals": ai_signals,
                }

        career_hits = self._matched_aliases(
            value,
            GENERIC_CAREER_SIGNALS,
        )

        technical_count = len(
            set(
                ai_signals
                + engineering_signals
                + coding_signals
            )
        )

        if (
            career_hits
            and technical_count < 4
        ):
            return {
                "accepted": False,
                "reason": "generic_career_or_course_material",
                "score_bonus": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                ),
            }

        bonus = min(
            0.65,
            (
                len(ai_signals) * 0.10
                + len(engineering_signals) * 0.07
                + min(3, len(coding_signals)) * 0.05
            ),
        )

        if subset in {
            "ArXiv",
            "Github",
            "StackExchange",
        }:
            bonus += 0.05

        return {
            "accepted": True,
            "reason": "accepted",
            "score_bonus": bonus,
            "signals": sorted(
                set(
                    ai_signals
                    + engineering_signals
                    + coding_signals
                )
            )[:20],
        }

    def _concept_requirements(
        self,
        query,
    ):
        lower = str(query).lower()
        requirements = []

        if self._contains_any(
            lower,
            AI_ALIASES,
        ):
            requirements.append(
                (
                    "ai",
                    AI_ALIASES,
                )
            )

        if self._contains_any(
            lower,
            CODING_ALIASES,
        ):
            requirements.append(
                (
                    "coding",
                    CODING_ALIASES,
                )
            )

        return requirements

    def _specific_terms(
        self,
        query,
    ):
        concept_tokens = set()

        for alias in (
            AI_ALIASES
            | CODING_ALIASES
        ):
            concept_tokens.update(
                _tokens(alias)
            )

        return [
            token
            for token in _tokens(query)
            if (
                len(token) >= 3
                and token not in STOPWORDS
                and token not in concept_tokens
            )
        ]

    def _relevance(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")

        if not value.strip():
            return None

        for _, aliases in self._concept_requirements(
            query
        ):
            if not self._contains_any(
                value,
                aliases,
            ):
                return None

        quality = self._technical_quality(
            query,
            value,
            subset,
        )

        if not quality["accepted"]:
            return None

        specific_terms = self._specific_terms(
            query
        )

        hard_specific = [
            token
            for token in specific_terms
            if token not in {
                "advanced",
            }
        ]

        if (
            hard_specific
            and not any(
                self._contains_any(
                    value,
                    {token},
                )
                for token in hard_specific
            )
        ):
            return None

        matched_specific = [
            token
            for token in specific_terms
            if self._contains_any(
                value,
                {token},
            )
        ]

        score = _cosine(
            query,
            value,
        )

        if query.lower() in value.lower():
            score += 0.35

        score += min(
            0.15,
            0.04 * len(matched_specific),
        )

        score += float(
            quality.get(
                "score_bonus",
                0.0,
            )
        )

        return score

    def _relevance_diagnostics(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")

        if not value.strip():
            return {
                "accepted": False,
                "reason": "empty",
                "signals": [],
            }

        missing = []

        for name, aliases in self._concept_requirements(
            query
        ):
            if not self._contains_any(
                value,
                aliases,
            ):
                missing.append(name)

        if missing:
            return {
                "accepted": False,
                "reason": (
                    "missing_"
                    + "_and_".join(missing)
                ),
                "signals": [],
            }

        quality = self._technical_quality(
            query,
            value,
            subset,
        )

        if not quality["accepted"]:
            return quality

        score = self._relevance(
            query,
            value,
            subset,
        )

        return {
            "accepted": score is not None,
            "reason": (
                "accepted"
                if score is not None
                else "low_relevance"
            ),
            "signals": quality.get(
                "signals",
                [],
            ),
            "score": (
                round(float(score), 5)
                if score is not None
                else None
            ),
        }

    def _remote_queries(
        self,
        query,
    ):
        query = _normalize_query(
            query
        )

        lower = query.lower()
        output = [query]

        # One compact fallback only. V1.2 fired three simultaneous expensive
        # full-text searches; when Hugging Face was overloaded all three timed
        # out together.
        if (
            self._contains_any(
                lower,
                AI_ALIASES,
            )
            and self._contains_any(
                lower,
                CODING_ALIASES,
            )
        ):
            output.append(
                "machine learning programming python"
            )

        elif self._contains_any(
            lower,
            AI_ALIASES,
        ):
            output.append(
                "machine learning neural network"
            )

        unique = []
        seen = set()

        for item in output:
            key = item.lower()

            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique[:2]

    def _code_syntax_count(
        self,
        text,
    ):
        value = str(text or "")

        count = 0

        for pattern in CODE_SYNTAX_PATTERNS:
            count += len(
                re.findall(
                    pattern,
                    value,
                    flags=re.IGNORECASE,
                )
            )

        return count

    def _window_candidates(
        self,
        text,
        query,
        window_chars=2800,
    ):
        """
        Produce local document windows around technical terms.

        V1.5 scored an entire source document. A generic career article could
        therefore qualify because technical words appeared somewhere much later
        in the document even though the learned excerpt was fluff.
        """
        value = str(text or "").strip()

        if not value:
            return []

        if len(value) <= window_chars:
            return [value]

        search_terms = sorted(
            (
                AI_TECHNICAL_SIGNALS
                | ADVANCED_ENGINEERING_SIGNALS
                | IMPLEMENTATION_SIGNALS
                | {"python"}
            ),
            key=len,
            reverse=True,
        )

        positions = []

        for term in search_terms:
            pattern = self._alias_pattern(
                term
            )

            if pattern is None:
                continue

            for match in pattern.finditer(
                value
            ):
                positions.append(
                    match.start()
                )

                if len(
                    positions
                ) >= 80:
                    break

            if len(
                positions
            ) >= 80:
                break

        # Include query-word positions as possible centres.
        lower = value.lower()

        for token in _tokens(
            query
        ):
            if len(token) < 4:
                continue

            start = 0

            while True:
                pos = lower.find(
                    token.lower(),
                    start,
                )

                if pos < 0:
                    break

                positions.append(
                    pos
                )

                if len(
                    positions
                ) >= 120:
                    break

                start = pos + len(
                    token
                )

            if len(
                positions
            ) >= 120:
                break

        if not positions:
            positions = [
                0,
                len(value) // 2,
            ]

        windows = []
        seen = set()

        half = (
            window_chars
            // 2
        )

        for position in positions:
            start = max(
                0,
                position - half,
            )

            end = min(
                len(value),
                start + window_chars,
            )

            start = max(
                0,
                end - window_chars,
            )

            window = value[
                start:end
            ].strip()

            if not window:
                continue

            key = self._hash(
                window
            )

            if key in seen:
                continue

            seen.add(key)
            windows.append(
                window
            )

            if len(
                windows
            ) >= 40:
                break

        return windows

    def _technical_window_quality(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")
        lower_query = str(
            query or ""
        ).lower()

        markup = self._markup_quality(
            value
        )

        if markup[
            "reject"
        ]:
            return {
                "accepted": False,
                "reason": (
                    "markup_or_metadata"
                ),
                "score": 0.0,
                "signals": [],
            }

        python_required = self._contains_any(
            lower_query,
            {"python"},
        )

        if (
            python_required
            and not self._contains_any(
                value,
                {"python"},
            )
        ):
            return {
                "accepted": False,
                "reason": "missing_python",
                "score": 0.0,
                "signals": [],
            }

        ai_signals = self._matched_aliases(
            value,
            AI_TECHNICAL_SIGNALS,
        )
        engineering_signals = self._matched_aliases(
            value,
            ADVANCED_ENGINEERING_SIGNALS,
        )
        implementation_signals = self._matched_aliases(
            value,
            IMPLEMENTATION_SIGNALS,
        )
        library_signals = self._matched_aliases(
            value,
            LIBRARY_SIGNALS,
        )
        coding_signals = self._matched_aliases(
            value,
            CODING_ALIASES,
        )
        career_signals = self._matched_aliases(
            value,
            GENERIC_CAREER_SIGNALS,
        )
        syntax_count = self._code_syntax_count(
            value
        )

        is_advanced = self._contains_any(
            lower_query,
            {"advanced"},
        )

        if (
            self._contains_any(
                lower_query,
                AI_ALIASES,
            )
            and not ai_signals
        ):
            return {
                "accepted": False,
                "reason": (
                    "no_advanced_ai_technical_signal"
                    if is_advanced
                    else "weak_ai_relevance"
                ),
                "score": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(
                lower_query,
                CODING_ALIASES,
            )
            and not coding_signals
        ):
            return {
                "accepted": False,
                "reason": (
                    "missing_coding_evidence"
                ),
                "score": 0.0,
                "signals": ai_signals,
            }

        if is_advanced:
            # Career/news framing is not advanced implementation material merely
            # because technical vocabulary is mentioned. Require concrete library
            # or code-syntax evidence in that same local window.
            if (
                career_signals
                and syntax_count == 0
                and len(set(library_signals)) < 2
            ):
                return {
                    "accepted": False,
                    "reason": (
                        "generic_career_or_news_material"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            # Advanced coding needs a dense technical section, not technical
            # vocabulary scattered across a long career/news article.
            if len(
                set(
                    ai_signals
                )
            ) < 2:
                return {
                    "accepted": False,
                    "reason": (
                        "insufficient_ai_depth"
                    ),
                    "score": 0.0,
                    "signals": ai_signals,
                }

            if len(
                set(
                    engineering_signals
                )
            ) < 2:
                return {
                    "accepted": False,
                    "reason": (
                        "insufficient_engineering_depth"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            implementation_strength = (
                len(
                    set(
                        implementation_signals
                    )
                )
                + len(
                    set(
                        library_signals
                    )
                )
                + min(
                    syntax_count,
                    3,
                )
            )

            if implementation_strength < 2:
                return {
                    "accepted": False,
                    "reason": (
                        "insufficient_implementation_evidence"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            # Pile-CC is broad web text. Career/news pieces from it need actual
            # code/library evidence before they can qualify as advanced coding.
            if (
                subset == "Pile-CC"
                and career_signals
                and (
                    syntax_count == 0
                    and len(
                        library_signals
                    ) < 2
                )
            ):
                return {
                    "accepted": False,
                    "reason": (
                        "generic_career_or_news_material"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

        technical_signal_count = len(
            set(
                ai_signals
                + engineering_signals
                + implementation_signals
                + library_signals
            )
        )

        # Generic career/course copy is never useful for advanced coding unless
        # implementation evidence dominates the section.
        if (
            career_signals
            and technical_signal_count < 6
            and syntax_count == 0
        ):
            return {
                "accepted": False,
                "reason": (
                    "generic_career_or_course_material"
                ),
                "score": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                ),
            }

        score = _cosine(
            query,
            value,
        )

        score += min(
            0.55,
            (
                len(
                    set(
                        ai_signals
                    )
                )
                * 0.09
                + len(
                    set(
                        engineering_signals
                    )
                )
                * 0.08
                + len(
                    set(
                        implementation_signals
                    )
                )
                * 0.07
                + len(
                    set(
                        library_signals
                    )
                )
                * 0.06
                + min(
                    syntax_count,
                    4,
                )
                * 0.08
            ),
        )

        if subset in {
            "Github",
            "ArXiv",
            "StackExchange",
        }:
            score += 0.08

        if subset == "Pile-CC":
            score -= 0.06

        return {
            "accepted": True,
            "reason": "accepted",
            "score": round(
                float(score),
                5,
            ),
            "signals": sorted(
                set(
                    ai_signals
                    + engineering_signals
                    + implementation_signals
                    + library_signals
                )
            )[:24],
            "syntax_count": syntax_count,
        }

    def _best_technical_window(
        self,
        text,
        query,
        subset,
        max_chars=2800,
    ):
        windows = self._window_candidates(
            text,
            query,
            window_chars=max_chars,
        )

        best_window = None
        best_quality = None

        rejection_reasons = Counter()

        for window in windows:
            quality = (
                self._technical_window_quality(
                    query,
                    window,
                    subset,
                )
            )

            if not quality.get(
                "accepted"
            ):
                rejection_reasons[
                    quality.get(
                        "reason",
                        "rejected",
                    )
                ] += 1
                continue

            if (
                best_quality is None
                or float(
                    quality.get(
                        "score",
                        0.0,
                    )
                )
                > float(
                    best_quality.get(
                        "score",
                        0.0,
                    )
                )
            ):
                best_window = window
                best_quality = quality

        if best_window is None:
            most_common_reason = (
                rejection_reasons.most_common(
                    1
                )[0][0]
                if rejection_reasons
                else "no_technical_window"
            )

            return {
                "accepted": False,
                "reason": (
                    most_common_reason
                ),
                "window": "",
                "score": None,
                "signals": [],
            }

        return {
            "accepted": True,
            "reason": "accepted",
            "window": best_window,
            "score": best_quality.get(
                "score",
                0.0,
            ),
            "signals": best_quality.get(
                "signals",
                [],
            ),
            "syntax_count": best_quality.get(
                "syntax_count",
                0,
            ),
        }

    def _best_excerpt(
        self,
        text,
        query,
        max_chars=7500,
    ):
        # Generic callers that do not supply a subset still get a query-centred
        # excerpt. Pile result ranking replaces this with the accepted technical
        # window before storage.
        value = str(text or "").strip()

        if len(value) <= max_chars:
            return value

        lower = value.lower()
        positions = []

        for token in _tokens(
            query
        ):
            if len(token) < 3:
                continue

            pos = lower.find(
                token
            )

            if pos >= 0:
                positions.append(
                    pos
                )

        center = (
            min(positions)
            if positions
            else 0
        )

        start = max(
            0,
            center - max_chars // 3,
        )
        end = min(
            len(value),
            start + max_chars,
        )

        return value[
            start:end
        ].strip()

    def _relevance_diagnostics(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")

        if not value.strip():
            return {
                "accepted": False,
                "reason": "empty",
                "signals": [],
            }

        # Broad topic gate first.
        missing = []

        for name, aliases in (
            self._concept_requirements(
                query
            )
        ):
            if not self._contains_any(
                value,
                aliases,
            ):
                missing.append(
                    name
                )

        if missing:
            return {
                "accepted": False,
                "reason": (
                    "missing_"
                    + "_and_".join(
                        missing
                    )
                ),
                "signals": [],
            }

        technical = (
            self._best_technical_window(
                value,
                query,
                subset,
                max_chars=2800,
            )
        )

        if not technical.get(
            "accepted"
        ):
            return {
                "accepted": False,
                "reason": technical.get(
                    "reason",
                    "no_technical_window",
                ),
                "signals": technical.get(
                    "signals",
                    [],
                ),
            }

        return {
            "accepted": True,
            "reason": "accepted",
            "signals": technical.get(
                "signals",
                [],
            ),
            "score": technical.get(
                "score",
                0.0,
            ),
            "window": technical.get(
                "window",
                "",
            ),
            "syntax_count": technical.get(
                "syntax_count",
                0,
            ),
        }

    def _relevance(
        self,
        query,
        text,
        subset,
    ):
        diagnostics = (
            self._relevance_diagnostics(
                query,
                text,
                subset,
            )
        )

        if not diagnostics.get(
            "accepted"
        ):
            return None

        return float(
            diagnostics.get(
                "score",
                0.0,
            )
            or 0.0
        )

    def _remote_queries(
        self,
        query,
    ):
        query = _normalize_query(
            query
        )

        lower = query.lower()
        output = [query]

        if (
            self._contains_any(
                lower,
                AI_ALIASES,
            )
            and self._contains_any(
                lower,
                CODING_ALIASES,
            )
        ):
            if self._contains_any(
                lower,
                {"python"},
            ):
                output.extend([
                    (
                        "python pytorch machine learning "
                        "model training implementation"
                    ),
                    (
                        "python transformer neural network "
                        "inference evaluation debugging"
                    ),
                ])
            else:
                output.extend([
                    (
                        "machine learning model training "
                        "implementation software"
                    ),
                    (
                        "transformer neural network "
                        "inference evaluation code"
                    ),
                ])

        elif self._contains_any(
            lower,
            AI_ALIASES,
        ):
            output.extend([
                (
                    "machine learning neural network "
                    "training inference"
                ),
            ])

        unique = []
        seen = set()

        for item in output:
            key = item.lower()

            if key in seen:
                continue

            seen.add(key)
            unique.append(
                item
            )

        return unique[:3]

    @staticmethod
    def _english_readability_ratio(
        text,
    ):
        """
        Rough language/usability heuristic, not language identification.

        For an English query, a result dominated by non-ASCII alphabetic text
        is less useful to Apollo unless it contains substantial executable code.
        """
        value = str(text or "")

        letters = [
            char
            for char in value
            if char.isalpha()
        ]

        if not letters:
            return 1.0

        latin_ascii = sum(
            1
            for char in letters
            if (
                "a" <= char.lower() <= "z"
            )
        )

        return (
            latin_ascii
            / len(letters)
        )

    @staticmethod
    def _strip_front_matter(
        text,
    ):
        value = str(text or "").strip()

        if not value:
            return value

        lines = value.splitlines()

        # ArXiv/Markdown sources can begin with YAML metadata. It is source
        # metadata, not knowledge, so remove it from the learned technical
        # section when a closing delimiter exists.
        if (
            lines
            and lines[0].strip()
            == "---"
        ):
            for index in range(
                1,
                min(
                    len(lines),
                    120,
                ),
            ):
                if (
                    lines[index].strip()
                    == "---"
                ):
                    value = "\n".join(
                        lines[
                            index + 1:
                        ]
                    ).strip()
                    break

        return value

    def _technical_window_quality(
        self,
        query,
        text,
        subset,
    ):
        query = str(query or "")
        value = self._strip_front_matter(
            text
        )
        lower_query = query.lower()

        markup = self._markup_quality(
            value
        )

        if markup["reject"]:
            return {
                "accepted": False,
                "reason": "markup_or_metadata",
                "score": 0.0,
                "signals": [],
            }

        python_required = (
            self._contains_any(
                lower_query,
                {"python"},
            )
        )

        if (
            python_required
            and not self._contains_any(
                value,
                {"python"},
            )
        ):
            return {
                "accepted": False,
                "reason": "missing_python",
                "score": 0.0,
                "signals": [],
            }

        ai_signals = (
            self._matched_aliases(
                value,
                AI_TECHNICAL_SIGNALS,
            )
        )
        engineering_signals = (
            self._matched_aliases(
                value,
                ADVANCED_ENGINEERING_SIGNALS,
            )
        )
        implementation_signals = (
            self._matched_aliases(
                value,
                IMPLEMENTATION_SIGNALS,
            )
        )
        library_signals = (
            self._matched_aliases(
                value,
                LIBRARY_SIGNALS,
            )
        )
        coding_signals = (
            self._matched_aliases(
                value,
                CODING_ALIASES,
            )
        )
        career_signals = (
            self._matched_aliases(
                value,
                GENERIC_CAREER_SIGNALS,
            )
        )
        novice_signals = (
            self._matched_aliases(
                value,
                NOVICE_SIGNALS,
            )
        )
        syntax_count = (
            self._code_syntax_count(
                value
            )
        )

        is_advanced = (
            self._contains_any(
                lower_query,
                {"advanced"},
            )
        )

        if (
            self._contains_any(
                lower_query,
                AI_ALIASES,
            )
            and not ai_signals
        ):
            return {
                "accepted": False,
                "reason": (
                    "no_advanced_ai_technical_signal"
                    if is_advanced
                    else "weak_ai_relevance"
                ),
                "score": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(
                lower_query,
                CODING_ALIASES,
            )
            and not coding_signals
        ):
            return {
                "accepted": False,
                "reason": "missing_coding_evidence",
                "score": 0.0,
                "signals": ai_signals,
            }

        unique_ai = set(
            ai_signals
        )
        unique_engineering = set(
            engineering_signals
        )
        unique_implementation = set(
            implementation_signals
        )
        unique_libraries = set(
            library_signals
        )

        implementation_strength = (
            len(
                unique_implementation
            )
            + len(
                unique_libraries
            )
            + min(
                syntax_count,
                3,
            )
        )

        if is_advanced:
            # Explicit novice questions are useful learning exercises, but they
            # are not source material for an "advanced" knowledge request unless
            # the surrounding accepted section itself contains strong code and
            # implementation evidence.
            if (
                novice_signals
                and (
                    implementation_strength < 5
                    or syntax_count < 2
                )
            ):
                return {
                    "accepted": False,
                    "reason": "novice_material",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if len(
                unique_ai
            ) < 2:
                return {
                    "accepted": False,
                    "reason": "insufficient_ai_depth",
                    "score": 0.0,
                    "signals": ai_signals,
                }

            if len(
                unique_engineering
            ) < 2:
                return {
                    "accepted": False,
                    "reason": "insufficient_engineering_depth",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if (
                implementation_strength
                < 2
            ):
                return {
                    "accepted": False,
                    "reason": "insufficient_implementation_evidence",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if (
                subset == "Pile-CC"
                and career_signals
                and (
                    syntax_count == 0
                    and len(
                        unique_libraries
                    ) < 2
                )
            ):
                return {
                    "accepted": False,
                    "reason": "generic_career_or_news_material",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

        technical_count = len(
            unique_ai
            | unique_engineering
            | unique_implementation
            | unique_libraries
        )

        if (
            career_signals
            and technical_count < 6
            and syntax_count == 0
        ):
            return {
                "accepted": False,
                "reason": "generic_career_or_course_material",
                "score": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                ),
            }

        # Apollo's normal interaction language is English. For a generic English
        # learning request, avoid banking a documentation section dominated by a
        # different natural language unless executable-code evidence is strong.
        english_ratio = (
            self._english_readability_ratio(
                value
            )
        )

        if (
            is_advanced
            and english_ratio < 0.58
            and (
                syntax_count < 3
                or implementation_strength < 5
            )
        ):
            return {
                "accepted": False,
                "reason": "non_english_dominant",
                "score": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                    + implementation_signals
                ),
            }

        score = _cosine(
            query,
            value,
        )

        score += min(
            0.65,
            (
                len(
                    unique_ai
                )
                * 0.09
                + len(
                    unique_engineering
                )
                * 0.08
                + len(
                    unique_implementation
                )
                * 0.08
                + len(
                    unique_libraries
                )
                * 0.07
                + min(
                    syntax_count,
                    4,
                )
                * 0.09
            ),
        )

        # Advanced-source preference.
        if subset == "Github":
            score += 0.12
        elif subset == "ArXiv":
            score += 0.10
        elif subset == "StackExchange":
            score += 0.04
        elif subset == "Pile-CC":
            score -= 0.10

        if novice_signals:
            score -= 0.20

        return {
            "accepted": True,
            "reason": "accepted",
            "score": round(
                float(score),
                5,
            ),
            "signals": sorted(
                set(
                    ai_signals
                    + engineering_signals
                    + implementation_signals
                    + library_signals
                )
            )[:24],
            "syntax_count": syntax_count,
            "english_ratio": round(
                english_ratio,
                4,
            ),
        }

    def _best_technical_window(
        self,
        text,
        query,
        subset,
        max_chars=2600,
    ):
        windows = self._window_candidates(
            text,
            query,
            window_chars=max_chars,
        )

        best_window = None
        best_quality = None
        rejection_reasons = Counter()

        for raw_window in windows:
            window = (
                self._strip_front_matter(
                    raw_window
                )
            )

            quality = (
                self._technical_window_quality(
                    query,
                    window,
                    subset,
                )
            )

            if not quality.get(
                "accepted"
            ):
                rejection_reasons[
                    quality.get(
                        "reason",
                        "rejected",
                    )
                ] += 1
                continue

            if (
                best_quality is None
                or float(
                    quality.get(
                        "score",
                        0.0,
                    )
                )
                > float(
                    best_quality.get(
                        "score",
                        0.0,
                    )
                )
            ):
                best_window = window
                best_quality = quality

        if best_window is None:
            most_common_reason = (
                rejection_reasons.most_common(
                    1
                )[0][0]
                if rejection_reasons
                else "no_technical_window"
            )

            return {
                "accepted": False,
                "reason": most_common_reason,
                "window": "",
                "score": None,
                "signals": [],
            }

        # Keep one curated section small enough to persist as a single knowledge
        # chunk. This prevents six accepted documents becoming twenty overlapping
        # chunks in the local-cache path.
        best_window = str(
            best_window
        ).strip()[
            :2600
        ]

        return {
            "accepted": True,
            "reason": "accepted",
            "window": best_window,
            "score": best_quality.get(
                "score",
                0.0,
            ),
            "signals": best_quality.get(
                "signals",
                [],
            ),
            "syntax_count": best_quality.get(
                "syntax_count",
                0,
            ),
        }

    def _local_sql_predicates(
        self,
        query,
    ):
        lower = str(
            query or ""
        ).lower()
        predicates = []

        if self._contains_any(
            lower,
            AI_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'machine learning') OR "
                "contains(lower(text), 'deep learning') OR "
                "contains(lower(text), 'neural network') OR "
                "contains(lower(text), 'transformer') OR "
                "contains(lower(text), 'language model') OR "
                "contains(lower(text), 'pytorch') OR "
                "contains(lower(text), 'tensorflow') OR "
                "contains(lower(text), 'scikit-learn')"
                ")"
            )

        if self._contains_any(
            lower,
            CODING_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'programming') OR "
                "contains(lower(text), 'python') OR "
                "contains(lower(text), 'implementation') OR "
                "contains(lower(text), 'debugging') OR "
                "contains(lower(text), 'source code') OR "
                "contains(lower(text), 'api')"
                ")"
            )

        # Explicit language constraints should be applied in DuckDB rather than
        # wasting candidate slots that the Python quality gate will later reject.
        if self._contains_any(
            lower,
            {"python"},
        ):
            predicates.append(
                "contains(lower(text), 'python')"
            )

        if self._contains_any(
            lower,
            {"advanced"},
        ):
            predicates.append(
                "("
                "contains(lower(text), 'pytorch') OR "
                "contains(lower(text), 'tensorflow') OR "
                "contains(lower(text), 'scikit-learn') OR "
                "contains(lower(text), 'training loop') OR "
                "contains(lower(text), 'inference') OR "
                "contains(lower(text), 'evaluation') OR "
                "contains(lower(text), 'optimizer') OR "
                "contains(lower(text), 'loss function') OR "
                "contains(lower(text), 'embedding') OR "
                "contains(lower(text), 'attention') OR "
                "contains(lower(text), 'debugging') OR "
                "contains(lower(text), 'data pipeline') OR "
                "contains(lower(text), 'architecture') OR "
                "contains(lower(text), 'gpu') OR "
                "contains(lower(text), 'cuda')"
                ")"
            )

        return predicates

    def _search_remote_variant(
        self,
        query,
        length=12,
    ):
        params = urllib.parse.urlencode({
            "dataset": PILE_DATASET,
            "config": "default",
            "split": "train",
            "query": query,
            "offset": 0,
            "length": length,
        })

        return self._http_json(
            HF_API
            + "/search?"
            + params,
        )

    def _rank_remote_rows(
        self,
        query,
        packets,
        limit,
    ):
        ranked = []
        seen = set()
        rejected = 0
        rejection_reasons = Counter()
        partial = False

        for variant, packet in packets:
            partial = (
                partial
                or bool(
                    packet.get(
                        "partial",
                        False,
                    )
                )
            )

            for item in packet.get(
                "rows",
                [],
            ):
                text, meta = (
                    self._extract_row(
                        item
                    )
                )

                if not text:
                    continue

                subset = str(
                    meta.get(
                        "pile_set_name",
                        "",
                    )
                    or "The Pile"
                )

                diagnostics = (
                    self._relevance_diagnostics(
                        query,
                        text,
                        subset,
                    )
                )

                if not diagnostics.get(
                    "accepted"
                ):
                    rejected += 1
                    rejection_reasons[
                        diagnostics.get(
                            "reason",
                            "rejected",
                        )
                    ] += 1
                    continue

                relevance = float(
                    diagnostics.get(
                        "score",
                        0.0,
                    )
                    or 0.0
                )

                excerpt = str(
                    diagnostics.get(
                        "window",
                        "",
                    )
                    or self._best_excerpt(
                        text,
                        query,
                        max_chars=2800,
                    )
                ).strip()

                digest = self._hash(
                    excerpt
                )

                if digest in seen:
                    continue

                seen.add(digest)

                ranked.append(
                    (
                        relevance,
                        {
                            "dataset": (
                                PILE_DATASET
                            ),
                            "dataset_label": (
                                "The Pile "
                                f"({subset})"
                            ),
                            "config": "default",
                            "split": "train",
                            "row_idx": (
                                item.get(
                                    "row_idx"
                                )
                            ),
                            "pile_set_name": (
                                subset
                            ),
                            "text": excerpt,
                            "characters": (
                                len(text)
                            ),
                            "meta": meta,
                            "matched_query_variant": (
                                variant
                            ),
                            "relevance": round(
                                float(
                                    relevance
                                ),
                                5,
                            ),
                            "access_method": (
                                "huggingface_search"
                            ),
                            "quality_signals": (
                                diagnostics.get(
                                    "signals",
                                    [],
                                )
                            ),
                        },
                    )
                )

        ranked.sort(
            key=lambda entry: entry[0],
            reverse=True,
        )

        return (
            [
                item
                for _, item
                in ranked[:limit]
            ],
            rejected,
            partial,
            dict(rejection_reasons),
        )

    def _remote_search(
        self,
        query,
        limit,
    ):
        variants = self._remote_queries(
            query
        )

        packets = []
        errors = []

        # Sequential by design. The remote service is the bottleneck; launching
        # several heavyweight searches at it simultaneously just multiplied the
        # timeout failure.
        for variant in variants:
            try:
                packet = (
                    self._search_remote_variant(
                        variant,
                        length=max(
                            8,
                            min(
                                20,
                                limit * 2,
                            ),
                        ),
                    )
                )
                packets.append(
                    (
                        variant,
                        packet,
                    )
                )

                results, rejected, partial, rejection_reasons = (
                    self._rank_remote_rows(
                        query,
                        packets,
                        limit,
                    )
                )

                if len(
                    results
                ) >= min(
                    3,
                    limit,
                ):
                    return {
                        "results": results,
                        "errors": errors,
                        "rejected": rejected,
                        "rejection_reasons": (
                            rejection_reasons
                        ),
                        "partial": partial,
                        "variants": variants,
                    }

            except Exception as exc:
                error_text = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                errors.append({
                    "query_variant": variant,
                    "error": error_text,
                })

                if self._is_remote_service_error_text(
                    error_text
                ):
                    self._mark_remote_unhealthy(
                        error_text,
                        seconds=900,
                    )
                    break

        results, rejected, partial, rejection_reasons = (
            self._rank_remote_rows(
                query,
                packets,
                limit,
            )
        )

        return {
            "results": results,
            "errors": errors,
            "rejected": rejected,
            "rejection_reasons": (
                rejection_reasons
            ),
            "partial": partial,
            "variants": variants,
        }

    def _cache_files(self):
        if not self.cache_dir.exists():
            return []

        output = []

        for path in sorted(
            self.cache_dir.glob(
                "*.parquet"
            )
        ):
            if not path.is_file():
                continue

            output.append(
                (
                    path,
                    path.stat().st_size,
                )
            )

        return output

    def _read_cached_catalog(self):
        if (
            not self.cache_catalog_path.exists()
            or self.validation
        ):
            return None

        try:
            data = json.loads(
                self.cache_catalog_path.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(
                data,
                dict,
            ):
                return None

            entries = data.get(
                "entries",
                [],
            )

            if not isinstance(
                entries,
                list,
            ):
                return None

            return data

        except Exception:
            return None

    def _write_cached_catalog(
        self,
        entries,
        source,
    ):
        if self.validation:
            return

        payload = {
            "dataset": PILE_DATASET,
            "source": source,
            "discovered_at_epoch": (
                time.time()
            ),
            "entries": entries,
        }

        temp = self.cache_catalog_path.with_suffix(
            ".json.tmp"
        )

        temp.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        temp.replace(
            self.cache_catalog_path
        )

    @staticmethod
    def _normalise_parquet_entry(
        url,
        filename="",
        size=0,
        config="",
        split="",
    ):
        url = str(
            url or ""
        ).strip()

        if not url:
            return None

        if ".parquet" not in url.lower():
            return None

        parsed = urllib.parse.urlparse(
            url
        )

        detected_name = (
            Path(
                urllib.parse.unquote(
                    parsed.path
                )
            ).name
            or str(
                filename
                or ""
            ).strip()
            or "pile.parquet"
        )

        try:
            size = int(
                size
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            size = 0

        return {
            "url": url,
            "filename": detected_name,
            "size": max(
                0,
                size,
            ),
            "config": str(
                config or ""
            ),
            "split": str(
                split or ""
            ),
        }

    def _extract_parquet_entries(
        self,
        data,
    ):
        """
        Parse both Dataset Viewer /parquet responses and Hub API parquet
        responses defensively.

        Hugging Face has changed response wrappers over time, so this walks the
        JSON and accepts any real .parquet URL while preserving config/split
        context when available.
        """
        entries = []

        def walk(
            node,
            context=None,
        ):
            context = dict(
                context or {}
            )

            if isinstance(
                node,
                dict,
            ):
                local = dict(
                    context
                )

                for key in (
                    "config",
                    "subset",
                ):
                    if key in node:
                        local[
                            "config"
                        ] = str(
                            node.get(
                                key
                            )
                            or ""
                        )

                if "split" in node:
                    local[
                        "split"
                    ] = str(
                        node.get(
                            "split"
                        )
                        or ""
                    )

                url = node.get(
                    "url"
                )

                if isinstance(
                    url,
                    str,
                ):
                    entry = (
                        self._normalise_parquet_entry(
                            url=url,
                            filename=node.get(
                                "filename",
                                "",
                            ),
                            size=node.get(
                                "size",
                                0,
                            ),
                            config=local.get(
                                "config",
                                "",
                            ),
                            split=local.get(
                                "split",
                                "",
                            ),
                        )
                    )

                    if entry is not None:
                        entries.append(
                            entry
                        )

                for key, value in node.items():
                    child_context = dict(
                        local
                    )

                    # Hub API responses can be nested:
                    # {config: {split: [url, ...]}}
                    if (
                        isinstance(
                            value,
                            (
                                dict,
                                list,
                                tuple,
                            ),
                        )
                    ):
                        if (
                            not child_context.get(
                                "config"
                            )
                            and isinstance(
                                key,
                                str,
                            )
                            and key
                            not in {
                                "parquet_files",
                                "pending",
                                "failed",
                                "entries",
                            }
                        ):
                            child_context[
                                "config"
                            ] = key

                        elif (
                            child_context.get(
                                "config"
                            )
                            and not child_context.get(
                                "split"
                            )
                            and isinstance(
                                key,
                                str,
                            )
                            and key
                            not in {
                                "parquet_files",
                                "pending",
                                "failed",
                                "entries",
                            }
                        ):
                            child_context[
                                "split"
                            ] = key

                        walk(
                            value,
                            child_context,
                        )

            elif isinstance(
                node,
                (
                    list,
                    tuple,
                ),
            ):
                for item in node:
                    walk(
                        item,
                        context,
                    )

            elif isinstance(
                node,
                str,
            ):
                entry = (
                    self._normalise_parquet_entry(
                        url=node,
                        config=context.get(
                            "config",
                            "",
                        ),
                        split=context.get(
                            "split",
                            "",
                        ),
                    )
                )

                if entry is not None:
                    entries.append(
                        entry
                    )

        walk(
            data,
            {},
        )

        # Dataset Viewer standard wrapper.
        if (
            isinstance(
                data,
                dict,
            )
            and isinstance(
                data.get(
                    "parquet_files"
                ),
                list,
            )
        ):
            for item in data[
                "parquet_files"
            ]:
                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                entry = (
                    self._normalise_parquet_entry(
                        url=item.get(
                            "url"
                        ),
                        filename=item.get(
                            "filename",
                            "",
                        ),
                        size=item.get(
                            "size",
                            0,
                        ),
                        config=item.get(
                            "config",
                            "",
                        ),
                        split=item.get(
                            "split",
                            "",
                        ),
                    )
                )

                if entry is not None:
                    entries.append(
                        entry
                    )

        unique = []
        seen = set()

        for entry in entries:
            url = entry[
                "url"
            ]

            if url in seen:
                continue

            seen.add(
                url
            )
            unique.append(
                entry
            )

        return unique

    @staticmethod
    def _parquet_sort_key(
        entry,
    ):
        split = str(
            entry.get(
                "split",
                "",
            )
        ).lower()
        config = str(
            entry.get(
                "config",
                "",
            )
        ).lower()
        filename = str(
            entry.get(
                "filename",
                "",
            )
        ).lower()

        if split == "partial-train":
            split_rank = 0
        elif "train" in split:
            split_rank = 1
        else:
            split_rank = 2

        config_rank = (
            0
            if config in {
                "",
                "default",
            }
            else 1
        )

        return (
            split_rank,
            config_rank,
            filename,
            entry.get(
                "url",
                "",
            ),
        )

    def _discover_parquet_shards(
        self,
        force=False,
    ):
        cached = (
            self._read_cached_catalog()
        )

        if (
            cached
            and not force
        ):
            discovered_at = float(
                cached.get(
                    "discovered_at_epoch",
                    0,
                )
                or 0
            )

            if (
                time.time()
                - discovered_at
                < PILE_CATALOG_TTL_SECONDS
            ):
                entries = cached.get(
                    "entries",
                    [],
                )

                if entries:
                    return {
                        "entries": entries,
                        "source": (
                            "cached_catalog"
                        ),
                        "errors": [],
                    }

        errors = []

        # Preferred source: Dataset Viewer documented /parquet endpoint.
        try:
            data = self._http_json(
                HF_PARQUET_API,
                timeout=35,
            )

            entries = (
                self._extract_parquet_entries(
                    data
                )
            )

            if entries:
                entries.sort(
                    key=self._parquet_sort_key
                )

                self._write_cached_catalog(
                    entries,
                    "datasets_server_parquet",
                )

                return {
                    "entries": entries,
                    "source": (
                        "datasets_server_parquet"
                    ),
                    "errors": errors,
                }

            errors.append({
                "provider": (
                    "datasets_server_parquet"
                ),
                "error": (
                    "No Parquet URLs were returned."
                ),
            })

        except Exception as exc:
            errors.append({
                "provider": (
                    "datasets_server_parquet"
                ),
                "error": (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            })

        # Secondary source: Hub API parquet listing. The hf CLI uses this API.
        try:
            data = self._http_json(
                HF_HUB_PARQUET_API,
                timeout=35,
            )

            entries = (
                self._extract_parquet_entries(
                    data
                )
            )

            if entries:
                entries.sort(
                    key=self._parquet_sort_key
                )

                self._write_cached_catalog(
                    entries,
                    "hub_api_parquet",
                )

                return {
                    "entries": entries,
                    "source": (
                        "hub_api_parquet"
                    ),
                    "errors": errors,
                }

            errors.append({
                "provider": (
                    "hub_api_parquet"
                ),
                "error": (
                    "No Parquet URLs were returned."
                ),
            })

        except Exception as exc:
            errors.append({
                "provider": (
                    "hub_api_parquet"
                ),
                "error": (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            })

        # A still-valid cached catalog is better than nothing even when it is
        # older than the normal TTL.
        if cached:
            entries = cached.get(
                "entries",
                [],
            )

            if entries:
                return {
                    "entries": entries,
                    "source": (
                        "stale_cached_catalog"
                    ),
                    "errors": errors,
                }

        return {
            "entries": [],
            "source": "none",
            "errors": errors,
        }

    def pile_cache_status(self):
        files = self._cache_files()

        bytes_on_disk = sum(
            path.stat().st_size
            for path, _
            in files
        )

        part_files = (
            list(
                self.cache_dir.glob(
                    "*.part"
                )
            )
            if self.cache_dir.exists()
            else []
        )

        catalog = (
            self._read_cached_catalog()
            or {}
        )

        catalog_entries = (
            catalog.get(
                "entries",
                []
            )
            if isinstance(
                catalog,
                dict,
            )
            else []
        )

        return {
            "shards_cached": len(
                files
            ),
            "discovered_shards": len(
                catalog_entries
            ),
            "bytes_on_disk": (
                bytes_on_disk
            ),
            "megabytes_on_disk": round(
                bytes_on_disk
                / (
                    1024
                    * 1024
                ),
                1,
            ),
            "incomplete_downloads": [
                path.name
                for path in part_files
            ],
            "cache_dir": str(
                self.cache_dir
            ),
            "catalog_file": str(
                self.cache_catalog_path
            ),
            "catalog_source": (
                catalog.get(
                    "source",
                    ""
                )
                if isinstance(
                    catalog,
                    dict,
                )
                else ""
            ),
            "duckdb_available": (
                self._duckdb_available()
            ),
            "remote_health": (
                self._remote_health_status()
            ),
        }

    @staticmethod
    def _duckdb_available():
        try:
            import duckdb  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _duckdb():
        try:
            import duckdb
            return duckdb
        except Exception as exc:
            raise RuntimeError(
                "Local Pile cache search requires DuckDB. "
                "Run Apollo's install.bat once after updating "
                "so requirements.txt installs duckdb."
            ) from exc

    def _download_one_shard(
        self,
        shard,
        local_index=0,
    ):
        self.cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not isinstance(
            shard,
            dict,
        ):
            raise TypeError(
                "Parquet shard metadata must be a dictionary."
            )

        url = str(
            shard.get(
                "url",
                "",
            )
        ).strip()

        if not url:
            raise ValueError(
                "Parquet shard URL is empty."
            )

        remote_filename = str(
            shard.get(
                "filename",
                "",
            )
        ).strip()

        remote_suffix = (
            Path(
                remote_filename
            ).suffix.lower()
            if remote_filename
            else ".parquet"
        )

        if remote_suffix != ".parquet":
            remote_suffix = ".parquet"

        name = (
            f"{int(local_index):04d}"
            f"{remote_suffix}"
        )

        final_path = (
            self.cache_dir
            / name
        )
        part_path = (
            self.cache_dir
            / (
                name
                + ".part"
            )
        )

        try:
            expected_size = int(
                shard.get(
                    "size",
                    0,
                )
                or 0
            )
        except (
            TypeError,
            ValueError,
        ):
            expected_size = 0

        if (
            final_path.exists()
            and final_path.stat().st_size
            >= (
                max(
                    1_000_000,
                    int(
                        expected_size
                        * 0.90
                    ),
                )
                if expected_size > 0
                else 1_000_000
            )
        ):
            return {
                "file": str(
                    final_path
                ),
                "source_url": url,
                "downloaded": False,
                "resumed": False,
                "bytes": (
                    final_path
                    .stat()
                    .st_size
                ),
            }

        resume_from = (
            part_path.stat().st_size
            if part_path.exists()
            else 0
        )

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/octet-stream"
            ),
        }

        token = (
            os.environ.get(
                "HF_TOKEN"
            )
            or os.environ.get(
                "HUGGINGFACE_TOKEN"
            )
            or ""
        ).strip()

        if token:
            headers[
                "Authorization"
            ] = (
                f"Bearer {token}"
            )

        if resume_from > 0:
            headers[
                "Range"
            ] = (
                f"bytes={resume_from}-"
            )

        request = (
            urllib.request.Request(
                url,
                headers=headers,
            )
        )

        with urllib.request.urlopen(
            request,
            timeout=90,
        ) as response:
            status = getattr(
                response,
                "status",
                200,
            )

            append = (
                resume_from > 0
                and status == 206
            )

            mode = (
                "ab"
                if append
                else "wb"
            )

            with part_path.open(
                mode
            ) as handle:
                while True:
                    chunk = response.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    handle.write(
                        chunk
                    )

        size = (
            part_path
            .stat()
            .st_size
        )

        if size < 1_000_000:
            raise RuntimeError(
                "Downloaded Pile shard is unexpectedly small: "
                f"{size} bytes."
            )

        part_path.replace(
            final_path
        )

        return {
            "file": str(
                final_path
            ),
            "source_url": url,
            "downloaded": True,
            "resumed": bool(
                resume_from
            ),
            "bytes": size,
        }

    def download_pile_cache(
        self,
        shards=1,
    ):
        if self.validation:
            return {
                "downloaded": 0,
                "validation": True,
            }

        try:
            shards = int(
                shards
            )
        except (
            TypeError,
            ValueError,
        ):
            shards = 1

        shards = max(
            1,
            shards,
        )

        discovery = (
            self._discover_parquet_shards(
                force=False,
            )
        )

        entries = discovery.get(
            "entries",
            [],
        )

        if not entries:
            raise RuntimeError(
                "Apollo could not discover any current Pile Parquet shards. "
                + json.dumps(
                    discovery.get(
                        "errors",
                        [],
                    ),
                    ensure_ascii=False,
                )
            )

        shards = min(
            shards,
            len(
                entries
            ),
        )

        results = []

        for index, shard in enumerate(
            entries[:shards]
        ):
            try:
                result = (
                    self._download_one_shard(
                        shard,
                        local_index=index,
                    )
                )

            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise

                # Generated Parquet URLs are not stable contracts. Rediscover the
                # catalog once and retry the same logical shard.
                refreshed = (
                    self._discover_parquet_shards(
                        force=True,
                    )
                )

                refreshed_entries = (
                    refreshed.get(
                        "entries",
                        [],
                    )
                )

                if (
                    index
                    >= len(
                        refreshed_entries
                    )
                ):
                    raise RuntimeError(
                        "Pile Parquet link returned 404 and rediscovery did not "
                        "return a replacement shard."
                    ) from exc

                result = (
                    self._download_one_shard(
                        refreshed_entries[
                            index
                        ],
                        local_index=index,
                    )
                )

                result[
                    "rediscovered_after_404"
                ] = True

                discovery = refreshed
                entries = (
                    refreshed_entries
                )

            results.append(
                result
            )

        status = (
            self.pile_cache_status()
        )

        return {
            "requested_shards": (
                shards
            ),
            "catalog_source": (
                discovery.get(
                    "source"
                )
            ),
            "catalog_errors": (
                discovery.get(
                    "errors",
                    [],
                )
            ),
            "files": results,
            "cache": status,
        }

    @staticmethod
    def _sql_quote_path(path):
        return str(path).replace(
            "'",
            "''",
        )

    def _local_sql_predicates(
        self,
        query,
    ):
        lower = query.lower()
        predicates = []

        if self._contains_any(
            lower,
            AI_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'machine learning') OR "
                "contains(lower(text), 'artificial intelligence') OR "
                "contains(lower(text), 'deep learning') OR "
                "contains(lower(text), 'neural') OR "
                "contains(lower(text), 'transformer') OR "
                "contains(lower(text), 'language model') OR "
                "contains(lower(text), ' llm')"
                ")"
            )

        if self._contains_any(
            lower,
            CODING_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'programming') OR "
                "contains(lower(text), 'python') OR "
                "contains(lower(text), 'software') OR "
                "contains(lower(text), ' code') OR "
                "contains(lower(text), 'developer') OR "
                "contains(lower(text), 'debug') OR "
                "contains(lower(text), 'algorithm') OR "
                "contains(lower(text), 'implementation')"
                ")"
            )

        hard_specific = [
            token
            for token in (
                self._specific_terms(
                    query
                )
            )
            if token not in {
                "advanced",
            }
        ]

        if hard_specific:
            term_sql = " OR ".join(
                (
                    "contains(lower(text), '"
                    + token.replace(
                        "'",
                        "''",
                    )
                    + "')"
                )
                for token
                in hard_specific[:5]
            )

            predicates.append(
                "(" + term_sql + ")"
            )

        if not predicates:
            useful = [
                token
                for token in _tokens(
                    query
                )
                if (
                    len(token) >= 3
                    and token
                    not in STOPWORDS
                )
            ]

            if useful:
                predicates.append(
                    "("
                    + " OR ".join(
                        (
                            "contains(lower(text), '"
                            + token.replace(
                                "'",
                                "''",
                            )
                            + "')"
                        )
                        for token
                        in useful[:6]
                    )
                    + ")"
                )

        return predicates

    def _search_local_cache(
        self,
        query,
        limit,
    ):
        files = [
            path
            for path, _
            in self._cache_files()
        ]

        if not files:
            return {
                "results": [],
                "errors": [],
                "rejected": 0,
                "partial": True,
                "cache_used": False,
            }

        duckdb = self._duckdb()

        file_sql = ", ".join(
            "'"
            + self._sql_quote_path(
                path
            )
            + "'"
            for path in files
        )

        predicates = (
            self._local_sql_predicates(
                query
            )
        )

        where = (
            " AND ".join(
                predicates
            )
            if predicates
            else "TRUE"
        )

        sql = f"""
            SELECT
                text,
                meta,
                filename
            FROM read_parquet(
                [{file_sql}],
                filename=true
            )
            WHERE {where}
            LIMIT 700
        """

        connection = duckdb.connect(
            database=":memory:"
        )

        try:
            rows = (
                connection.execute(
                    sql
                ).fetchall()
            )
        finally:
            connection.close()

        ranked = []
        rejected = 0
        rejection_reasons = Counter()
        seen = set()

        for text, meta, filename in rows:
            text = str(
                text or ""
            )

            if isinstance(
                meta,
                dict,
            ):
                meta_dict = meta
            elif isinstance(
                meta,
                str,
            ):
                try:
                    meta_dict = (
                        json.loads(
                            meta
                        )
                    )
                except Exception:
                    meta_dict = {
                        "raw": meta
                    }
            else:
                meta_dict = {}

            subset = str(
                meta_dict.get(
                    "pile_set_name",
                    "",
                )
                or "The Pile"
            )

            diagnostics = (
                self._relevance_diagnostics(
                    query,
                    text,
                    subset,
                )
            )

            if not diagnostics.get(
                "accepted"
            ):
                rejected += 1
                rejection_reasons[
                    diagnostics.get(
                        "reason",
                        "rejected",
                    )
                ] += 1
                continue

            relevance = float(
                diagnostics.get(
                    "score",
                    0.0,
                )
                or 0.0
            )

            excerpt = str(
                diagnostics.get(
                    "window",
                    "",
                )
                or self._best_excerpt(
                    text,
                    query,
                    max_chars=2600,
                )
            ).strip()[:2200]

            digest = self._hash(
                excerpt
            )

            local_locator = (
                Path(
                    str(
                        filename
                    )
                ).name
                + "#"
                + digest[:10]
            )

            if digest in seen:
                continue

            seen.add(digest)

            ranked.append(
                (
                    relevance,
                    {
                        "dataset": (
                            PILE_DATASET
                        ),
                        "dataset_label": (
                            "Local Pile Cache "
                            f"({subset})"
                        ),
                        "config": "default",
                        "split": (
                            "partial-train"
                        ),
                        "row_idx": (
                            local_locator
                        ),
                        "pile_set_name": (
                            subset
                        ),
                        "text": excerpt,
                        "characters": (
                            len(text)
                        ),
                        "meta": meta_dict,
                        "relevance": round(
                            float(
                                relevance
                            ),
                            5,
                        ),
                        "access_method": (
                            "local_parquet_cache"
                        ),
                        "cache_file": (
                            Path(
                                str(
                                    filename
                                )
                            ).name
                        ),
                        "quality_signals": (
                            diagnostics.get(
                                "signals",
                                [],
                            )
                        ),
                    },
                )
            )

        ranked.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return {
            "results": [
                item
                for _, item
                in ranked[:limit]
            ],
            "errors": [],
            "rejected": rejected,
            "rejection_reasons": (
                dict(rejection_reasons)
            ),
            "partial": True,
            "cache_used": True,
        }

    @staticmethod
    def _is_remote_service_error_text(
        error_text,
    ):
        """
        Errors that mean the remote source is unavailable/unhealthy rather than
        "the topic had no useful Pile result".

        These should trigger the local-cache fallback.
        """
        text = str(
            error_text or ""
        ).lower()

        markers = (
            "timeout",
            "timed out",
            "http error 404",
            "http error 500",
            "http error 501",
            "http error 502",
            "http error 503",
            "http error 504",
            "internal server error",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "temporary failure",
            "connection reset",
            "connection aborted",
            "connection refused",
            "remote end closed connection",
            "urlerror",
            "name or service not known",
            "temporary failure in name resolution",
        )

        return any(
            marker in text
            for marker in markers
        )

    @classmethod
    def _all_remote_service_errors(
        cls,
        errors,
    ):
        if not errors:
            return False

        return all(
            cls._is_remote_service_error_text(
                item.get(
                    "error",
                    item,
                )
            )
            for item in errors
        )

    def _mark_remote_unhealthy(
        self,
        error_text,
        seconds=900,
    ):
        self._last_remote_error = str(
            error_text or ""
        )
        self._remote_unhealthy_until = max(
            self._remote_unhealthy_until,
            time.time() + int(seconds),
        )

    def _remote_is_unhealthy(self):
        return (
            time.time()
            < self._remote_unhealthy_until
        )

    def _remote_health_status(self):
        remaining = max(
            0,
            int(
                self._remote_unhealthy_until
                - time.time()
            ),
        )

        return {
            "temporarily_unhealthy": (
                remaining > 0
            ),
            "retry_after_seconds": (
                remaining
            ),
            "last_error": (
                self._last_remote_error
            ),
        }

    def search_pile(
        self,
        query,
        limit=5,
    ):
        query = _normalize_query(
            query
        )

        if not query:
            raise ValueError(
                "query cannot be empty."
            )

        limit = self._limit(
            limit,
            default=5,
            maximum=12,
        )

        # If Hugging Face recently returned server/network errors, do not repeat
        # the same failing request every time the user retries. Use the local Pile
        # cache first until the short circuit-breaker expires.
        if self._remote_is_unhealthy():
            local_first = (
                self._search_local_cache(
                    query,
                    limit,
                )
            )

            if local_first.get(
                "results"
            ):
                return {
                    "query": query,
                    "dataset": PILE_DATASET,
                    "count": len(
                        local_first["results"]
                    ),
                    "partial": True,
                    "results": (
                        local_first["results"]
                    ),
                    "query_variants": [],
                    "rejected_as_irrelevant": (
                        local_first.get(
                            "rejected",
                            0,
                        )
                    ),
                    "errors": [
                        {
                            "remote_circuit_breaker": True,
                            "error": (
                                self._last_remote_error
                            ),
                        }
                    ],
                    "access_method": (
                        "local_parquet_cache"
                    ),
                    "remote_health": (
                        self._remote_health_status()
                    ),
                }

        remote = (
            self._remote_search(
                query,
                limit,
            )
        )

        results = remote.get(
            "results",
            [],
        )

        if results:
            return {
                "query": query,
                "dataset": PILE_DATASET,
                "count": len(results),
                "partial": bool(
                    remote.get(
                        "partial"
                    )
                ),
                "results": results,
                "query_variants": (
                    remote.get(
                        "variants",
                        [],
                    )
                ),
                "rejected_as_irrelevant": (
                    remote.get(
                        "rejected",
                        0,
                    )
                ),
                "rejection_reasons": (
                    remote.get(
                        "rejection_reasons",
                        {},
                    )
                ),
                "errors": (
                    remote.get(
                        "errors",
                        [],
                    )
                ),
                "access_method": (
                    "huggingface_search"
                ),
            }

        # Remote failed/no useful results: immediately use any existing local
        # cache rather than returning a dead-end error.
        local = (
            self._search_local_cache(
                query,
                limit,
            )
        )

        if local.get(
            "results"
        ):
            return {
                "query": query,
                "dataset": PILE_DATASET,
                "count": len(
                    local["results"]
                ),
                "partial": True,
                "results": (
                    local["results"]
                ),
                "query_variants": (
                    remote.get(
                        "variants",
                        [],
                    )
                ),
                "rejected_as_irrelevant": (
                    int(
                        remote.get(
                            "rejected",
                            0,
                        )
                    )
                    + int(
                        local.get(
                            "rejected",
                            0,
                        )
                    )
                ),
                "rejection_reasons": (
                    local.get(
                        "rejection_reasons",
                        {},
                    )
                ),
                "errors": (
                    remote.get(
                        "errors",
                        [],
                    )
                ),
                "access_method": (
                    "local_parquet_cache"
                ),
            }

        return {
            "query": query,
            "dataset": PILE_DATASET,
            "count": 0,
            "partial": bool(
                remote.get(
                    "partial"
                )
            ),
            "results": [],
            "query_variants": (
                remote.get(
                    "variants",
                    [],
                )
            ),
            "rejected_as_irrelevant": (
                remote.get(
                    "rejected",
                    0,
                )
            ),
            "rejection_reasons": (
                remote.get(
                    "rejection_reasons",
                    {},
                )
            ),
            "errors": (
                remote.get(
                    "errors",
                    [],
                )
            ),
            "access_method": (
                "none"
            ),
            "cache": (
                self.pile_cache_status()
            ),
            "remote_health": (
                self._remote_health_status()
            ),
        }

    def _replace_previous_query_knowledge(
        self,
        query,
    ):
        normalized = _normalize_query(
            query
        ).lower()

        with self._db_lock:
            rows = self.conn.execute(
                """
                SELECT id, meta_json
                FROM knowledge_chunks
                WHERE source = 'the_pile'
                """
            ).fetchall()

            ids = []

            for row in rows:
                try:
                    meta = json.loads(
                        row["meta_json"]
                        or "{}"
                    )
                except Exception:
                    meta = {}

                previous_query = _normalize_query(
                    meta.get(
                        "query",
                        "",
                    )
                ).lower()

                if (
                    previous_query
                    and previous_query
                    == normalized
                ):
                    ids.append(
                        row["id"]
                    )

            for ident in ids:
                self.conn.execute(
                    """
                    DELETE FROM knowledge_chunks
                    WHERE id = ?
                    """,
                    (ident,),
                )

            self.conn.commit()

        return len(ids)

    def learn_from_pile(
        self,
        query,
        limit=5,
        auto_cache=False,
    ):
        query = _normalize_query(
            query
        )

        result = self.search_pile(
            query,
            limit=limit,
        )

        auto_cache_downloaded = False
        cache_download_result = None

        # An explicit Learn command can opt into one Lite cache shard if the
        # remote service is unavailable (timeout, HTTP 5xx or connection failure)
        # and there is no cache yet.
        if (
            not result.get("results")
            and bool(auto_cache)
            and not self.validation
            and self._all_remote_service_errors(
                result.get(
                    "errors",
                    [],
                )
            )
            and self.pile_cache_status().get(
                "shards_cached",
                0,
            ) == 0
        ):
            if not self._duckdb_available():
                return {
                    "learned": False,
                    "query": query,
                    "documents_found": 0,
                    "chunks_added": 0,
                    "dataset": PILE_DATASET,
                    "errors": result.get(
                        "errors",
                        [],
                    ),
                    "dependency_missing": (
                        "duckdb"
                    ),
                    "action_required": (
                        "Run install.bat once, then retry. Apollo will be able "
                        "to download and search a local Lite Pile cache."
                    ),
                }

            try:
                cache_download_result = (
                    self.download_pile_cache(
                        shards=1,
                    )
                )
                auto_cache_downloaded = True

                # Search local directly after the fallback download. Do not hit
                # the remote endpoint again and waste another timeout cycle.
                local = (
                    self._search_local_cache(
                        query,
                        limit,
                    )
                )

                result = {
                    "query": query,
                    "dataset": (
                        PILE_DATASET
                    ),
                    "count": len(
                        local.get(
                            "results",
                            [],
                        )
                    ),
                    "partial": True,
                    "results": local.get(
                        "results",
                        [],
                    ),
                    "query_variants": [],
                    "rejected_as_irrelevant": (
                        local.get(
                            "rejected",
                            0,
                        )
                    ),
                    "rejection_reasons": (
                        local.get(
                            "rejection_reasons",
                            {},
                        )
                    ),
                    "errors": [],
                    "access_method": (
                        "local_parquet_cache"
                    ),
                }

            except Exception as exc:
                result.setdefault(
                    "errors",
                    [],
                ).append({
                    "cache_fallback": True,
                    "error": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                })

        replaced_previous_chunks = 0

        if result.get(
            "results"
        ):
            replaced_previous_chunks = (
                self._replace_previous_query_knowledge(
                    query
                )
            )

        inserted = 0
        learned_passages = []

        for item in result.get(
            "results",
            [],
        ):
            subset = (
                item.get(
                    "pile_set_name"
                )
                or "The Pile"
            )

            row_idx = item.get(
                "row_idx"
            )

            source_identity = (
                str(row_idx)
                if row_idx is not None
                else self._hash(
                    item.get(
                        "text",
                        "",
                    )
                )[:16]
            )

            source_ref = (
                f"{PILE_DATASET}:"
                f"{item.get('access_method', 'unknown')}:"
                f"{source_identity}:"
                f"{subset}"
            )

            curated_text = str(
                item.get(
                    "text",
                    "",
                )
            ).strip()[:2200]

            ident = self._insert_chunk(
                curated_text,
                title=(
                    f"The Pile — "
                    f"{subset} — {query}"
                ),
                source="the_pile",
                source_ref=source_ref,
                meta={
                    "query": query,
                    "pile_set_name": (
                        subset
                    ),
                    "row_idx": row_idx,
                    "dataset": (
                        PILE_DATASET
                    ),
                    "relevance": (
                        item.get(
                            "relevance"
                        )
                    ),
                    "quality_signals": (
                        item.get(
                            "quality_signals",
                            [],
                        )
                    ),
                    "access_method": (
                        item.get(
                            "access_method"
                        )
                    ),
                    "cache_file": (
                        item.get(
                            "cache_file"
                        )
                    ),
                },
            )

            added_count = (
                1
                if ident is not None
                else 0
            )

            inserted += (
                added_count
            )

            if added_count:
                learned_passages.append({
                    "subset": subset,
                    "row_idx": row_idx,
                    "source_ref": (
                        source_ref
                    ),
                    "relevance": (
                        item.get(
                            "relevance"
                        )
                    ),
                    "access_method": (
                        item.get(
                            "access_method"
                        )
                    ),
                    "cache_file": (
                        item.get(
                            "cache_file"
                        )
                    ),
                    "quality_signals": (
                        item.get(
                            "quality_signals",
                            [],
                        )
                    ),
                    "text": str(
                        item.get(
                            "text",
                            "",
                        )
                    )[:1800],
                })

        return {
            "learned": (
                inserted > 0
            ),
            "query": query,
            "documents_found": (
                result.get(
                    "count",
                    0,
                )
            ),
            "chunks_added": inserted,
            "dataset": PILE_DATASET,
            "partial": result.get(
                "partial",
                False,
            ),
            "rejected_as_irrelevant": (
                result.get(
                    "rejected_as_irrelevant",
                    0,
                )
            ),
            "rejection_reasons": (
                result.get(
                    "rejection_reasons",
                    {},
                )
            ),
            "replaced_previous_chunks": (
                replaced_previous_chunks
            ),
            "query_variants": (
                result.get(
                    "query_variants",
                    [],
                )
            ),
            "errors": result.get(
                "errors",
                [],
            ),
            "learned_passages": (
                learned_passages
            ),
            "access_method": (
                result.get(
                    "access_method"
                )
            ),
            "auto_cache_downloaded": (
                auto_cache_downloaded
            ),
            "cache_download": (
                cache_download_result
            ),
        }

    def _research_dir(self):
        return (
            self.base_dir
            / "storage"
            / "training"
            / "research"
        )

    def sync_research_files(self):
        folder = self._research_dir()

        if not folder.exists():
            return {
                "files_seen": 0,
                "files_changed": 0,
                "chunks_added": 0,
            }

        files_seen = 0
        files_changed = 0
        chunks_added = 0

        for path in sorted(
            folder.rglob("*")
        ):
            if not path.is_file():
                continue

            if path.suffix.lower() not in {
                ".txt",
                ".md",
                ".json",
                ".csv",
                ".py",
            }:
                continue

            if "self_test" in path.parts:
                continue

            files_seen += 1

            try:
                raw = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except Exception:
                continue

            relative = str(
                path.relative_to(
                    folder
                )
            ).replace(
                "\\",
                "/",
            )

            digest = self._hash(raw)

            with self._db_lock:
                row = self.conn.execute(
                    """
                    SELECT content_hash
                    FROM synced_sources
                    WHERE source_ref = ?
                    """,
                    (relative,),
                ).fetchone()

            if (
                row
                and row[
                    "content_hash"
                ] == digest
            ):
                continue

            with self._db_lock:
                self.conn.execute(
                    """
                    DELETE FROM knowledge_chunks
                    WHERE source = 'research_file'
                      AND source_ref = ?
                    """,
                    (relative,),
                )
                self.conn.commit()

            result = self.add_knowledge(
                raw,
                title=(
                    f"Saved research — "
                    f"{relative}"
                ),
                source="research_file",
                source_ref=relative,
                meta={
                    "filename": relative
                },
            )

            chunks_added += int(
                result.get(
                    "added",
                    0,
                )
            )
            files_changed += 1

            with self._db_lock:
                self.conn.execute(
                    """
                    INSERT INTO synced_sources(
                        source_ref,
                        content_hash,
                        synced_at
                    )
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(source_ref)
                    DO UPDATE SET
                        content_hash =
                            excluded.content_hash,
                        synced_at =
                            CURRENT_TIMESTAMP
                    """,
                    (
                        relative,
                        digest,
                    ),
                )
                self.conn.commit()

        return {
            "files_seen": files_seen,
            "files_changed": (
                files_changed
            ),
            "chunks_added": (
                chunks_added
            ),
        }

    def _search_fts(
        self,
        query,
        limit,
    ):
        terms = [
            token
            for token in _tokens(
                query
            )
            if len(token) >= 2
        ]

        if not terms:
            return []

        expression = " OR ".join(
            '"'
            + token.replace(
                '"',
                '""',
            )
            + '"'
            for token in terms[:12]
        )

        with self._db_lock:
            return self.conn.execute(
                """
                SELECT
                    k.id,
                    k.source,
                    k.source_ref,
                    k.title,
                    k.text,
                    k.meta_json,
                    bm25(
                        knowledge_fts
                    ) AS score
                FROM knowledge_fts
                JOIN knowledge_chunks AS k
                  ON k.id =
                     knowledge_fts.rowid
                WHERE knowledge_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (
                    expression,
                    limit,
                ),
            ).fetchall()

    def search_knowledge(
        self,
        query,
        limit=5,
    ):
        query = _normalize_query(
            query
        )

        if not query:
            raise ValueError(
                "query cannot be empty."
            )

        limit = self._limit(
            limit,
            default=5,
            maximum=12,
        )

        if not self.validation:
            try:
                self.sync_research_files()
            except Exception:
                pass

        rows = []

        if self.fts_available:
            try:
                rows = self._search_fts(
                    query,
                    limit,
                )
            except sqlite3.OperationalError:
                rows = []

        if not rows:
            with self._db_lock:
                all_rows = (
                    self.conn.execute(
                        """
                        SELECT
                            id,
                            source,
                            source_ref,
                            title,
                            text,
                            meta_json
                        FROM knowledge_chunks
                        ORDER BY id DESC
                        LIMIT 2000
                        """
                    ).fetchall()
                )

            ranked = []

            for row in all_rows:
                searchable = (
                    str(
                        row["title"]
                        or ""
                    )
                    + " "
                    + str(
                        row["text"]
                        or ""
                    )
                )

                score = _cosine(
                    query,
                    searchable,
                )

                if (
                    query.lower()
                    in searchable.lower()
                ):
                    score += 0.4

                if score > 0:
                    ranked.append(
                        (
                            score,
                            row,
                        )
                    )

            ranked.sort(
                key=lambda item: (
                    item[0]
                ),
                reverse=True,
            )

            rows = [
                row
                for _, row
                in ranked[:limit]
            ]

        output = []

        for row in rows[:limit]:
            text = str(
                row["text"]
                or ""
            )

            excerpt = self._best_excerpt(
                text,
                query,
                max_chars=3500,
            )

            try:
                meta = json.loads(
                    row[
                        "meta_json"
                    ]
                    or "{}"
                )
            except Exception:
                meta = {}

            output.append({
                "id": row["id"],
                "source": (
                    row["source"]
                ),
                "source_ref": (
                    row[
                        "source_ref"
                    ]
                ),
                "title": (
                    row["title"]
                ),
                "text": excerpt,
                "meta": meta,
            })

        return {
            "query": query,
            "count": len(output),
            "matches": output,
        }

    def stats(self):
        with self._db_lock:
            count = self.conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM knowledge_chunks
                """
            ).fetchone()["c"]

            sources = self.conn.execute(
                """
                SELECT
                    source,
                    COUNT(*) AS c
                FROM knowledge_chunks
                GROUP BY source
                ORDER BY c DESC
                """
            ).fetchall()

        return {
            "chunks": int(count),
            "sources": {
                row["source"]:
                    int(row["c"])
                for row in sources
            },
            "fts_available": bool(
                self.fts_available
            ),
            "database": (
                "in-memory validation database"
                if self.validation
                else self.db_path
            ),
            "pile_dataset": (
                PILE_DATASET
            ),
            "pile_cache": (
                self.pile_cache_status()
            ),
        }

    def self_test(self):
        assert (
            _normalize_query(
                "advanced ai codeing"
            )
            == "advanced ai coding"
        )

        assert self._all_remote_service_errors([
            {
                "error": (
                    "HTTPError: HTTP Error 500: "
                    "Internal Server Error"
                )
            }
        ])


        assert self._all_remote_service_errors([
            {
                "error": (
                    "HTTPError: HTTP Error 404: "
                    "Not Found"
                )
            }
        ])

        discovered = self._extract_parquet_entries({
            "parquet_files": [
                {
                    "dataset": PILE_DATASET,
                    "config": "default",
                    "split": "partial-train",
                    "url": (
                        "https://huggingface.co/datasets/example/"
                        "resolve/refs%2Fconvert%2Fparquet/"
                        "default/partial-train/0000.parquet"
                    ),
                    "filename": "0000.parquet",
                    "size": 123456789,
                }
            ],
            "partial": True,
        })

        assert len(discovered) == 1
        assert discovered[0]["split"] == "partial-train"
        assert discovered[0]["filename"] == "0000.parquet"

        assert self._all_remote_service_errors([
            {
                "error": (
                    "TimeoutError: "
                    "The read operation timed out"
                )
            }
        ])

        assert not self._all_remote_service_errors([
            {
                "error": (
                    "No relevant passages found"
                )
            }
        ])

        assert not self._contains_any(
            "calculate cosine distance",
            {"ai"},
        )
        assert not self._contains_any(
            "html document",
            {"ml"},
        )

        good = (
            "Advanced Python machine learning implementation using PyTorch "
            "covers neural network model training, inference, evaluation, "
            "debugging and data pipeline architecture."
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                good,
                "Github",
            )
            is not None
        )

        bad_xml = (
            '<?xml version="1.0"?><doi_batch xmlns="http://www.crossref.org" '
            'xmlns:ai="x" xmlns:xsi="y">'
            '<schemaLocation>crossref.org/schema</schemaLocation>'
            '<body>python ai metadata</body></doi_batch>'
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                bad_xml,
                "Github",
            )
            is None
        )

        beginner = (
            "How to open a web browser in Python from my chatbot application. "
            "I call webbrowser.open and want Firefox to launch."
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                beginner,
                "StackExchange",
            )
            is None
        )


        career_with_scattered_terms = (
            "There is a growing need among companies for AI professionals who "
            "know machine learning and deep learning. Career opportunities are "
            "expanding rapidly. Python is a popular language. Elsewhere this "
            "article mentions algorithms, classes, coding and gradients, but "
            "does not present model implementation, testing architecture, "
            "training code, APIs or a technical engineering workflow."
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                career_with_scattered_terms,
                "Pile-CC",
            )
            is None
        )

        strong_window = (
            "Advanced Python machine learning engineering with PyTorch. "
            "A neural network model training loop uses torch.optim, a loss "
            "function and gradient updates. The implementation includes "
            "inference, evaluation, unit tests, debugging, GPU batching and "
            "a production data pipeline architecture. "
            "import torch\n"
            "def train_model(model, loader, optimizer):\n"
            "    model.train()\n"
            "    return model\n"
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                strong_window,
                "Github",
            )
            is not None
        )


        quickdraw_beginner = (
            "Q: Applying machine learning algorithms on Google's Quickdraw "
            "dataset. I'm trying to apply machine learning algorithms available "
            "in Python's scikit-learn package. Since I'm a complete beginner in "
            "machine learning and I have no knowledge about how neural networks "
            "work yet, I wanted to try scikit-learn algorithms."
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                quickdraw_beginner,
                "StackExchange",
            )
            is None
        )

        korean_dominant = (
            "Python PyTorch embedding tokenization inference numpy. "
            + "한국어 임베딩 개발자를 위한 형태소 처리와 토크나이징 설명입니다. "
            * 35
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                korean_dominant,
                "Github",
            )
            is None
        )

        added = self.add_knowledge(
            (
                "A printed circuit board "
                "connects electronic components "
                "using conductive copper traces."
            ),
            title="Circuit board basics",
            source="self_test",
            source_ref="test:pcb",
        )

        assert added["added"] >= 1

        found = self.search_knowledge(
            "copper traces circuit board",
            limit=3,
        )

        assert found["matches"]

        errors = []

        def worker():
            try:
                result = (
                    self.search_knowledge(
                        "copper circuit",
                        limit=2,
                    )
                )
                assert result[
                    "matches"
                ]
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(
            target=worker
        )
        thread.start()
        thread.join(
            timeout=5
        )

        assert not thread.is_alive()
        assert not errors

        directory_dump = (
            "# Useful Python AI repositories\n"
            + "\n".join(
                (
                    f"- [project{i}](https://github.com/example/project{i}): "
                    "PyTorch machine learning API architecture inference GPU"
                )
                for i in range(12)
            )
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                directory_dump,
                "Github",
            )
            is None
        )

        korean_readme = (
            "Python PyTorch embedding inference tokenization. "
            + (
                "한국어 임베딩과 형태소 분석 토크나이징 설명입니다. "
                * 50
            )
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                korean_readme,
                "Github",
            )
            is None
        )

        traceback_dump = (
            "Python TensorFlow machine learning debugging GPU optimizer.\n"
            "Traceback (most recent call last):\n"
            + "\n".join(
                (
                    f'File "/tmp/train.py", line {i}, in train\n'
                    "tensorflow.python.framework.errors_impl.ResourceExhaustedError: OOM"
                )
                for i in range(8)
            )
        )

        assert (
            self._relevance(
                "advanced ai coding in python",
                traceback_dump,
                "StackExchange",
            )
            is None
        )

        return (
            "Compiled knowledge, high-signal curation, typo normalization and "
            "cross-thread SQLite tests passed."
        )

    def build_ui(
        self,
        parent=None,
        ui_context=None,
    ):
        from PySide6.QtCore import (
            QObject,
            QRunnable,
            QThreadPool,
            Signal,
            Slot,
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
            def __init__(
                self,
                fn,
            ):
                super().__init__()
                self.fn = fn
                self.signals = Signals()
                self.setAutoDelete(
                    True
                )

            @Slot()
            def run(self):
                try:
                    self.signals.finished.emit(
                        self.fn()
                    )
                except Exception as exc:
                    self.signals.failed.emit(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

        page = QWidget(parent)
        layout = QVBoxLayout(page)

        title = QLabel(
            "Apollo Knowledge Base"
        )
        title.setStyleSheet(
            "font-size:22px;"
            "font-weight:700;"
            "color:#e7fffb;"
        )

        info = QLabel(
            "Apollo tries The Pile online first. If Hugging Face search is slow, "
            "you can keep a resumable local Parquet cache and search it directly."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#91bdb6;"
        )

        query = QLineEdit()
        query.setPlaceholderText(
            "Topic — e.g. advanced AI coding"
        )

        buttons = QHBoxLayout()

        local_btn = QPushButton(
            "Search Local Knowledge"
        )
        pile_btn = QPushButton(
            "Search The Pile"
        )
        learn_btn = QPushButton(
            "Learn From The Pile"
        )
        cache_btn = QPushButton(
            "Download Lite Cache (1 shard)"
        )
        cache_more_btn = QPushButton(
            "Add One Cache Shard"
        )
        status_btn = QPushButton(
            "Cache / Knowledge Stats"
        )

        for button in (
            local_btn,
            pile_btn,
            learn_btn,
            cache_btn,
            cache_more_btn,
            status_btn,
        ):
            buttons.addWidget(button)

        status = QLabel("Ready")
        status.setStyleSheet(
            "color:#75d8c5;"
        )

        output = QTextBrowser()
        output.setOpenExternalLinks(
            True
        )

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(query)
        layout.addLayout(buttons)
        layout.addWidget(status)
        layout.addWidget(
            output,
            1,
        )

        pool = (
            QThreadPool.globalInstance()
        )
        active = []

        def keep(task):
            active.append(task)

            def release(*_):
                try:
                    active.remove(
                        task
                    )
                except ValueError:
                    pass

            task.signals.finished.connect(
                release
            )
            task.signals.failed.connect(
                release
            )

        def fail(message):
            status.setText(
                "Error"
            )
            output.setPlainText(
                str(message)
            )

        def run_task(
            status_text,
            fn,
            renderer,
        ):
            status.setText(
                status_text
            )

            task = Task(fn)

            task.signals.finished.connect(
                renderer
            )
            task.signals.failed.connect(
                fail
            )

            keep(task)
            pool.start(task)

        def require_query():
            value = (
                query.text().strip()
            )

            if not value:
                QMessageBox.information(
                    page,
                    "Apollo Knowledge",
                    "Enter a topic first.",
                )
                return None

            return value

        def render_search(result):
            status.setText(
                f"Pile matches: "
                f"{result.get('count', 0)} — "
                f"{result.get('access_method', 'unknown')}"
            )

            pieces = []

            for item in result.get(
                "results",
                [],
            ):
                pieces.append(
                    "<h3>"
                    + html.escape(
                        str(
                            item.get(
                                "pile_set_name"
                            )
                            or "The Pile"
                        )
                    )
                    + "</h3>"
                    + "<p><b>Access:</b> "
                    + html.escape(
                        str(
                            item.get(
                                "access_method"
                            )
                        )
                    )
                    + "</p>"
                    + "<pre style='white-space:pre-wrap;'>"
                    + html.escape(
                        str(
                            item.get(
                                "text",
                                "",
                            )
                        )
                    )
                    + "</pre>"
                )

            if not pieces:
                pieces.append(
                    "<pre>"
                    + html.escape(
                        json.dumps(
                            result,
                            indent=2,
                            ensure_ascii=False,
                        )
                    )
                    + "</pre>"
                )

            output.setHtml(
                "\n".join(
                    pieces
                )
            )

        def render_learn(result):
            status.setText(
                "Pile learning complete"
            )

            output.setPlainText(
                "Topic: "
                f"{result.get('query')}\n"
                "Documents accepted: "
                f"{result.get('documents_found')}\n"
                "Chunks added: "
                f"{result.get('chunks_added')}\n"
                "Access method: "
                f"{result.get('access_method')}\n"
                "Automatic Lite cache downloaded: "
                f"{result.get('auto_cache_downloaded')}\n"
                "Errors: "
                f"{len(result.get('errors', []))}"
            )

        def render_cache(result):
            status.setText(
                "Pile cache updated"
            )
            output.setPlainText(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                )
            )

        def render_stats(result):
            status.setText(
                "Knowledge / cache stats"
            )
            output.setPlainText(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                )
            )

        local_btn.clicked.connect(
            lambda: (
                lambda q: (
                    run_task(
                        "Searching compiled local knowledge...",
                        lambda: (
                            module.search_knowledge(
                                q,
                                6,
                            )
                        ),
                        lambda result: (
                            output.setPlainText(
                                json.dumps(
                                    result,
                                    indent=2,
                                    ensure_ascii=False,
                                )
                            ),
                            status.setText(
                                f"Local matches: "
                                f"{result.get('count', 0)}"
                            ),
                        ),
                    )
                    if q
                    else None
                )
            )(
                require_query()
            )
        )

        pile_btn.clicked.connect(
            lambda: (
                lambda q: (
                    run_task(
                        "Searching The Pile online/cache...",
                        lambda: (
                            module.search_pile(
                                q,
                                6,
                            )
                        ),
                        render_search,
                    )
                    if q
                    else None
                )
            )(
                require_query()
            )
        )

        learn_btn.clicked.connect(
            lambda: (
                lambda q: (
                    run_task(
                        "Learning from The Pile...",
                        lambda: (
                            module.learn_from_pile(
                                q,
                                6,
                                auto_cache=False,
                            )
                        ),
                        render_learn,
                    )
                    if q
                    else None
                )
            )(
                require_query()
            )
        )

        cache_btn.clicked.connect(
            lambda: run_task(
                "Discovering current Pile Parquet shard and downloading/resuming cache...",
                lambda: (
                    module.download_pile_cache(
                        1
                    )
                ),
                render_cache,
            )
        )

        def add_one():
            cached = (
                module.pile_cache_status()
                .get(
                    "shards_cached",
                    0,
                )
            )

            target = min(
                len(
                    PILE_CACHE_SHARDS
                ),
                cached + 1,
            )

            run_task(
                f"Downloading/resuming Pile cache shard {target}...",
                lambda: (
                    module.download_pile_cache(
                        target
                    )
                ),
                render_cache,
            )

        cache_more_btn.clicked.connect(
            add_one
        )

        status_btn.clicked.connect(
            lambda: run_task(
                "Reading cache/knowledge status...",
                module.stats,
                render_stats,
            )
        )

        return page

    @staticmethod
    def _natural_language_readability(
        text,
    ):
        """
        Estimate whether the explanatory prose is predominantly English.

        URLs, markdown link destinations, inline/fenced code and common code-ish
        identifiers are removed before measuring. This prevents a README full of
        URLs/library names from looking "English enough" when the prose itself is
        mostly another language.
        """
        value = str(text or "")

        # Remove fenced code.
        value = re.sub(
            r"```.*?```",
            " ",
            value,
            flags=re.DOTALL,
        )

        # Remove markdown link destinations while keeping visible link text.
        value = re.sub(
            r"\[([^\]]+)\]\([^)]+\)",
            r"\1",
            value,
        )

        # Remove URLs.
        value = re.sub(
            r"https?://\S+",
            " ",
            value,
            flags=re.IGNORECASE,
        )

        # Remove inline code.
        value = re.sub(
            r"`[^`]+`",
            " ",
            value,
        )

        letters = [
            char
            for char in value
            if char.isalpha()
        ]

        if not letters:
            return {
                "english_ratio": 1.0,
                "letters": 0,
                "english_words": 0,
            }

        ascii_latin = sum(
            1
            for char in letters
            if "a" <= char.lower() <= "z"
        )

        english_words = len(
            re.findall(
                r"\b[a-zA-Z]{3,}\b",
                value,
            )
        )

        return {
            "english_ratio": (
                ascii_latin
                / len(letters)
            ),
            "letters": len(
                letters
            ),
            "english_words": (
                english_words
            ),
        }

    @staticmethod
    def _document_structure_quality(
        text,
    ):
        value = str(text or "")
        lines = [
            line.strip()
            for line in value.splitlines()
            if line.strip()
        ]

        markdown_links = len(
            re.findall(
                r"\[[^\]]{1,120}\]\([^)]+\)",
                value,
            )
        )

        raw_urls = len(
            re.findall(
                r"https?://",
                value,
                flags=re.IGNORECASE,
            )
        )

        list_lines = sum(
            1
            for line in lines
            if re.match(
                r"^(?:[-*+]|\d+[.)])\s+",
                line,
            )
        )

        traceback_markers = len(
            re.findall(
                (
                    r"(?:^|\n)\s*Traceback \(most recent call last\):"
                    r"|(?:^|\n)\s*File \"[^\"]+\", line \d+"
                    r"|(?:^|\n).*(?:Error|Exception):\s"
                    r"|(?:^|\n).*(?:tensorflow|torch).*(?:warning|error)"
                ),
                value,
                flags=re.IGNORECASE,
            )
        )

        prose_sentences = len(
            re.findall(
                r"[A-Za-z][^.!?\n]{25,}[.!?]",
                value,
            )
        )

        line_count = max(
            1,
            len(lines),
        )

        list_ratio = (
            list_lines
            / line_count
        )

        # Repository indexes / awesome lists can look very technical because
        # every bullet names frameworks and projects. They are navigation, not
        # explanatory knowledge.
        link_directory = (
            markdown_links >= 7
            and (
                list_ratio >= 0.28
                or (
                    markdown_links
                    + raw_urls
                ) >= 12
            )
            and prose_sentences < 8
        )

        # Raw failure logs are useful evidence but poor knowledge chunks. If an
        # answer/explanation exists elsewhere in the document, window scoring can
        # pick that instead.
        traceback_heavy = (
            traceback_markers >= 5
            and prose_sentences < 4
        )

        return {
            "link_directory": (
                link_directory
            ),
            "traceback_heavy": (
                traceback_heavy
            ),
            "markdown_links": (
                markdown_links
            ),
            "raw_urls": raw_urls,
            "list_ratio": round(
                list_ratio,
                4,
            ),
            "traceback_markers": (
                traceback_markers
            ),
            "prose_sentences": (
                prose_sentences
            ),
        }

    def _technical_window_quality(
        self,
        query,
        text,
        subset,
    ):
        query = str(query or "")
        value = self._strip_front_matter(
            text
        )
        lower_query = query.lower()

        markup = self._markup_quality(
            value
        )

        if markup["reject"]:
            return {
                "accepted": False,
                "reason": "markup_or_metadata",
                "score": 0.0,
                "signals": [],
            }

        structure = (
            self._document_structure_quality(
                value
            )
        )

        if structure[
            "link_directory"
        ]:
            return {
                "accepted": False,
                "reason": "link_directory_or_catalog",
                "score": 0.0,
                "signals": [],
            }

        if structure[
            "traceback_heavy"
        ]:
            return {
                "accepted": False,
                "reason": "traceback_or_log_dump",
                "score": 0.0,
                "signals": [],
            }

        python_required = (
            self._contains_any(
                lower_query,
                {"python"},
            )
        )

        if (
            python_required
            and not self._contains_any(
                value,
                {"python"},
            )
        ):
            return {
                "accepted": False,
                "reason": "missing_python",
                "score": 0.0,
                "signals": [],
            }

        ai_signals = self._matched_aliases(
            value,
            AI_TECHNICAL_SIGNALS,
        )
        engineering_signals = self._matched_aliases(
            value,
            ADVANCED_ENGINEERING_SIGNALS,
        )
        implementation_signals = self._matched_aliases(
            value,
            IMPLEMENTATION_SIGNALS,
        )
        library_signals = self._matched_aliases(
            value,
            LIBRARY_SIGNALS,
        )
        coding_signals = self._matched_aliases(
            value,
            CODING_ALIASES,
        )
        career_signals = self._matched_aliases(
            value,
            GENERIC_CAREER_SIGNALS,
        )
        novice_signals = self._matched_aliases(
            value,
            NOVICE_SIGNALS,
        )

        syntax_count = (
            self._code_syntax_count(
                value
            )
        )

        is_advanced = (
            self._contains_any(
                lower_query,
                {"advanced"},
            )
        )

        if (
            self._contains_any(
                lower_query,
                AI_ALIASES,
            )
            and not ai_signals
        ):
            return {
                "accepted": False,
                "reason": (
                    "no_advanced_ai_technical_signal"
                    if is_advanced
                    else "weak_ai_relevance"
                ),
                "score": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(
                lower_query,
                CODING_ALIASES,
            )
            and not coding_signals
        ):
            return {
                "accepted": False,
                "reason": "missing_coding_evidence",
                "score": 0.0,
                "signals": ai_signals,
            }

        unique_ai = set(
            ai_signals
        )
        unique_engineering = set(
            engineering_signals
        )
        unique_implementation = set(
            implementation_signals
        )
        unique_libraries = set(
            library_signals
        )

        implementation_strength = (
            len(
                unique_implementation
            )
            + len(
                unique_libraries
            )
            + min(
                syntax_count,
                3,
            )
        )

        if is_advanced:
            if (
                novice_signals
                and (
                    implementation_strength < 5
                    or syntax_count < 2
                )
            ):
                return {
                    "accepted": False,
                    "reason": "novice_material",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if len(
                unique_ai
            ) < 2:
                return {
                    "accepted": False,
                    "reason": "insufficient_ai_depth",
                    "score": 0.0,
                    "signals": ai_signals,
                }

            if len(
                unique_engineering
            ) < 2:
                return {
                    "accepted": False,
                    "reason": "insufficient_engineering_depth",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if (
                implementation_strength
                < 2
            ):
                return {
                    "accepted": False,
                    "reason": "insufficient_implementation_evidence",
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

        technical_count = len(
            unique_ai
            | unique_engineering
            | unique_implementation
            | unique_libraries
        )

        if (
            is_advanced
            and career_signals
            and syntax_count == 0
            and len(
                unique_libraries
            ) < 2
        ):
            return {
                "accepted": False,
                "reason": "generic_career_or_news_material",
                "score": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                ),
            }

        if (
            career_signals
            and technical_count < 6
            and syntax_count == 0
        ):
            return {
                "accepted": False,
                "reason": "generic_career_or_course_material",
                "score": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                ),
            }

        readability = (
            self._natural_language_readability(
                value
            )
        )

        # Much stricter than v1.8. Code/URLs no longer count toward the English
        # ratio. A non-English README can still pass only if it contains a lot of
        # actual code and enough English explanation to be directly useful.
        if (
            is_advanced
            and readability[
                "letters"
            ] >= 200
            and readability[
                "english_ratio"
            ] < 0.74
            and (
                syntax_count < 4
                or readability[
                    "english_words"
                ] < 90
            )
        ):
            return {
                "accepted": False,
                "reason": "non_english_dominant",
                "score": 0.0,
                "signals": (
                    ai_signals
                    + engineering_signals
                    + implementation_signals
                ),
            }

        score = _cosine(
            query,
            value,
        )

        score += min(
            0.70,
            (
                len(
                    unique_ai
                )
                * 0.09
                + len(
                    unique_engineering
                )
                * 0.08
                + len(
                    unique_implementation
                )
                * 0.08
                + len(
                    unique_libraries
                )
                * 0.07
                + min(
                    syntax_count,
                    4,
                )
                * 0.09
            ),
        )

        if subset == "Github":
            score += 0.12
        elif subset == "ArXiv":
            score += 0.12
        elif subset == "StackExchange":
            score += 0.02
        elif subset == "Pile-CC":
            score -= 0.12

        if novice_signals:
            score -= 0.20

        # Penalise remaining link/log density without automatically rejecting a
        # legitimate documentation section.
        score -= min(
            0.15,
            (
                structure[
                    "markdown_links"
                ]
                * 0.006
                + structure[
                    "traceback_markers"
                ]
                * 0.015
            ),
        )

        return {
            "accepted": True,
            "reason": "accepted",
            "score": round(
                float(score),
                5,
            ),
            "signals": sorted(
                set(
                    ai_signals
                    + engineering_signals
                    + implementation_signals
                    + library_signals
                )
            )[:24],
            "syntax_count": (
                syntax_count
            ),
            "english_ratio": round(
                readability[
                    "english_ratio"
                ],
                4,
            ),
            "structure": structure,
        }

    def _best_technical_window(
        self,
        text,
        query,
        subset,
        max_chars=2400,
    ):
        windows = self._window_candidates(
            text,
            query,
            window_chars=max_chars,
        )

        best_window = None
        best_quality = None
        rejection_reasons = Counter()

        for raw_window in windows:
            window = self._strip_front_matter(
                raw_window
            )

            quality = self._technical_window_quality(
                query,
                window,
                subset,
            )

            if not quality.get(
                "accepted"
            ):
                rejection_reasons[
                    quality.get(
                        "reason",
                        "rejected",
                    )
                ] += 1
                continue

            if (
                best_quality is None
                or float(
                    quality.get(
                        "score",
                        0.0,
                    )
                )
                > float(
                    best_quality.get(
                        "score",
                        0.0,
                    )
                )
            ):
                best_window = window
                best_quality = quality

        if best_window is None:
            reason = (
                rejection_reasons.most_common(
                    1
                )[0][0]
                if rejection_reasons
                else "no_technical_window"
            )

            return {
                "accepted": False,
                "reason": reason,
                "window": "",
                "score": None,
                "signals": [],
            }

        best_window = str(
            best_window
        ).strip()[
            :2400
        ]

        return {
            "accepted": True,
            "reason": "accepted",
            "window": best_window,
            "score": best_quality.get(
                "score",
                0.0,
            ),
            "signals": best_quality.get(
                "signals",
                [],
            ),
            "syntax_count": best_quality.get(
                "syntax_count",
                0,
            ),
        }

    def _relevance_diagnostics(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")

        if not value.strip():
            return {
                "accepted": False,
                "reason": "empty",
                "signals": [],
            }

        missing = []

        for name, aliases in (
            self._concept_requirements(
                query
            )
        ):
            if not self._contains_any(
                value,
                aliases,
            ):
                missing.append(
                    name
                )

        if missing:
            return {
                "accepted": False,
                "reason": (
                    "missing_"
                    + "_and_".join(
                        missing
                    )
                ),
                "signals": [],
            }

        technical = self._best_technical_window(
            value,
            query,
            subset,
            max_chars=2400,
        )

        if not technical.get(
            "accepted"
        ):
            return {
                "accepted": False,
                "reason": technical.get(
                    "reason",
                    "no_technical_window",
                ),
                "signals": technical.get(
                    "signals",
                    [],
                ),
            }

        return {
            "accepted": True,
            "reason": "accepted",
            "signals": technical.get(
                "signals",
                [],
            ),
            "score": technical.get(
                "score",
                0.0,
            ),
            "window": technical.get(
                "window",
                "",
            ),
            "syntax_count": technical.get(
                "syntax_count",
                0,
            ),
        }

    def _relevance(
        self,
        query,
        text,
        subset,
    ):
        result = self._relevance_diagnostics(
            query,
            text,
            subset,
        )

        if not result.get(
            "accepted"
        ):
            return None

        return float(
            result.get(
                "score",
                0.0,
            )
            or 0.0
        )

    def _local_sql_predicates(
        self,
        query,
    ):
        """
        Final active local-cache prefilter.

        V1.8 accidentally defined a stricter SQL prefilter before an older method
        later in the class, so Python silently used the older broad version.
        This definition is deliberately placed at the end of the class.
        """
        lower = str(
            query or ""
        ).lower()

        predicates = []

        if self._contains_any(
            lower,
            AI_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'machine learning') OR "
                "contains(lower(text), 'deep learning') OR "
                "contains(lower(text), 'neural network') OR "
                "contains(lower(text), 'transformer') OR "
                "contains(lower(text), 'language model') OR "
                "contains(lower(text), 'pytorch') OR "
                "contains(lower(text), 'tensorflow') OR "
                "contains(lower(text), 'scikit-learn')"
                ")"
            )

        if self._contains_any(
            lower,
            CODING_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'python') OR "
                "contains(lower(text), 'implementation') OR "
                "contains(lower(text), 'source code') OR "
                "contains(lower(text), 'debugging') OR "
                "contains(lower(text), 'inference') OR "
                "contains(lower(text), 'training') OR "
                "contains(lower(text), 'evaluation')"
                ")"
            )

        if self._contains_any(
            lower,
            {"python"},
        ):
            predicates.append(
                "contains(lower(text), 'python')"
            )

        if self._contains_any(
            lower,
            {"advanced"},
        ):
            # Two separate implementation groups make the SQL filter much less
            # likely to hand the Python reranker generic AI pages.
            predicates.append(
                "("
                "contains(lower(text), 'pytorch') OR "
                "contains(lower(text), 'tensorflow') OR "
                "contains(lower(text), 'scikit-learn') OR "
                "contains(lower(text), 'keras') OR "
                "contains(lower(text), 'transformer')"
                ")"
            )

            predicates.append(
                "("
                "contains(lower(text), 'training') OR "
                "contains(lower(text), 'inference') OR "
                "contains(lower(text), 'evaluation') OR "
                "contains(lower(text), 'debugging') OR "
                "contains(lower(text), 'optimizer') OR "
                "contains(lower(text), 'loss function') OR "
                "contains(lower(text), 'embedding') OR "
                "contains(lower(text), 'attention') OR "
                "contains(lower(text), 'data pipeline') OR "
                "contains(lower(text), 'architecture') OR "
                "contains(lower(text), 'gpu') OR "
                "contains(lower(text), 'cuda')"
                ")"
            )

        return predicates


    @staticmethod
    def _source_script_profile(
        text,
    ):
        value = str(text or "")

        letters = [
            char
            for char in value
            if char.isalpha()
        ]

        total = max(
            1,
            len(letters),
        )

        ascii_latin = sum(
            1
            for char in letters
            if "a" <= char.lower() <= "z"
        )

        hangul = len(
            re.findall(
                r"[\uac00-\ud7a3]",
                value,
            )
        )

        cjk = len(
            re.findall(
                r"[\u3400-\u4dbf\u4e00-\u9fff]",
                value,
            )
        )

        kana = len(
            re.findall(
                r"[\u3040-\u30ff]",
                value,
            )
        )

        return {
            "letters": len(
                letters
            ),
            "ascii_latin_ratio": (
                ascii_latin
                / total
            ),
            "hangul": hangul,
            "hangul_ratio": (
                hangul
                / total
            ),
            "cjk": cjk,
            "kana": kana,
        }

    @staticmethod
    def _whole_source_structure(
        text,
    ):
        value = str(text or "")

        markdown_links = len(
            re.findall(
                r"\[[^\]]{1,180}\]\([^)]+\)",
                value,
            )
        )

        github_urls = len(
            re.findall(
                r"github\.com/",
                value,
                flags=re.IGNORECASE,
            )
        )

        raw_urls = len(
            re.findall(
                r"https?://",
                value,
                flags=re.IGNORECASE,
            )
        )

        repository_bullets = len(
            re.findall(
                r"(?:^|\n|\s)[*+-]\s*"
                r"\[[^\]]+\]\("
                r"https?://github\.com/",
                value,
                flags=re.IGNORECASE,
            )
        )

        prose_sentences = len(
            re.findall(
                r"[A-Za-z][^.!?\n]{30,}[.!?]",
                value,
            )
        )

        question_prefix = bool(
            re.search(
                r"^\s*Q\s*:",
                value,
                flags=re.IGNORECASE,
            )
        )

        answer_marker = bool(
            re.search(
                r"(?:^|\n)\s*(?:A|Answer)\s*:",
                value,
                flags=re.IGNORECASE,
            )
        )

        traceback_markers = len(
            re.findall(
                (
                    r"Traceback \(most recent call last\):"
                    r"|File \"[^\"]+\", line \d+"
                    r"|(?:Error|Exception):\s"
                    r"|ResourceExhaustedError"
                    r"|InvalidArgumentError"
                ),
                value,
                flags=re.IGNORECASE,
            )
        )

        return {
            "markdown_links": (
                markdown_links
            ),
            "github_urls": (
                github_urls
            ),
            "raw_urls": raw_urls,
            "repository_bullets": (
                repository_bullets
            ),
            "prose_sentences": (
                prose_sentences
            ),
            "question_prefix": (
                question_prefix
            ),
            "answer_marker": (
                answer_marker
            ),
            "traceback_markers": (
                traceback_markers
            ),
        }

    def _whole_source_policy(
        self,
        query,
        text,
        subset,
    ):
        """
        Source-level gate. This runs BEFORE technical-window extraction.

        A locally technical-looking 2k window cannot rescue an entire repository
        catalog, question-only beginner post or overwhelmingly non-English source.
        """
        value = str(text or "")
        lower_query = str(
            query or ""
        ).lower()

        is_advanced = (
            self._contains_any(
                lower_query,
                {"advanced"},
            )
        )

        structure = (
            self._whole_source_structure(
                value
            )
        )

        scripts = (
            self._source_script_profile(
                value
            )
        )

        syntax_count = (
            self._code_syntax_count(
                value
            )
        )

        novice_signals = (
            self._matched_aliases(
                value,
                NOVICE_SIGNALS,
            )
        )

        # Repository/awesome-list style documents are navigation, not durable
        # engineering knowledge. Check the whole source so a small technical
        # fragment cannot sneak the catalog through.
        if (
            subset == "Github"
            and (
                structure[
                    "github_urls"
                ] >= 5
                or structure[
                    "repository_bullets"
                ] >= 3
                or (
                    structure[
                        "markdown_links"
                    ] >= 7
                    and structure[
                        "raw_urls"
                    ] >= 7
                )
            )
            and syntax_count < 3
        ):
            return {
                "accepted": False,
                "reason": (
                    "repository_catalog"
                ),
            }

        # Advanced learning from StackExchange should consume explanations/answers,
        # not a raw question body.
        if (
            is_advanced
            and subset == "StackExchange"
            and structure[
                "question_prefix"
            ]
            and not structure[
                "answer_marker"
            ]
        ):
            return {
                "accepted": False,
                "reason": (
                    "question_only_source"
                ),
            }

        if (
            is_advanced
            and novice_signals
            and subset == "StackExchange"
        ):
            return {
                "accepted": False,
                "reason": (
                    "novice_material"
                ),
            }

        # Explicit script counting closes the Korean README hole reliably.
        if (
            is_advanced
            and scripts[
                "letters"
            ] >= 300
            and (
                scripts[
                    "hangul"
                ] >= 80
                or scripts[
                    "hangul_ratio"
                ] >= 0.10
                or scripts[
                    "cjk"
                ] >= 120
                or scripts[
                    "kana"
                ] >= 120
            )
            and syntax_count < 8
        ):
            return {
                "accepted": False,
                "reason": (
                    "non_english_dominant"
                ),
            }

        if (
            structure[
                "traceback_markers"
            ] >= 12
            and structure[
                "prose_sentences"
            ] < 8
        ):
            return {
                "accepted": False,
                "reason": (
                    "traceback_or_log_dump"
                ),
            }

        return {
            "accepted": True,
            "reason": "accepted",
        }

    def _technical_window_quality(
        self,
        query,
        text,
        subset,
    ):
        query = str(query or "")
        value = self._strip_front_matter(
            text
        )
        lower_query = query.lower()

        markup = self._markup_quality(
            value
        )

        if markup["reject"]:
            return {
                "accepted": False,
                "reason": (
                    "markup_or_metadata"
                ),
                "score": 0.0,
                "signals": [],
            }

        python_required = (
            self._contains_any(
                lower_query,
                {"python"},
            )
        )

        if (
            python_required
            and not self._contains_any(
                value,
                {"python"},
            )
        ):
            return {
                "accepted": False,
                "reason": "missing_python",
                "score": 0.0,
                "signals": [],
            }

        ai_signals = self._matched_aliases(
            value,
            AI_TECHNICAL_SIGNALS,
        )
        engineering_signals = (
            self._matched_aliases(
                value,
                ADVANCED_ENGINEERING_SIGNALS,
            )
        )
        implementation_signals = (
            self._matched_aliases(
                value,
                IMPLEMENTATION_SIGNALS,
            )
        )
        library_signals = (
            self._matched_aliases(
                value,
                LIBRARY_SIGNALS,
            )
        )
        coding_signals = (
            self._matched_aliases(
                value,
                CODING_ALIASES,
            )
        )
        career_signals = (
            self._matched_aliases(
                value,
                GENERIC_CAREER_SIGNALS,
            )
        )

        syntax_count = (
            self._code_syntax_count(
                value
            )
        )

        is_advanced = (
            self._contains_any(
                lower_query,
                {"advanced"},
            )
        )

        unique_ai = set(
            ai_signals
        )
        unique_engineering = set(
            engineering_signals
        )
        unique_implementation = set(
            implementation_signals
        )
        unique_libraries = set(
            library_signals
        )

        implementation_strength = (
            len(
                unique_implementation
            )
            + len(
                unique_libraries
            )
            + min(
                syntax_count,
                4,
            )
        )

        if (
            self._contains_any(
                lower_query,
                AI_ALIASES,
            )
            and not unique_ai
        ):
            return {
                "accepted": False,
                "reason": "missing_ai",
                "score": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(
                lower_query,
                CODING_ALIASES,
            )
            and not coding_signals
        ):
            return {
                "accepted": False,
                "reason": "missing_coding",
                "score": 0.0,
                "signals": [],
            }

        if is_advanced:
            if len(
                unique_ai
            ) < 2:
                return {
                    "accepted": False,
                    "reason": (
                        "insufficient_ai_depth"
                    ),
                    "score": 0.0,
                    "signals": ai_signals,
                }

            if len(
                unique_engineering
            ) < 2:
                return {
                    "accepted": False,
                    "reason": (
                        "insufficient_engineering_depth"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if (
                implementation_strength
                < 3
            ):
                return {
                    "accepted": False,
                    "reason": (
                        "insufficient_implementation_evidence"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

            if (
                subset == "ArXiv"
                and not unique_libraries
                and syntax_count == 0
            ):
                return {
                    "accepted": False,
                    "reason": (
                        "theory_without_implementation"
                    ),
                    "score": 0.0,
                    "signals": (
                        ai_signals
                        + engineering_signals
                    ),
                }

        if (
            career_signals
            and syntax_count == 0
            and len(
                unique_libraries
            ) < 2
        ):
            return {
                "accepted": False,
                "reason": (
                    "generic_career_or_news_material"
                ),
                "score": 0.0,
                "signals": [],
            }

        score = _cosine(
            query,
            value,
        )

        score += min(
            0.75,
            (
                len(
                    unique_ai
                )
                * 0.09
                + len(
                    unique_engineering
                )
                * 0.09
                + len(
                    unique_implementation
                )
                * 0.08
                + len(
                    unique_libraries
                )
                * 0.08
                + min(
                    syntax_count,
                    5,
                )
                * 0.10
            ),
        )

        if subset == "Github":
            score += 0.16
        elif subset == "ArXiv":
            score += 0.08
        elif subset == "StackExchange":
            score -= 0.08
        elif subset == "Pile-CC":
            score -= 0.15

        return {
            "accepted": True,
            "reason": "accepted",
            "score": round(
                float(score),
                5,
            ),
            "signals": sorted(
                set(
                    ai_signals
                    + engineering_signals
                    + implementation_signals
                    + library_signals
                )
            )[:24],
            "syntax_count": (
                syntax_count
            ),
        }

    def _best_technical_window(
        self,
        text,
        query,
        subset,
        max_chars=2200,
    ):
        windows = self._window_candidates(
            text,
            query,
            window_chars=max_chars,
        )

        best_window = None
        best_quality = None
        rejection_reasons = Counter()

        for raw_window in windows:
            window = self._strip_front_matter(
                raw_window
            )

            quality = self._technical_window_quality(
                query,
                window,
                subset,
            )

            if not quality.get(
                "accepted"
            ):
                rejection_reasons[
                    quality.get(
                        "reason",
                        "rejected",
                    )
                ] += 1
                continue

            if (
                best_quality is None
                or float(
                    quality.get(
                        "score",
                        0.0,
                    )
                )
                > float(
                    best_quality.get(
                        "score",
                        0.0,
                    )
                )
            ):
                best_window = window
                best_quality = quality

        if best_window is None:
            reason = (
                rejection_reasons.most_common(
                    1
                )[0][0]
                if rejection_reasons
                else "no_technical_window"
            )

            return {
                "accepted": False,
                "reason": reason,
                "window": "",
                "score": None,
                "signals": [],
            }

        return {
            "accepted": True,
            "reason": "accepted",
            "window": str(
                best_window
            ).strip()[
                :2200
            ],
            "score": best_quality.get(
                "score",
                0.0,
            ),
            "signals": best_quality.get(
                "signals",
                [],
            ),
            "syntax_count": best_quality.get(
                "syntax_count",
                0,
            ),
        }

    def _relevance_diagnostics(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")

        if not value.strip():
            return {
                "accepted": False,
                "reason": "empty",
                "signals": [],
            }

        source_policy = (
            self._whole_source_policy(
                query,
                value,
                subset,
            )
        )

        if not source_policy.get(
            "accepted"
        ):
            return {
                "accepted": False,
                "reason": (
                    source_policy.get(
                        "reason",
                        "source_policy_rejected",
                    )
                ),
                "signals": [],
            }

        technical = (
            self._best_technical_window(
                value,
                query,
                subset,
                max_chars=2200,
            )
        )

        if not technical.get(
            "accepted"
        ):
            return {
                "accepted": False,
                "reason": (
                    technical.get(
                        "reason",
                        "no_technical_window",
                    )
                ),
                "signals": technical.get(
                    "signals",
                    [],
                ),
            }

        return {
            "accepted": True,
            "reason": "accepted",
            "signals": technical.get(
                "signals",
                [],
            ),
            "score": technical.get(
                "score",
                0.0,
            ),
            "window": technical.get(
                "window",
                "",
            ),
            "syntax_count": technical.get(
                "syntax_count",
                0,
            ),
        }

    def _relevance(
        self,
        query,
        text,
        subset,
    ):
        result = self._relevance_diagnostics(
            query,
            text,
            subset,
        )

        if not result.get(
            "accepted"
        ):
            return None

        return float(
            result.get(
                "score",
                0.0,
            )
            or 0.0
        )


    def _whole_source_policy(
        self,
        query,
        text,
        subset,
    ):
        value = str(text or "")
        lower_query = str(query or "").lower()
        is_advanced = self._contains_any(
            lower_query,
            {"advanced"},
        )

        structure = self._whole_source_structure(
            value
        )
        scripts = self._source_script_profile(
            value
        )
        syntax_count = self._code_syntax_count(
            value
        )
        novice_signals = self._matched_aliases(
            value,
            NOVICE_SIGNALS,
        )

        if (
            subset == "Github"
            and (
                structure["github_urls"] >= 5
                or structure["repository_bullets"] >= 3
                or (
                    structure["markdown_links"] >= 7
                    and structure["raw_urls"] >= 7
                )
            )
            and syntax_count < 3
        ):
            return {
                "accepted": False,
                "reason": "repository_catalog",
            }

        if (
            is_advanced
            and subset == "StackExchange"
            and structure["question_prefix"]
            and not structure["answer_marker"]
        ):
            return {
                "accepted": False,
                "reason": "question_only_source",
            }

        if (
            is_advanced
            and novice_signals
            and subset == "StackExchange"
        ):
            return {
                "accepted": False,
                "reason": "novice_material",
            }

        # English request: substantial Hangul/CJK/Kana prose is rejected at the
        # whole-document level. Code/library names cannot dilute this signal.
        if (
            is_advanced
            and scripts["letters"] >= 180
            and (
                scripts["hangul"] >= 35
                or scripts["hangul_ratio"] >= 0.04
                or scripts["cjk"] >= 75
                or scripts["kana"] >= 75
            )
        ):
            return {
                "accepted": False,
                "reason": "non_english_dominant",
            }

        if (
            structure["traceback_markers"] >= 12
            and structure["prose_sentences"] < 8
        ):
            return {
                "accepted": False,
                "reason": "traceback_or_log_dump",
            }

        return {
            "accepted": True,
            "reason": "accepted",
        }

    def _technical_window_quality(
        self,
        query,
        text,
        subset,
    ):
        query = str(query or "")
        value = self._strip_front_matter(
            text
        )
        lower_query = query.lower()

        markup = self._markup_quality(
            value
        )
        if markup["reject"]:
            return {
                "accepted": False,
                "reason": "markup_or_metadata",
                "score": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(
                lower_query,
                {"python"},
            )
            and not self._contains_any(
                value,
                {"python"},
            )
        ):
            return {
                "accepted": False,
                "reason": "missing_python",
                "score": 0.0,
                "signals": [],
            }

        core_ai = self._matched_aliases(
            value,
            AI_CORE_SIGNALS,
        )
        frameworks = self._matched_aliases(
            value,
            AI_FRAMEWORK_SIGNALS,
        )
        engineering = self._matched_aliases(
            value,
            ADVANCED_ENGINEERING_SIGNALS,
        )
        implementation = self._matched_aliases(
            value,
            IMPLEMENTATION_SIGNALS,
        )
        libraries = self._matched_aliases(
            value,
            LIBRARY_SIGNALS,
        )
        coding = self._matched_aliases(
            value,
            CODING_ALIASES,
        )
        career = self._matched_aliases(
            value,
            GENERIC_CAREER_SIGNALS,
        )

        syntax_count = self._code_syntax_count(
            value
        )
        is_advanced = self._contains_any(
            lower_query,
            {"advanced"},
        )

        core_set = set(core_ai)
        framework_set = set(frameworks)
        engineering_set = set(engineering)
        implementation_set = set(implementation)
        library_set = set(libraries)

        implementation_strength = (
            len(implementation_set)
            + len(library_set)
            + min(syntax_count, 5)
        )

        if (
            self._contains_any(
                lower_query,
                AI_ALIASES,
            )
            and not (
                core_set
                or framework_set
            )
        ):
            return {
                "accepted": False,
                "reason": "missing_ai",
                "score": 0.0,
                "signals": [],
            }

        if (
            self._contains_any(
                lower_query,
                CODING_ALIASES,
            )
            and not coding
        ):
            return {
                "accepted": False,
                "reason": "missing_coding",
                "score": 0.0,
                "signals": [],
            }

        if is_advanced:
            # Strong executable AI code can pass with fewer prose concepts.
            strong_code = (
                syntax_count >= 5
                and len(framework_set) >= 1
                and len(engineering_set) >= 1
            )

            if (
                len(core_set) < 2
                and not strong_code
            ):
                return {
                    "accepted": False,
                    "reason": "insufficient_core_ai_depth",
                    "score": 0.0,
                    "signals": core_ai + frameworks,
                }

            if (
                len(engineering_set) < 2
                and not strong_code
            ):
                return {
                    "accepted": False,
                    "reason": "insufficient_engineering_depth",
                    "score": 0.0,
                    "signals": core_ai + engineering,
                }

            if implementation_strength < 3:
                return {
                    "accepted": False,
                    "reason": "insufficient_implementation_evidence",
                    "score": 0.0,
                    "signals": core_ai + engineering,
                }

            if (
                subset in {"PubMed Central", "PubMed"}
                and len(core_set) < 2
            ):
                return {
                    "accepted": False,
                    "reason": "domain_drift_or_weak_ai_core",
                    "score": 0.0,
                    "signals": core_ai + frameworks,
                }

            if (
                subset == "ArXiv"
                and not (
                    framework_set
                    or syntax_count >= 2
                )
            ):
                return {
                    "accepted": False,
                    "reason": "theory_without_implementation",
                    "score": 0.0,
                    "signals": core_ai + engineering,
                }

        if (
            career
            and syntax_count == 0
            and len(framework_set) < 2
        ):
            return {
                "accepted": False,
                "reason": "generic_career_or_news_material",
                "score": 0.0,
                "signals": [],
            }

        score = _cosine(
            query,
            value,
        )
        score += min(
            0.80,
            (
                len(core_set) * 0.12
                + len(framework_set) * 0.08
                + len(engineering_set) * 0.09
                + len(implementation_set) * 0.08
                + min(syntax_count, 5) * 0.10
            ),
        )

        if subset == "Github":
            score += 0.18
        elif subset == "ArXiv":
            score += 0.10
        elif subset == "StackExchange":
            score -= 0.08
        elif subset in {"PubMed Central", "PubMed"}:
            score -= 0.18
        elif subset == "Pile-CC":
            score -= 0.15

        return {
            "accepted": True,
            "reason": "accepted",
            "score": round(
                float(score),
                5,
            ),
            "signals": sorted(
                set(
                    core_ai
                    + frameworks
                    + engineering
                    + implementation
                    + libraries
                )
            )[:24],
            "syntax_count": syntax_count,
        }

    def _local_sql_predicates(
        self,
        query,
    ):
        lower = str(query or "").lower()
        predicates = []

        if self._contains_any(
            lower,
            AI_ALIASES,
        ):
            predicates.append(
                "("
                "contains(lower(text), 'machine learning') OR "
                "contains(lower(text), 'deep learning') OR "
                "contains(lower(text), 'neural network') OR "
                "contains(lower(text), 'transformer') OR "
                "contains(lower(text), 'language model') OR "
                "contains(lower(text), 'model training') OR "
                "contains(lower(text), 'inference')"
                ")"
            )

        if self._contains_any(
            lower,
            {"python"},
        ):
            predicates.append(
                "contains(lower(text), 'python')"
            )

        if self._contains_any(
            lower,
            {"advanced"},
        ):
            predicates.append(
                "("
                "contains(lower(text), 'pytorch') OR "
                "contains(lower(text), 'tensorflow') OR "
                "contains(lower(text), 'keras') OR "
                "contains(lower(text), 'scikit-learn') OR "
                "contains(lower(text), 'transformer')"
                ")"
            )
            predicates.append(
                "("
                "contains(lower(text), 'training') OR "
                "contains(lower(text), 'inference') OR "
                "contains(lower(text), 'evaluation') OR "
                "contains(lower(text), 'optimizer') OR "
                "contains(lower(text), 'loss function') OR "
                "contains(lower(text), 'attention') OR "
                "contains(lower(text), 'debugging') OR "
                "contains(lower(text), 'architecture') OR "
                "contains(lower(text), 'gpu') OR "
                "contains(lower(text), 'cuda')"
                ")"
            )

        return predicates

    def run(
        self,
        action,
        arguments,
    ):
        arguments = (
            arguments or {}
        )

        if action == "search_knowledge":
            return self.search_knowledge(
                arguments.get(
                    "query"
                ),
                arguments.get(
                    "limit",
                    5,
                ),
            )

        if action == "search_pile":
            return self.search_pile(
                arguments.get(
                    "query"
                ),
                arguments.get(
                    "limit",
                    5,
                ),
            )

        if action == "learn_from_pile":
            return self.learn_from_pile(
                arguments.get(
                    "query"
                ),
                arguments.get(
                    "limit",
                    5,
                ),
                bool(
                    arguments.get(
                        "auto_cache",
                        False,
                    )
                ),
            )

        if action == "pile_cache_status":
            return (
                self.pile_cache_status()
            )

        if action == "download_pile_cache":
            return (
                self.download_pile_cache(
                    arguments.get(
                        "shards",
                        1,
                    )
                )
            )

        if action == "sync_research_files":
            return (
                self.sync_research_files()
            )

        if action == "add_knowledge":
            return self.add_knowledge(
                arguments.get(
                    "text"
                ),
                title=arguments.get(
                    "title",
                    "",
                ),
                source=arguments.get(
                    "source",
                    "manual",
                ),
                source_ref=arguments.get(
                    "source_ref",
                    "",
                ),
            )

        if action == "knowledge_stats":
            return self.stats()

        raise KeyError(action)

    def close(self):
        with self._db_lock:
            try:
                self.conn.close()
            except Exception:
                pass
