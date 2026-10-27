# Evaluation set

`questions.jsonl` is the single source of truth: 340 questions, one JSON object per line. These break down into 320 topic questions (8 for each of the 40 topics, IDs `T01-01` … `T40-08`) and 20 boundary cases (`B01` … `B20`) that test partial answers and refusals.

How the agent must format and how answers are scored is defined in [`response_templates.md`](response_templates.md).

Counts, per-topic coverage and CSV exports are generated from this file rather than committed:

```bash
python scripts/eval_report.py              # difficulty / type / status counts
python scripts/eval_report.py --topics     # per-topic coverage
python scripts/eval_report.py --csv x.csv  # flat CSV for a spreadsheet
python scripts/eval_report.py --check      # verify scores, bands and ids
```

## Status

This file is a question inventory with assigned difficulty. It is not yet a validated golden benchmark.

- Most expected answers and notebook/cell evidence are still pending. Only 14 questions have `evidence_status = source_cells_verified`.
- Every `score_eligible` value stays `false` until the answer key has been reviewed.
- `candidate_notebook_numbers` are navigation hints, not verified citations.
- Refusal labels for boundary cases remain provisional (`candidate_refuse` / `candidate_partial`) until absence has also been checked against image content.
- No notebook code was executed.

## Record fields

| Group | Fields |
|---|---|
| Identity | `question_id`, `legacy_question_id`, `topic_id`, `topic_name`, `split_group_id` |
| Question | `question`, `question_type`, `secondary_types`, `expected_behavior` (`answer` / `partial` / `candidate_*`) |
| Answer key | `expected_answer`, `expected_answer_points`, `expected_sources` (notebook, sha256, cell index, section, excerpt) |
| Flags | `requires_math`, `requires_code`, `requires_multi_notebook`, `should_refuse`, `score_eligible`, `split` |
| Review | `evidence_status`, `question_review_status`, `answer_key_review_status`, `evaluation_notes`, `legacy_user_review` |
| Difficulty | `difficulty`, `difficulty_score`, the four factor values, `difficulty_profile`, `difficulty_rationale`, `difficulty_rubric_version`, `retrieval_breadth_status`, `difficulty_recheck_trigger` |

The 20 questions from the first reviewed batch (Q01–Q23, with Q02, Q06 and Q11 retired and Q09 as the Bayes replacement) keep their wording, are linked through `legacy_question_id`, and carry your original review decision in `legacy_user_review`.

## Question types

There are 10 types. Each topic gets 7–8 of them, laid out in this order:

1. Definition / conceptual understanding
2. Formula, derivation or practical reasoning, whichever fits the topic. Five topics without a suitable math objective get an extra reasoning or misconception question instead.
3. Comparison or choice between alternatives
4. Retrieve a relevant implementation
5. Explain an implementation detail
6. Diagnose an error or misconception
7. Multi-notebook synthesis
8. Recommend two related topics, with evidence for each relationship

A slot can be relabeled or removed if source review shows it doesn't apply. Implementations must be retrieved from notebook code, not generated.

## Difficulty rubric (`question_demand_v1`)

Difficulty measures what the agent has to do. It does not measure answer length, topic importance or whether the corpus can answer the question.

```
score = 0.35 × cognitive_operation + 0.25 × retrieval_breadth
      + 0.20 × math_demand        + 0.20 × ambiguity_inference

easy < 0.40 ≤ medium < 0.70 ≤ hard
```

| Factor | Low | Middle | High |
|---|---|---|---|
| Cognitive operation | 0.25 recall/restate | 0.65 explain/apply | 0.95–1 analyze/evaluate/synthesize/derive |
| Retrieval breadth | 0.25 one evidence unit | 0.50–0.65 several related units | 0.80–1 multiple evidence groups or notebooks |
| Math demand | 0 none; 0.25 formula meanings | 0.45–0.50 interpret or calculate | 0.90–1 proof or multi-step derivation |
| Ambiguity / inference | 0.15 directly stated | 0.40–0.65 bounded interpretation | 0.70–0.90 judgment, separating partial support |

Each question is assigned a named `difficulty_profile` (recall, explain, compare, derive, synthesis, diagnose, recommend, partial, refuse, and so on), which sets the four factor values. The per-question rationale is stored in `difficulty_rationale`.

Retrieval breadth is an estimate, because chunking isn't built yet; evidence mapping may change it. The word "why" doesn't automatically make a question hard. The current split (24 easy / 166 medium / 150 hard) is skewed toward hard because the set deliberately includes many comparison and synthesis questions. Labels were not lowered to hit a target distribution.

## Evidence and review gates (before a question becomes scoreable)

1. Map the question to exact notebook/cell evidence and to distinct required evidence groups.
2. Write answer points and claim-to-source mappings, separating stated facts from bounded deductions.
3. For math, verify formulas, variable definitions and each requested step. If steps are missing, change the expected behavior to `partial`.
4. For comparisons, require evidence for both sides. Don't infer universal runtime or accuracy rankings.
5. For synthesis, require at least two notebooks that each contribute a distinct necessary fact; otherwise reclassify the question.
6. For recommendations, accept a relationship only if it is backed by evidence. Belonging to the same family does not establish a prerequisite.
7. For refusals, search synonyms and inspect image content before asserting that something is absent from the corpus.
8. Finalize the rubric, run your review, then freeze the benchmark version.

## Scoring and split policy

- Score retrieval evidence coverage, factual correctness, unsupported-claim rate, citation correctness and behavior correctness separately. Apply the math, code, comparison and recommendation rubrics only where they're relevant.
- When a definition fails, first check whether the required evidence reached the model before blaming retrieval.
- Hold out about 20% as test questions, but only after evidence verification and near-duplicate grouping. Keep paraphrases and linked boundary/core pairs in the same `split_group_id`.
- The whole set has been seen during development, so a truly blind test will need a later batch written independently.
