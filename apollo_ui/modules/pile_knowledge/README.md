# Apollo Pile Knowledge v1.3

This version is designed for the failure:

`TimeoutError: The read operation timed out`

from Hugging Face Dataset Viewer `/search`.

## Search path

1. Try the online Pile search with a longer timeout and a maximum of two queries.
2. If online search fails, use any local Pile Parquet cache immediately.
3. For explicit Chat `learn from The Pile ...` requests, Apollo may automatically
   download the first Lite cache shard when all remote failures are timeouts.

## Local Lite cache

The first shard is approximately 266 MB.

Location:

`storage/pile_cache/0000.parquet`

Apollo can expand the cache one shard at a time. The current Hugging Face partial
preview is represented by ten shards totalling roughly 2.6 GB.

The download uses a `.part` file and HTTP Range requests where supported, so an
interrupted cache download can resume.

## DuckDB

Local Parquet searching uses DuckDB.

`requirements.txt` now includes:

`duckdb>=1.1`

After upgrading an existing Apollo install, run:

`install.bat`

once before using local Pile cache search.

## Query typo normalization

Common user spellings are normalized before retrieval, including:

`codeing -> coding`

`nural -> neural`

`programing -> programming`

## Accuracy

Local cache search still uses Apollo's relevance gate. A query for AI coding must
match both AI/ML material and programming/software material before the passage can
be compiled into Apollo's knowledge database.
