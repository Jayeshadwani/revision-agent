# Evaluation set

`golden_set.jsonl` is the single source of truth: 340 test cases (schema `v1`), one JSON object per line. They break down into 320 topic questions (8 for each of the 40 topics, IDs `T01-01` … `T40-08`) and 20 boundary cases (`B01` … `B20`), which test partial answers and refusals.

[`response_templates.md`](response_templates.md) defines how the agent must format each answer and how answers are scored.

```bash
python scripts/eval_report.py              # counts by difficulty, type, template, topic, completeness
python scripts/eval_report.py --check      # schema validation (exits 1 on errors)
python scripts/eval_report.py --csv x.csv  # flat CSV for a spreadsheet ('|' separates list items)
```

## Status

All 340 records pass schema validation. **20 are complete**, meaning they have an answer key and source cells (or are refusals with an answer key). The other 320 still need `expected_answer` and `expected_sources` filled in before they can be scored. `expected_chunk_ids` is empty everywhere until the chunk index exists. Refusal labels stay provisional until corpus absence has also been checked against image content.

## Record schema

```jsonc
{
  "question_id": "T12-01",                 // T<topic>-<slot>, or B01–B20
  "version": "v1",
  "question": "Explain precision and recall. Include an example if available.",
  "question_type": "definition",           // enum below; picks the template
  "difficulty": "medium",                  // easy | medium | hard
  "difficulty_score": 0.465,               // 0–1, rubric below
  "expected_answer": {
    "summary": "",                          // reference answer in a sentence or two
    "key_points": ["…", "…"],               // what a correct answer must contain
    "required_sections": ["answer", "intuition", "sources"],
    "optional_sections": ["mathematical_form", "implementation_from_notes", "common_mistakes"]
  },
  "expected_sources": [                    // empty for refusals
    { "notebook_id": "nb_14", "notebook_title": "Classification metrics",
      "section": "What can be a good metric?", "cell_ids": [5], "source_type": "markdown" }
  ],
  "expected_chunk_ids": [],                // filled once indexing exists
  "expected_topics": ["Classification evaluation"],
  "requirements": {
    "requires_math": false, "requires_code": false, "requires_comparison": false,
    "requires_multi_notebook": false, "requires_recommendation": false,
    "requires_step_by_step": false, "partial_evidence_only": false, "should_refuse": false
  },
  "answer_template": "concept_explanation",
  "evaluation": {
    "min_faithfulness": 0.9, "min_correctness": 0.8,
    "min_context_recall": 0.75, "min_citation_validity": 1.0,
    "human_rubric": { "retrieval": 2, "grounding": 2, "correctness": 2,
                      "structure": 2, "citation_quality": 2 }
  },
  "notes": ""                              // reviewer guidance / edge cases
}
```

### Allowed values

| Field | Values |
|---|---|
| `question_type` | `definition`, `formula_recall`, `math_derivation`, `concept_explanation`, `comparison`, `code_implementation`, `code_explanation`, `debugging`, `multi_notebook_synthesis`, `topic_recommendation`, `revision_plan`, `refusal`, `partial_answer` |
| `answer_template` | `concept_explanation`, `formula`, `mathematical_explanation`, `comparison`, `code_implementation`, `code_explanation`, `misconception`, `synthesis`, `topic_recommendation`, `revision_plan`, `refusal`, `partial_answer` |
| `difficulty` | `easy`, `medium`, `hard` |
| `source_type` | `markdown`, `code`, `output`, `mixed` |

- `notebook_id` is `nb_<number>`, taken from the notebook's file-name prefix (for example `14 - Classification metrics.ipynb` → `nb_14`).
- `cell_ids` are 0-based positions in the notebook's cell list. Colab shows them as `cell_id + 1`.
- §2 of `response_templates.md` gives the mapping from question type to template and sections.

### Validation rules (`--check`)

- `question_id` is unique, and `question` is non-empty.
- `question_type`, `answer_template`, `difficulty` and `source_type` use allowed values. `difficulty` matches the band of `difficulty_score`.
- `should_refuse` is true exactly for `refusal`, and refusals have no `expected_sources`. `partial_evidence_only` is true exactly for `partial_answer`.
- `requires_math` uses a math template or a required math section.
- `requires_multi_notebook` with sources needs at least two distinct `notebook_id`s.
- Every non-refusal template requires `sources`, and no section is both required and optional.

A record with no answer key or no sources is valid but incomplete. The report counts these separately rather than treating them as errors.

## Question types per topic

Each topic gets 8 slots: definition; formula or derivation (or practical reasoning, where a topic has no math objective); comparison; code implementation; code explanation; debugging/misconception; multi-notebook synthesis; topic recommendation. A slot can be relabeled or removed if source review shows it doesn't apply. Implementations must be retrieved from notebook code, never generated.

## Difficulty rubric

Difficulty measures what the agent has to do. It does not measure answer length, topic importance or whether the corpus can answer the question.

```
difficulty_score = 0.35 × cognitive_operation + 0.25 × retrieval_breadth
                 + 0.20 × math_demand        + 0.20 × ambiguity_inference

easy < 0.40 ≤ medium < 0.70 ≤ hard
```

| Factor | Low | Middle | High |
|---|---|---|---|
| Cognitive operation | 0.25 recall/restate | 0.65 explain/apply | 0.95–1 analyze/evaluate/synthesize/derive |
| Retrieval breadth | 0.25 one evidence unit | 0.50–0.65 several related units | 0.80–1 multiple evidence groups or notebooks |
| Math demand | 0 none; 0.25 formula meanings | 0.45–0.50 interpret or calculate | 0.90–1 proof or multi-step derivation |
| Ambiguity / inference | 0.15 directly stated | 0.40–0.65 bounded interpretation | 0.70–0.90 judgment, separating partial support |

Only the final score is stored, not the individual factor values. Retrieval breadth is estimated, because chunking isn't built yet, so re-score a question if evidence mapping changes what it needs. The current split (24 easy / 166 medium / 150 hard) leans hard because the set deliberately includes many comparison and synthesis questions.

## Completing a question (before it is scored)

1. Map it to exact notebook cells in `expected_sources`.
2. Write `summary` and `key_points`, keeping stated facts separate from bounded deductions.
3. Math: verify formulas, variable definitions and each requested step. If steps are missing, retype the question as `partial_answer`.
4. Comparison: require evidence for both sides, and don't infer universal runtime or accuracy rankings.
5. Synthesis: require at least two notebooks that each contribute a distinct necessary fact; otherwise retype the question.
6. Recommendation: accept only evidence-backed relationships. Belonging to the same family is not a prerequisite.
7. Refusal: search synonyms and inspect image content before asserting that something is absent.

## Split policy

Hold out about 20% as test questions, but only after answer keys are done. Keep paraphrases and linked boundary/core pairs (for example `T12-01` and `B01`) on the same side of the split. The whole set has been seen during development, so a truly blind test will need a later batch written independently.
