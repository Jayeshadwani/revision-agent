# Changelog

## phase2 — PH2-CHUNK-001 (issue #3): Concept, Tool and Resource chunks (2026-10-27)

### Chunks

- New `src/chunking.py` (merge and split logic) and `src/chunk_builder.py` (CLI, linking, report).
  They write `concept_chunks.jsonl`, `tool_chunks.jsonl`, `resource_chunks.jsonl`,
  `chunk_exclusions.jsonl` and `chunking_report.md`. See `docs/chunking.md`.
- Results:
  - Concept chunks: 862, covering all 3,025 eligible teaching spans.
    - Median 310 tokens: 433 are within 300–800, 426 are smaller and 3 are larger.
    - 115 are tiny: isolated short sections that are flagged rather than merged across a section
      boundary.
    - Embedded instructor notes and quiz text are stripped from 26 chunks.
  - Tool chunks: 1,322, one per answer-suitable Tool.
    - 793 are attached to concepts through implements/demonstrates/visualizes links.
    - 10 copies are flagged `duplicate_of` and are not retrieval-eligible.
  - Resource chunks: 1,318, one per attachable Resource.
    - All are `vision_status: pending` and not retrieval-eligible.
    - The 108 `pending_vision` resources are excluded.

### Content-role fixes found while checking chunks

- **Code.**
  - Statements inside `if` / `with` blocks are now checked, and shell `!gdown` / `!wget` /
    `!pip` lines count as loading or setup.
  - 6 cells were re-labelled from tool_demonstration to non-tool roles:
    - 4 data loaders that use `!gdown` / `!wget`.
    - 1 directory set-up.
    - The GPU-conditional hyperparameters cell (V80 in the PH1-ROLE-001 validation sample).
- **Markdown.**
  - A heading inside a quiz container section ("QUIZ", "Quiz 2", "MCQs") is now a quiz.
  - A topic list under an Agenda/Content heading is now an agenda item.
  - A question written as a heading, or a lesson under an Agenda H1, is unaffected.
  - 3 spans changed role.
- **Knock-on changes.**
  - The Tools inventory is down to 1,453, and tool IDs after nb_18 shift.
  - The golden prompt reference `TOOL_0604` becomes `TOOL_0602`, mapped by source cell.
  - The PH1-ROLE-001 QC row V80 is marked as fixed.

### Tests

- `tests/test_chunking.py` has 20 tests covering the ticket's ten cases:
  - tiny-span merging
  - no merging across notebooks or unrelated sections
  - source reconstruction
  - tool provenance
  - pending-vision exclusion
  - relationship-gated attachment
  - support-content exclusion
  - unique IDs
  - stable reruns
- It also has split/overlap/stripping primitives and corpus checks.
- `tests/test_content_roles.py` gains 4 tests for the new role rules.

## phase1-v2 — Issue #1: Tools and Resources inventories (2026-10-27)

The Tools and Resources inventories are now built from the classified corpus
(spans + content roles). They replace the phase1-v1 inventories that `src/assets.py` used to build.

### Modules

- `src/tools_inventory.py` → `tools.jsonl` and `tool_exclusions.jsonl`.
- `src/resources_inventory.py` → `resources.jsonl`, `resources_report.md` and `images/`.
- `src/tool_concept_linker.py` → `tool_concept_links.jsonl`.
- `src/assets.py` now holds the shared helpers. Its `run()` builds all three and writes
  `tools_report.md`: `python src/assets.py`.

### Tools

- One Tool per retrieval-eligible code cell in a tool role: 1,459 Tools.
- Every other code cell (675) is in `tool_exclusions.jsonl` with its role and a reason. That
  includes the 4 tool-role cells flagged `invalid_syntax`.
- Each Tool has:
  - Type, title, description and purpose.
  - Inputs and outputs.
  - Libraries, concepts and topic IDs.
  - Source (notebook, section, cell).
  - Quality flags: self-contained, has output, nearby explanation, parses, complexity, and
    suitable-for-answer with reasons.
  - The IDs of the explanation spans it came from.
- 1,328 are suitable for answers as they are. The other 131 are one-line cells with no output.

### Resources

- One resource per image: 1,102 markdown images (all 972 image-referencing cells) and 324 plot
  outputs.
- Each resource records:
  - The span holding the image.
  - Its caption: alt text, the same span or nearby markdown.
  - Linked concept spans and tools.
  - Availability: embedded / google_drive / external_url / missing.
  - Retrieval status.
  - A vision priority for the later OCR/VLM pass.
- Image content is never read (`content_extracted: false`). A type is set only from structural
  evidence:
  - plot: code output.
  - decorative: ≤ 48 px.
  - external_reference: hot-linked from a third-party site.
  - The author's alt text, when it names a type.
- Everything else is `unclassified` (1,082), and 1,055 of those are queued at high vision
  priority.
- `Screenshot_…png` filenames are kept as a `capture_hint`, not used as a type. A spot check
  found handwritten formulas and slides behind such names.

### Tool–Concept links

- Each candidate is a teaching, eligible span in the tool's notebook, scored from evidence:
  - Same section, or closest ancestor section with prose.
  - Proximity before the tool.
  - Being the tool's nearest explanation.
  - Shared function/method names.
  - Shared topic.
- Links ≥ 0.55 get implements / demonstrates / visualizes from the tool's role, but only with
  structural evidence; otherwise `supports`.
- Below 0.55, one `uncertain` link is kept if ≥ 0.35; weaker evidence makes no link.
- Result:
  - 862 tools linked.
  - 358 with only an uncertain link.
  - 239 unlinked. None of these has prose in its section.

### Evaluation

- Tools are renumbered because only eligible cells are Tools now.
- `evaluation/golden_prompts.jsonl` moves `TOOL_0187` → `TOOL_0136` and `TOOL_0857` →
  `TOOL_0604`, mapped by source cell. Resource IDs are unchanged.

### Review

- `data/processed/qa/inventory_review_sample.csv` holds 20 Tools (4 per type) and 20 Resources
  (stratified).
- Tools: type, provenance and flags 20/20. Links 18/19, first pass: one proximity +
  identifier link was typed `implements`. Fixed by the structural-evidence rule.
- Resources: 20/20. 0 critical misclassifications.

### Tests

- `tests/test_tools_inventory.py` and `tests/test_resources_inventory.py` share a synthetic
  notebook in `tests/inventory_fixture.py`. Corpus checks run locally.
- `tests/test_assets.py` now covers only the shared helpers.

## phase1-v2 — PH1-ROLE-001: content roles (2026-10-27)

Every markdown span and code cell now has a `content_role`, so chunking and retrieval can keep
instructor notes, quizzes, agendas, setup code and data loaders out of default answers.

### Fields

- Spans (`cells.jsonl` → `spans`, and the new `data/processed/spans.jsonl`) and code cells get
  `content_role`, `role_confidence`, `role_method` (`rule` | `llm` | `manual`), `role_reason`,
  `retrieval_eligible`, plus:
  - `retrieval_index`: `concepts` | `tools` | `resources` | `support` | `none`. This says where an
    excluded record still lives (e.g. a quiz goes to `support`, an image-only span to `resources`).
  - `role_flags`: `embedded_instructor_note`, `embedded_quiz`, `invalid_syntax`,
    `instructor_optional_teaching`. These mark teaching records that need stripping at chunking.
- Outputs get `retrieval_eligible` (`teaching_text` and `result` only).
- Raw cells (markdown cells without spans, raw cells) carry no role.

### How roles are assigned (`src/content_role_classifier.py`)

1. **Rules** decide most records. Order matters:
   - Markdown: preamble → instructor note → quiz/MCQ/practice → agenda → assessment links →
     business heading / scenario framing → logistics → heading-only / image-only /
     formatting-only → question prompts → teaching.
   - Code: empty/comments → setup (pip, config, seeds, locale) → shell inspection → timing →
     statement-level plumbing (every statement is an import, config, loader, literal constant
     or display → `data_loading` / `environment_setup` / `non_teaching`) → bare inspection →
     the shared Tools rules from `src/assets.py`.
2. **Records the rules cannot decide** are queued: instructor markers mixed with teaching text,
   lettered options without an answer key, and code that is not valid Python. They were labelled
   offline from the text plus section path only (51 labels in `data/labels/role_labels.jsonl`,
   local). Each label is keyed by record id and a content hash; a stale label is ignored and the
   record goes back to the queue. `manual` labels override rules.
3. `python src/content_role_classifier.py --export-queue q.jsonl` writes anything still unlabelled.
   `python src/ingestion.py` runs the classifier as part of the pipeline.

### Retrieval eligibility

- Eligible:
  - `teaching` spans with real text.
  - `tool_*` and `visualization` cells, unless flagged `invalid_syntax`.
- Not eligible:
  - Heading-only and formatting-only spans (kept as context).
  - Image-only spans and image credits (Resources).
  - Every support role.
- `business_context`: the first occurrence in a notebook goes to `support`, repeats to `none`.

### Results

- 5,308 spans and 2,134 code cells classified: 7,391 by rule, 51 by label, 0 unknown, empty queue.
- QC, all in `data/processed/qa/content_role_review_sample.csv`:
  - Ticket's stratified 100: first pass 93% correct with 2 critical false positives (a timing print
    and a locale hack labelled as tools). Both are fixed. After fixes it scores 100%, but that is
    in-sample.
  - After the rules were frozen, 100 fresh random retrieval-eligible records were checked: 97%
    correct, 1 critical false positive. That was GPU-conditional hyperparameter constants inside
    an `if`. The other two errors were plotting-helper calls labelled `tool_demonstration`.

### Tests

`tests/test_content_roles.py` has 34 tests:
- Each markdown and code rule.
- Label resolution, stale-hash invalidation, manual override and taxonomy validation.
- Corpus checks (run when `data/processed` is built):
  - Every record has the role fields.
  - Unknown rate ≤ 10%.
  - Excluded roles are never eligible.
  - Outputs have eligibility.
  - `spans.jsonl` matches `cells.jsonl`.

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
