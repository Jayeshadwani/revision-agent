# Evaluation prompts

There are two files, both in the same `v1` schema, one JSON object per line:

| File | Records | Purpose | Answer keys |
|---|---:|---|---|
| `golden_prompts.jsonl` | 20 | End-to-end evaluation of retrieval and generation (answer, format, citations, refusal) | Complete: `key_points` plus verified `expected_sources` (refusals have no sources) |
| `retrieval_prompts.jsonl` | 320 | Retrieval-quality evaluation across all 40 topics | Deferred; `expected_answer` and `expected_sources` filled later |

Each record is a realistic user prompt, such as "Explain precision and recall" or "I'm revising KMeans, what next?". The golden set is the first reviewed batch: 15 topic prompts plus boundary cases `B01`–`B05`. The retrieval set holds the other topic prompts (`T01-01` … `T40-08`) and boundary cases `B06`–`B20`. A prompt moves from the retrieval set to the golden set once its answer key and sources are verified.

Prompts can point at the three kinds of corpus assets: concept chunks (`expected_chunk_ids`, once chunking exists), tools (`expected_tool_ids`, `TOOL_0001`…) and resources (`expected_resource_ids`, `RES_0001`…). Tools and resources are built locally by `src/assets.py` (issue #1). IDs are numbered in corpus order, so they stay stable while the notebooks and content roles don't change; a change in which cells are tools renumbers them, and the references here must be migrated (by source cell).

[`response_templates.md`](response_templates.md) defines how the agent must format each answer and how answers are scored.

```bash
python scripts/eval_report.py                        # summary of both sets
python scripts/eval_report.py --set golden           # one set only
python scripts/eval_report.py --check                # validate both (exits 1 on errors)
python scripts/eval_report.py --set retrieval --csv x.csv   # flat CSV ('|' separates list items)
```

## Status

- **Golden set:** all 20 prompts are complete. It has no `tool_explanation` or `multi_notebook_synthesis` samples yet. 3 prompts link to tools and 2 to resources; both resource-linked prompts (T05-02, T23-03) rely partly on images hosted on Drive or a CDN that are not available offline.
- **Retrieval set:** all 320 records are schema-valid, but none has an answer key or source cells yet. Until `expected_sources` (and later `expected_chunk_ids`) are filled in, these prompts can only be used for manual inspection of what retrieval returns, not for scored recall@k.
- `expected_chunk_ids` is empty in both sets until the chunk index exists.
- Refusal labels stay provisional until corpus absence has also been checked against image content.

## Record schema

```jsonc
{
  "prompt_id": "T12-01",                   // T<topic>-<slot>, or B01–B20
  "version": "v1",
  "prompt": "Explain precision and recall. Include an example if available.",
  "prompt_type": "concept_explanation",    // enum below; picks the template
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
  "expected_concepts": ["Classification evaluation"],
  "expected_tool_ids": [],                 // TOOL_#### from tools.jsonl
  "expected_resource_ids": [],             // RES_#### from resources.jsonl
  "requirements": {
    "requires_math": false, "requires_tool": false, "requires_resource": false, "requires_comparison": false,
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
| `prompt_type` | `concept_explanation`, `formula_recall`, `math_derivation`, `comparison`, `tool_request`, `tool_explanation`, `debugging`, `multi_notebook_synthesis`, `topic_recommendation`, `revision_plan`, `refusal`, `partial_answer`, `image_dependent_explanation` |
| `answer_template` | `concept_explanation`, `formula`, `mathematical_explanation`, `comparison`, `code_implementation`, `code_explanation`, `misconception`, `synthesis`, `topic_recommendation`, `revision_plan`, `refusal`, `partial_answer` |
| `difficulty` | `easy`, `medium`, `hard` |
| `source_type` | `markdown`, `code`, `output`, `mixed` |

- `notebook_id` is `nb_<number>`, taken from the notebook's file-name prefix (for example `14 - Classification metrics.ipynb` → `nb_14`).
- `cell_ids` are 0-based positions in the notebook's cell list. Colab shows them as `cell_id + 1`.
- §2 of `response_templates.md` gives the mapping from prompt type to template and sections.

### Validation rules (`--check`)

- `prompt_id` is unique, and `prompt` is non-empty.
- `prompt_type`, `answer_template`, `difficulty` and `source_type` use allowed values. `difficulty` matches the band of `difficulty_score`.
- `should_refuse` is true exactly for `refusal`, and refusals have no `expected_sources`. `partial_evidence_only` is true exactly for `partial_answer`.
- `requires_math` uses a math template or a required math section.
- `requires_multi_notebook` with sources needs at least two distinct `notebook_id`s.
- Every non-refusal template requires `sources`, and no section is both required and optional.
- `tool_request` and `tool_explanation` set `requires_tool`; `requires_resource` needs at least one `expected_resource_ids`.
- Tool and resource IDs are well-formed and, when the local inventories exist, actually exist.

In the retrieval set, a record with no answer key or no sources is valid but incomplete; the report counts these separately. In the golden set, every record must be complete, so `--check` treats an incomplete golden record as an error.

## Prompt types per topic

Each topic gets 8 slots: concept explanation; formula or derivation (or practical reasoning, where a topic has no math objective); comparison; tool request; tool explanation; debugging/misconception; multi-notebook synthesis; topic recommendation. A slot can be relabeled or removed if source review shows it doesn't apply. Implementations must be retrieved from notebook code, never generated.

## Difficulty rubric

Difficulty measures what the agent has to do. It does not measure answer length, topic importance or whether the corpus can answer the prompt.

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

Only the final score is stored, not the individual factor values. Retrieval breadth is estimated, because chunking isn't built yet, so re-score a prompt if evidence mapping changes what it needs. The current split (24 easy / 166 medium / 150 hard) leans hard because the set deliberately includes many comparison and synthesis prompts.

## Completing a prompt (to promote it to the golden set)

1. Map it to exact notebook cells in `expected_sources`, and to the tools and resources it needs (`expected_tool_ids`, `expected_resource_ids`). If the evidence is an image that isn't available, the prompt can't be fully answered from text: mark it `partial_answer` or caption the image first.
2. Write `summary` and `key_points`, keeping stated facts separate from bounded deductions.
3. Math: verify formulas, variable definitions and each requested step. If steps are missing, retype the prompt as `partial_answer`.
4. Comparison: require evidence for both sides, and don't infer universal runtime or accuracy rankings.
5. Synthesis: require at least two notebooks that each contribute a distinct necessary fact; otherwise retype the prompt.
6. Recommendation: accept only evidence-backed relationships. Belonging to the same family is not a prerequisite.
7. Refusal: search synonyms and inspect image content before asserting that something is absent.

## Split policy

Hold out about 20% as test prompts, but only after answer keys are done. Keep paraphrases and linked boundary/core pairs (for example `T12-01` and `B01`) on the same side of the split. The whole set has been seen during development, so a truly blind test will need a later batch written independently.
