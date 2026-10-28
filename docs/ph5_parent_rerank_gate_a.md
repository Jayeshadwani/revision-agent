# PH5-RETRIEVE-002 — Gate A: design, offline evidence, resource estimates

Issue #11. This is the Gate A deliverable: analysis and design, no-cost local code and tests, and
resource estimates. **Nothing here downloads a model, makes a paid call, re-embeds or changes the
default retrieval.** Gate B needs written PO approval of the requests in [§6](#6-approval-requests-gate-b).

## 1. Baseline (PH4-RETRIEVE-001, 47 labelled prompts)

| Mode (default = hybrid_rrf) | Recall@5 | Recall@10 | MRR | Hit@1 | Tool coverage |
|---|---:|---:|---:|---:|---:|
| dense | 0.732 | 0.823 | 0.684 | 0.553 | 0.625 |
| BM25 | 0.651 | 0.725 | 0.560 | 0.383 | 0.625 |
| **hybrid RRF** | **0.736** | **0.817** | **0.729** | **0.617** | **0.750** |

Known weak spots: multi-notebook questions (Recall@5 0.42), concept explanations crowded out by
code chunks, and misspelled source terms ("Dendogram").

## 2. Design

```
query → candidates over CHILDREN (dense / BM25 / hybrid, 50) → map child → PARENT (dedup, fail closed)
      → [optional] cross-encoder rerank → context package (5 concepts + 3 tools, ≤ 4,000 tokens)
```

**Parents** are the existing Concept chunks (`CON_*`), plus Tool chunks, which are their own
parents. They already meet the issue's boundary rules:
- one notebook, related sections only
- instructor notes and quizzes stripped (PH2)
- 300–800 tokens
- every evaluation label already points at them

No IDs change.

**Children** (`src/parent_retrieval.py`):
- Each child is a window of ≤128 or ≤256 estimated tokens, cut at paragraph boundaries inside one
  parent segment. Fenced code, `$$` math and tables are never cut.
- Child IDs are versioned, e.g. `CON_000123.c02.s128`.
- A child never spans two segments, so it never crosses a span, section or notebook.

**Expansion rules.** These are enforced in `ParentStore.expand` and tested:

| Situation | Behaviour |
|---|---|
| Unknown child, missing parent, parent in another notebook | Mapping error, dropped (fail closed) |
| Parent text changed since the map was built (sha256 per segment) | `stale_parent_segment`, dropped |
| Parent role not teaching/mixed, or ineligible child | Dropped |
| Mixed parent (teaching + quiz) | Only eligible segments are serialized; the quiz span never is |
| Filters (notebook, type, …) | Re-checked on the **parent**, not only on the child |
| Several children hit one parent | One entry at the first-hit rank; every matched child kept for provenance |
| Parent over its 1,200-token budget | Whole segments around the matched ones are kept; omitted segments are listed |
| Context over its 4,000-token budget | Remaining parents are listed in `omitted_for_budget`, never silently cut |
| Expanded text | Marked `untrusted_source_text`; injection-like text sets `injection_suspected` |

**Reranking** (`src/reranker.py`): `safe_rerank` wraps any cross-encoder.
- **Failure handling.** All of these fall back to the baseline order, with the reason logged:
  - timeout
  - missing or corrupt model
  - out of memory
  - a partial batch failure
  - the wrong number of scores
  - all scores invalid
- **NaN/inf scores** go last. **Ties** keep the baseline order.
- **Inputs over the model limit** are logged, never trimmed silently.
- **Scores are logits used only for ordering.** They are not calibrated relevance, so nothing
  should threshold on them.
- **The model loads only from a local directory.** `local_files_only`; with no approved checkpoint,
  the reranker is unavailable.
- **Gate B compares two placements:**
  - rerank the children before expansion (shorter inputs, less truncation)
  - rerank the parents after expansion (whole sections, higher truncation risk)

## 3. Offline evidence (BM25 only, `src/parent_experiment.py`)

Setup: the same 47 prompts and the same 50-parent candidate budget. There is a fixed held-out
split: 60% dev, 40% test, by sha256(prompt_id), chosen before any tuning. Token counts are
estimates.

| Variant | Recall@5 | Recall@10 | MRR | Hit@1 | Candidate Recall@50 | Context tokens (top 5) | Units |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline chunks | 0.651 | 0.725 | 0.560 | 0.383 | 0.973 | 1,428 | 2,174 |
| child 128 → parent | 0.688 | 0.798 | 0.565 | 0.362 | 0.931 | 1,517 | 5,144 |
| child 256 → parent | 0.612 | 0.777 | 0.564 | 0.383 | 0.941 | 1,473 | 4,514 |

**Reading it:**
- **Small children help coverage in keyword search.** Child-128 raises Recall@10 by 0.07 and
  Recall@5 by 0.04, and broad short queries rise from 0.43 to 0.83.
- **They don't put the right answer first more often.** MRR is flat and Hit@1 drops slightly.
- **Multi-notebook gets worse** (Recall@5 0.34 → 0.24).
- **Candidate Recall@50 falls** (0.973 → 0.931). Many children of the same parent fill the pool, so
  fewer distinct parents reach it. That's why reranking can't fix missing candidates, and why Gate
  B should report candidate recall separately.
- **Context size barely changes**, because parents are the same chunks. The parent design doesn't
  inflate the context.
- **Child-256 is not better than the baseline on keyword search.**
- **Caveat:** n = 47 (dev 28, test 19), so one prompt is about 0.02. Treat these numbers as
  direction, not proof, and note the evidence is keyword-only. Dense children need embeddings,
  which is Gate B.

Per-query keyword search is under 4 ms for the baseline and 33–58 ms with children. The extra time
is the expansion step's integrity hashing; it can be cached per corpus version in Gate B.

## 4. Reranker alternatives (no download yet)

| Model | License | Parameters | Weights (fp32, approx.) | Max input | Notes |
|---|---|---:|---:|---:|---|
| `cross-encoder/ms-marco-MiniLM-L6-v2` | Apache-2.0 ✔ | 22.7M ✔ | ~90 MB | 512 | Smallest; English MS MARCO; MRR@10 39.0 on MS MARCO dev ✔ |
| `mixedbread-ai/mxbai-rerank-xsmall-v1` | Apache-2.0 ✔ | ~70M (verify) | ~280 MB | 512 | Small; newer training data |
| `BAAI/bge-reranker-base` | MIT ✔ | ~278M (verify) | ~1.1 GB | 512 | Stronger, about 10× MiniLM compute |
| `BAAI/bge-reranker-v2-m3` | Apache-2.0 ✔ | ~568M (verify) | ~2.3 GB | 8,192 | Multilingual, long input; heavy on CPU |

✔ means checked against the model card or provider page. "verify" means it gets confirmed from
the checkpoint at Gate B, before download.

**CPU latency is not measured yet.** Order-of-magnitude assumption for reranking 20 candidates of
about 300 tokens on a 4-core laptop:
- MiniLM: roughly 0.2–0.6 s
- base-size models: 2–5 s
- m3: 5–15 s

**Recommendation:** start with MiniLM-L6, which is the smallest and Apache-licensed. Rerank the top
20, not the top 50, to bound latency. Use mxbai-xsmall as the alternative if MiniLM shows no gain.

## 5. Resource estimates for Gate B

| Item | Estimate |
|---|---|
| Re-embedding children (128 and 256), text-embedding-3-small | ~0.95M tokens → **≈ $0.02** total |
| New Qdrant collections | `revision_agent_v1_child128` (~30 MB) and `…_child256` (~26 MB), experimental; `revision_agent_v1` untouched |
| Reranker download and disk | ~90 MB (MiniLM) |
| Extra RAM at query time | MiniLM ~0.3–0.5 GB; base-size ~1.5–2 GB |
| Per-query compute | 1 query embedding (cached) + Qdrant search + rerank of 20 candidates on CPU |
| Paid per-query cost | Unchanged: one query embedding, ~$0.000001 |

## 6. Approval requests (Gate B)

Please approve or adjust each:
1. **Model download:** `cross-encoder/ms-marco-MiniLM-L6-v2` (~90 MB, Apache-2.0). Optionally also
   `mxbai-rerank-xsmall-v1` for comparison.
2. **Re-embedding spend:** up to **$0.05** for child-128 and child-256 experimental collections. This
   must not touch `revision_agent_v1`.
3. **RAM/CPU budget:** ≤ 1 GB extra RAM, CPU only.
4. **Latency target:** retrieval + rerank p95 ≤ **1.5 s** warm and ≤ 5 s cold, on a laptop CPU.
5. **Go/no-go rule.** Proposed: adopt a variant only if, on the **held-out test split**, all of
   these hold:
   - Recall@5 or MRR improves by ≥ 0.03 over hybrid
   - no category drops by more than 0.05 Recall@5
   - candidate Recall@50 doesn't fall
   - leakage is zero
   - p95 is within the target
   - Recall@5 alone is never enough

**Gate B plan:**
- Ablations: baseline (hybrid) vs parent-only vs reranker-only vs combined, with both child sizes
  and both rerank placements.
- Tune on dev only; report test once.
- Measure cold and warm p50/p95, peak RAM and storage.
- Include failure cases.
- The default stays hybrid until a second PO approval.

## 7. PM edge-case matrix (#11)

| Edge case | Status | Where |
|---|---|---|
| Missing / deleted / renamed parent; stale offsets → fail closed, hash check | ✅ Tested | `test_parent_retrieval.py`: `test_E14_*`, `test_stale_source_fails_closed`, `test_unknown_child` |
| Overlapping children, dedup by parent, keep child provenance | ✅ Tested | `test_E09_*`, `test_E01_*`, `test_no_forbidden_text_for_any_ranking` |
| Cross-section / notebook / document leakage | ✅ Tested (notebook) | `test_cross_notebook_child_rejected`, `test_E20_*`; children cannot cross segments by construction |
| Cross-user leakage | ⚠️ N/A today | Single-user corpus; revisit if multi-user content is added |
| Mixed parent: strip quiz / notes / answer keys before expansion | ✅ Tested | `test_E10_*`, `test_quiz_segment_never_serialized`, `test_E08_*` |
| Over budget, long math/code/tables, image-only, no silent truncation | ✅ Tested (slicing + omitted lists); math/code never cut | `test_oversized_parent_is_sliced_with_report`, `test_E16_*`, `test_E02_*`; chunk-level code/math tests in `test_chunking.py` |
| Filters re-applied to expanded parent | ✅ Tested | `test_E13_*`, `test_E20_*`, `test_filters_on_parent_type` |
| Reindex / role change → versioned map, cache invalidation | 🟡 Partial | Versioned child IDs + segment hashes (stale detection tested); cache keys are Gate B |
| Zero candidates / low evidence / typo / short or long query | ✅ Tested (expansion side) | `test_E15_*`, `test_E18_*`, `test_E12_*`; refusing to answer is generation (next phase) |
| Candidate recall reported separately (Recall@50) | ✅ Reported | `parent_experiment.py`, §3 |
| Reranker input truncation: child-before vs parent-after | 🟡 Logged now, compared in Gate B | `over_limit`, `input_tokens` in `RerankResult`; `test_inputs_over_model_limit_are_logged` |
| Negative / tied / NaN / inf scores | ✅ Tested | `test_reranker.py` |
| Cold start, missing/corrupt model, timeout, OOM, partial batch → baseline | ✅ Tested | `test_reranker.py`, `test_E17_*` |
| Reranking vs concept/tool quotas, attachments | 🟡 Gate B | Quotas and attachments stay in `retrieval.py`; reranking feeds the same selection |
| Cache keys (query, corpus hash, model, filters) | 🟡 Gate B | Query-embedding cache already keys on model+text; ranking cache not built |
| Prompt injection stays untrusted | ✅ Tested (flag) | `test_E11_*`; enforcement in prompts is generation |
| Labels audited, never tuned to outputs | ✅ Documented | §8 |
| Multiple hits per parent inflating metrics | ✅ Handled | Parents deduplicated before scoring; "useful parents in top 5" reported |
| Large parents winning by size | ✅ Reported | Context tokens (top 5) per variant |
| Category regressions | ✅ Reported | §3; `parent_experiment_report.md` |
| Same corpus, held-out prompts, hardware, budget | ✅ Set up | Fixed split, 50-candidate budget for all variants |
| Cold/warm p50/p95, RAM, storage, cost | 🟡 Partial | Keyword latency, build RAM, storage and cost estimated here; reranker/dense measured in Gate B |
| No evidence / exhausted budget → fail safe | ✅ Expansion side | Empty or omitted lists, never invented sources |

**Blockers before Gate B can be accepted:** reranking vs quota/attachment interplay, ranking-cache
keys, and measured reranker latency/RAM. All three need the approved model.

## 8. Findings and label audit (nothing changed in this PR)

- **Fixture (PR #12): most children paraphrase their parent** (e.g. C004 "High accuracy…" vs
  P002 "A very high accuracy…").
  - The adapter can't verify those parents as whole text, so it serves only the eligible children,
    which is the safe outcome. Only P001 expands as a whole.
  - Suggestion: a fixture v2 with verbatim children or offsets.
  - Also, C013 is labelled `quiz` under an `environment_setup` parent.
- **Golden T16-08 and T17-03** cite `nb_18` cell 24, a quiz block ("Quiz – Check your
  understanding"). It's correctly unreachable. Proposed fix: replace it with the teaching cell it
  quizzes, after review.
- **QA-17 (StandardScaler)**: the label lists only nb_13/nb_15 cells, while the results from
  nb_19/20/22 are also correct. Proposed fix: add those cells, from the notebook structure and not
  from retrieval output.

## Files

- `src/parent_retrieval.py`: hierarchy, safe expansion, fixture adapter
- `src/reranker.py`: safe rerank wrapper, local-only cross-encoder
- `src/parent_experiment.py`: offline keyword comparison and footprint, writing
  `data/processed/parent_experiment_report.md`
- `tests/test_parent_retrieval.py` (31 tests) and `tests/test_reranker.py` (14 tests)
