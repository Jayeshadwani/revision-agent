# Chunking (PH2-CHUNK-001)

Chunks are the units the retriever will index. There are three chunk types, built by
`src/chunk_builder.py`; the merge and split logic lives in `src/chunking.py`.

```
python src/ingestion.py        # cells, spans, content roles
python src/assets.py           # tools, resources, tool–concept links
python src/chunk_builder.py    # chunks + chunking_report.md
```

All outputs go to `data/processed/`, which stays local.

| File | ID | One record per |
|---|---|---|
| `concept_chunks.jsonl` | `CON_000001` | group of teaching spans |
| `tool_chunks.jsonl` | `TOOLCHUNK_000001` | answer-suitable Tool |
| `resource_chunks.jsonl` | `RESCHUNK_000001` | attachable Resource |
| `chunk_exclusions.jsonl` | — | record that could have been a chunk but isn't, with the reason |
| `chunking_report.md` | — | coverage, size distribution, issues, manual review |

IDs are numbered in corpus order. The same inputs always give the same IDs and content. If the
inputs change (new roles, new tools), the IDs can shift.

## Concept chunks

- **Input.**
  - Spans with `content_role = teaching` and `retrieval_eligible = true`.
  - Heading-only, image-only and formatting-only spans are context, not chunks.
  - Spans in support roles (quiz, instructor_note, agenda, business_context, rhetorical_question,
    preamble) stay in `spans.jsonl` and are never chunked.
- **Stripping.**
  - Some teaching spans carry an `embedded_instructor_note` or `embedded_quiz` flag (PH1-ROLE-001).
    For these, the note block or quiz tail is removed before chunking.
  - A note that is one bullet of a teaching list removes only that bullet.
  - The kept character ranges are recorded in `source_segments`.
- **Merging** is greedy and keeps notebook order:
  - Text from the same section keeps joining a chunk while it fits in 760 tokens. That is the
    800-token target minus room for the breadcrumb.
  - A related section can join while the chunk is still below 300 tokens. Related means parent,
    child or sibling under the same parent.
  - After that pass, a chunk still below 300 tokens joins a related neighbour if the result fits.
  - Text never merges across notebooks or across unrelated sections.
- **Splitting.**
  - A span longer than the budget is split at paragraph boundaries.
  - Fenced code, `$$` math blocks and tables are never cut. A single block that is larger than the
    budget stays whole and is flagged `is_oversized` if it exceeds 1,200 tokens.
  - Overlap is used only inside a split span that contains math: the next piece repeats the last
    paragraph of the previous piece, if that paragraph is at most 20% of the budget.
- **Text.**
  - `raw_text` is the exact source text, so it can be rebuilt from `source_segments`.
  - `content` is what gets embedded:
    - It starts with the breadcrumb:
      ```
      Notebook: Classification metrics
      Section path: Metrics > Precision
      ```
    - Images become `[Image RES_xxxx]`.
    - HTML styling tags are removed outside code.
  - The breadcrumb leaves out quiz-question and agenda headings that authors placed above lesson
    sections. `section_path` keeps the full structural path.
- **Flags.**
  - `is_merged`, `is_split`, `has_overlap`.
  - `is_tiny` (< 100 tokens) and `is_oversized` (> 1,200 tokens).
  - `stripped_support_content`.
  - `is_duplicate`: an exact repeat of earlier text. Its `duplicate_of` is set and it is not
    retrieval-eligible.

Token counts are estimates, because no tokenizer is installed. The estimate counts word pieces of
up to 8 characters plus punctuation. Swap in the embedding model's tokenizer when there is one.

## Tool chunks

- One chunk per Tool with `quality.suitable_for_answer = true`.
- One-line tools with no output are excluded, with the reason recorded.
- `code` is the cell exactly as stored. `content` holds:
  - the breadcrumb
  - the title, type and purpose
  - the description, when it came from the notebook
  - the libraries
  - the code, in a fenced block
- Duplicates:
  - The same multi-line code copied into another notebook, or repeated in the same section, gets
    `duplicate_of` and is not retrieval-eligible.
  - The same code re-run under another section, or a 1–2 line snippet that also appears in
    another notebook, gets `repeats_code_of`. It keeps its own context and stays eligible.

## Resource chunks

- One chunk per Resource with `retrieval_status = attachable`, meaning it is linked to a concept
  span or a tool.
- `pending_vision` resources are excluded, with the reason recorded.
- Nothing about the image itself is generated:
  - `vision_status` is `pending` for every resource.
  - `content` says the image content was not extracted.
  - `retrieval_eligible` stays false until an OCR/VLM pass fills `vlm_caption` or `ocr_text`.
- Attachable resources can be shown next to the concept and tool chunks they link to.

## Links

These come from `tool_concept_links.jsonl`.

| Relationship | Concept chunk field | Tool chunk field | Attached automatically |
|---|---|---|---|
| implements, demonstrates, visualizes | `linked_tool_ids`, `linked_tool_chunk_ids` | `linked_concept_chunk_ids` | yes |
| supports | `secondary_tool_ids` | `secondary_concept_chunk_ids` | no |
| uncertain | `uncertain_tool_ids` | `uncertain_concept_chunk_ids` | no |

Only answer-suitable tools, which are the ones with tool chunks, are attached.

A resource links to:
- the concept chunks that contain its `linked_concept_span_ids`
- for a plot, the concept chunks its tool *visualizes*

The concept chunk lists it under `linked_resource_ids`.
