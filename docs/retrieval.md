# Retrieval (PH4-RETRIEVE-001)

```
prompt ─┬─ dense: Qdrant revision_agent_v1, top 50 ─┐
        └─ BM25 over the same 2,174 texts, top 50 ──┴─ RRF (k = 60) ─ filters ─ top 5 concepts + 3 tools (max 8)
                                                                        ├─ attach ≤ 2 linked tools per concept
                                                                        └─ attach attachable images (vision pending)
```

| Module | Role |
|---|---|
| `src/bm25_index.py` | Okapi BM25 (k1 1.5, b 0.75) in pure Python; the tokenizer keeps identifiers (`fillna`, `train_test_split`, `df.fillna`) |
| `src/hybrid_fusion.py` | Reciprocal Rank Fusion, `1 / (60 + rank)` summed over retrievers, no weights, deterministic ties |
| `src/retrieval.py` | `Retriever` with three modes (`dense`, `bm25`, `hybrid_rrf`), filters, a safety guard, tool and resource attachment, and a CLI for manual QA |
| `src/retrieval_eval.py` | Recall@5/10, MRR, Hit@1 and tool coverage per mode and category, plus filter probes and the default-mode decision |

## Running it

```
python src/retrieval.py "curse of dimensionality" --mode bm25
python src/retrieval.py "train a CNN" --mode hybrid_rrf --type tool
python src/retrieval.py "loss derivative" --math --json
python src/retrieval_eval.py               # dense + BM25 + hybrid (needs the index and OPENAI_API_KEY)
python src/retrieval_eval.py --bm25-only   # no API calls
```

Outputs, all local:
- `data/processed/retrieval_report.md`
- `data/processed/retrieval_results.jsonl` (one row per prompt × mode)
- `data/processed/retrieval_decision.json`
- `data/processed/query_embeddings.jsonl` (query-vector cache, so evaluation re-runs are free)

## Filters and safety

- **Filters.** `chunk_type`, `notebook_id`, `content_role`, `contains_math` and `retrieval_eligible`.
  - The default is `retrieval_eligible = true`.
  - An unknown filter field raises an error.
- **What's searchable.** Only the retrieval-eligible concept and tool chunks, so quizzes, instructor
  notes, agendas, business-context repeats, preamble, loading/setup/debugging/non-teaching code and
  resources are never candidates.
- **Safety guard.** It also drops any dense hit whose chunk is missing from the current chunk files
  (a stale index) or that has an excluded role, and counts it in `guard_dropped`.

## The context package

- **`retrieved_chunks`.** The fused ranking, capped at 5 concepts and 3 tools, 8 chunks at most. If
  `chunk_type` is filtered, up to 8 of that type. Each entry has its rank, score, source (`dense`,
  `bm25` or `bm25+dense`), notebook, section and the embedded text.
- **`attached_tools`.**
  - Each retrieved concept gets up to 2 tools linked to it as implements, demonstrates or
    visualizes.
  - Tools that ranked anyway come first, then the more confident links.
  - The reason is recorded: `also_retrieved`, `ranked_candidate` or `linked_to_retrieved_concept`.
- **`attached_resources`.** Up to 3 attachable images per concept.
  - Each carries `vision_status: pending` and `not_usable_as_text_evidence: true`.
  - No image text is included.
- **`ranking`.** The top 20 of the fused list, used for evaluation.

## Evaluation

**Labelled prompts:**
- `evaluation/golden_prompts.jsonl`: 17 scorable prompts, plus 3 refusals reported separately.
- `evaluation/retrieval_qa_set.jsonl`: 30 prompts, namely 10 concept, 5 math, 5 tool, 5 broad
  short and 5 multi-notebook.
  - Their expected cells were picked from the notebook section structure, not from retriever output.
  - The tool prompts list a few canonical code cells. When several cells are valid answers, recall
    is conservative.
- `evaluation/retrieval_prompts.jsonl` (320) has no expected sources yet, so it isn't scored.

**Relevance and metrics:**
- A chunk is relevant if one of its source cells is an expected cell.
- Expected cells that no eligible chunk contains are listed and left out of recall. For example,
  golden prompts T16-08 and T17-03 cite `nb_18` cell 24, which is a quiz.
- Recall@k is the share of reachable expected cells covered by the top k chunks.
- MRR is 1 / rank of the first relevant chunk within the top 20.
- Hit@1 means the first chunk is relevant.
- Tool coverage: for prompts expecting code, the expected tool is in the top 10 or attached.

**Categories:** `concept`, `math`, `tool`, `multi_notebook`, `formula_keyword` (acronyms,
identifiers, formula words) and `broad_short` (4 words or fewer). A prompt can be in several.

**Decision rule:**
- `hybrid_rrf` becomes the default only if it beats dense on Recall@5 or MRR (all prompts) without
  losing on either. Otherwise the default stays `dense`.
- The result is written to `retrieval_decision.json`, and `retrieval.py` reads it.
- Weights are not tuned in this ticket.

**BM25-only baseline** on this corpus (47 scored prompts): Recall@5 0.651, Recall@10 0.725, MRR
0.560, Hit@1 0.383. Dense and hybrid are measured with `python src/retrieval_eval.py` on a machine
with the index and API key.
