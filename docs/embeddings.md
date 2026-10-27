# Embeddings and vector index (PH3-EMBED-001)

This step embeds the retrieval-eligible Concept and Tool chunks with OpenAI
`text-embedding-3-small` and stores them in a local Qdrant collection.

| Module | Role |
|---|---|
| `src/embeddings.py` | Config, model tokenizer (tiktoken), OpenAI embedder (batching, retries), the text embedded for each chunk |
| `src/vector_index.py` | `QdrantIndex` (local mode) and `MemoryIndex` (same interface, used by tests) |
| `src/index_builder.py` | Idempotent sync, health checks, `embedding_report.md`, spot-check searches |

## Running it

```bash
pip install openai tiktoken qdrant-client
export OPENAI_API_KEY=...            # never commit it

python src/chunk_builder.py          # PH2 output must be current
python src/index_builder.py --dry-run     # token counts, diff, cost; no API calls
python src/index_builder.py               # embed + index
python src/index_builder.py --spot-check  # 10 QA searches -> data/processed/index_spot_check.md
```

Outputs (all local):

- `data/index/qdrant/`: the collection `revision_agent_v1`.
- `data/index/manifest.json`: model, version, dimensions, tokenizer, corpus fingerprint, counts.
- `data/processed/embedding_tokens.jsonl`: per chunk, the tokenizer count, flag and content hash.
- `data/processed/embedding_report.md`: coverage, token usage, cost and index health.

The exit code is 1 if any chunk failed to embed, and 2 if a package, the API key or a matching
collection is missing.

## Configuration

| Setting | Value |
|---|---|
| model | `text-embedding-3-small` (OpenAI) |
| dimensions / distance | 1536 / cosine |
| batch | 128 inputs, at most 250k tokens per request |
| max input | 8,192 tokens: a chunk above it fails loudly and is never truncated |
| safe threshold | 1,500 tokens: chunks above it are flagged in the report |
| embedding_version | `v1` → collection `revision_agent_v1` |
| price | 0.02 USD per 1M tokens (list price; check before relying on the estimate) |

## What is embedded

- **Concept chunks**: the chunk's `content`, which is the breadcrumb plus the merged teaching text.
- **Tool chunks**:
  ```
  Tool: <title>
  Purpose: <purpose>
  Description: <description>            (only when it came from the notebook)
  Notebook: <title>
  Section path: <a > b > c>
  Libraries: <libs>

  Tool code:
  ```python
  <code exactly as stored>
  ```
  ```
- **Not embedded:**
  - resource chunks (vision pending)
  - chunks with `retrieval_eligible = false` (duplicates)
  - anything in a support role, since the chunk files never contain it

The exact text sent is stored in each payload as `text`, so retrieval can show it without
another lookup.

## Payload

Every point carries the fields that identify and filter it:
- **Identity:** `chunk_id`, `chunk_type`, `notebook_id`, `notebook_title`, `section_path` (a
  string; `section_path_list` holds the list).
- **Filter fields:** `content_role` (`teaching` or the tool type) and `contains_math`.
- **Embedding details:** `token_count`, `tokenizer`, `embedding_model`, `embedding_version`,
  `embedding_dimensions`.
- **Versioning:** `corpus_fingerprint` and `content_hash`.
- **Provenance and text:** `source_cell_ids`, `retrieval_eligible`, `text`.

On top of these:
- **Concept points** add `contains_latex`, `contains_table`, `source_span_ids`, `linked_tool_ids`,
  `linked_tool_chunk_ids`, `linked_resource_ids`, `is_tiny` and `is_oversized`.
- **Tool points** add `tool_id`, `tool_type`, `title`, `language`, `libraries`,
  `linked_concept_chunk_ids` and `linked_resource_ids`.

**Payload indexes:** `chunk_type`, `notebook_id`, `content_role`, `contains_math`,
`embedding_model`, `embedding_version` and `retrieval_eligible`. Qdrant's local mode accepts
these but filters by scanning, which is fine at about 2k points. The same indexes take effect on
a Qdrant server.

**Point IDs:** Qdrant only accepts integer or UUID IDs. Each point's ID is a UUIDv5 of the chunk
ID (`vector_index.point_id`), and the chunk ID is also stored in the payload.

## Idempotency

`content_hash` is a hash of model, dimensions, version and embedded text.

| Situation | Action |
|---|---|
| New chunk | Embed and upsert |
| Embedded text changed | Re-embed and upsert |
| Unchanged | Skip. If only metadata changed (links, corpus fingerprint), the payload is overwritten without re-embedding |
| Chunk no longer present | Delete its point |
| Collection holds another model or version | Refuse. Bump `embedding_version` (new collection) or run `--rebuild` |
| Pending-vision resource | Never loaded |

A failed batch (after up to 5 retries on rate-limit, timeout or 5xx errors) is recorded in the
report and not upserted. The next run picks it up again as new.

## Tests

`tests/test_embeddings.py` and `tests/test_vector_index.py` cover the ticket's 12 cases. They need
no network or API key: OpenAI is faked, and vectors come from a deterministic `HashEmbedder`. The
index tests run on `MemoryIndex`, and again on Qdrant's in-memory mode when `qdrant-client` is
installed. The tokenizer test runs when `tiktoken` is installed.
