# Changelog

## phase1-v2 — PH1-FIX-001: sections per heading span (2026-10-27)

Manual QA (PH1-QA-001) found that one section per cell mislabelled 24.5% of markdown text: long
cells hold several headings but carried only the first, and cells starting with a plain title or
`---` got no section. Ingestion now assigns sections per heading span.

### Sections

- Every non-empty markdown cell is split at its headings into contiguous **spans**
  (`cells.jsonl` → `spans`). Each span has `span_id` (`nb_45_cell_000_span_003`), `kind`,
  `heading_level`, `heading_text`, `section_title`, `section_path`, `content`,
  `char_start`/`char_end` and `contains_math`/`contains_table`/`contains_list`.
- Offsets index into the cell's `content`. Spans are views over it: concatenating them in order
  reproduces `content` exactly. `content` itself is unchanged from phase1-v1 (same conservative
  cleaning; `source_hash` still hashes the raw source).
- Span kinds:
  - `heading`: starts at a structural heading.
  - `label`: starts at a block label (`Question`, `Choices`, `Code`); the section does not change.
  - `continuation`: text before the cell's first heading; it continues the previous section.
  - `preamble`: text before the notebook's first heading; `section_path: []`, title `Preamble`
    (replaces "Untitled / beginning of notebook").
- A leading slice holding only blank lines or thematic breaks (`---`) is merged into the first
  heading's span. Plain title lines are never promoted to headings.
- Supported headings: ATX (`#`–`######`, up to 3 leading spaces, optional closing `#`s), Setext
  (`===` → level 1, `---` under a paragraph line → level 2) and HTML `<h1>`–`<h6>`, including when
  wrapped in tags such as `<center>`. `#text` without a space is not a heading (CommonMark).
  Lines inside fenced code blocks are never headings; fences close only on the same character
  with at least the opening length.
- New cell fields: `span_count`, `has_multiple_sections`, `section_accuracy_status`
  (`ok`, `fixed` = cell spans several sections and is now split, `preamble`).
- `section` / `section_path` stay for compatibility. For markdown cells they now come from the
  span holding the most text; code cells take the section governing their position. New code
  should read `spans`.

### Outputs

- Text outputs get an `output_role`: `teaching_text`, `result`, `log`, `dataframe_dump` or
  `error`, decided on the full text before truncation. Truncation is the separate `truncated`
  flag plus `original_length`, so the kind of output is not lost when it is cut.
- Limits by role: `teaching_text` and `result` keep up to 20,000 characters; `log`,
  `dataframe_dump` and `error` are cut at 4,000. nb_30_cell_027's printed lesson (4,635 chars,
  BCE / softmax / cross-entropy) is now kept in full.
- `teaching_text` means printed prose. It includes printed lessons (nb_30, nb_31, nb_33) and also
  NLP demo outputs that print sample documents or reviews (nb_45, nb_47, nb_49–nb_53).
- ANSI cursor codes such as `\x1b[?25l` are now stripped from outputs (16 install/download logs).

### Report and checks

- The "section coverage" check is replaced by **Section accuracy** (< 2% of markdown text under
  the wrong section) and **Span integrity** (contiguous spans, exact offsets, reconstruction,
  every span has a section or is preamble).
- Accuracy uses an independent line-by-line walk of the headings across cells, counting
  non-whitespace characters. The same walk scores the phase1-v1 rule for comparison:
  **24.53% → 0.00%** mislabelled (1,126,348 markdown characters).
- The report adds per-notebook mislabel rates, the worst cells, output roles, and the PH1-QA-001
  statuses. `notebooks.jsonl` adds `span_count`, `multi_section_cells`, `preamble_only_cells`,
  `section_mislabel_rate`, `legacy_section_mislabel_rate`, `teaching_outputs` (and drops
  `section_coverage`). `corpus_inventory.csv` replaces `section_coverage` with `span_count`,
  `multi_section_cells`, `section_mislabel_rate`.

### Not changed

- Verified against a phase1-v1 snapshot: no cell `content`, `source_hash` or detection flag changed
  in any of the 6,432 cells. 8 cells gain headings that v1 missed (ATX indented by 1–3 spaces); no
  heading was lost. Output text changed in exactly two ways: 16 install/download logs lost ANSI
  cursor codes (in 6 already-truncated logs this shifts the 4,000-character window), and 10
  outputs previously cut at 4,000 characters are longer now (6 kept in full, 4 cut at 20,000).
- Tools/Resources inventories (`src/assets.py`) were built on phase1-v1 cells and are not
  regenerated in this ticket.

### Tests

`tests/test_section_spans.py` (17 tests):
- Regressions on `nb_45_cell_000`, `nb_30_cell_001` and `nb_30_cell_027`.
- A synthetic fixture covering preamble text, a leading `---`, ATX/Setext/HTML headings,
  `#` inside code fences, LaTeX with `$`, a table and MCQ labels.
- Reconstruction, output-role and truncation-limit tests.
- A mutation test showing the accuracy check detects a mislabelled span.
