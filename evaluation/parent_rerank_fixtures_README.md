# Parent retrieval + cross-encoder contract fixtures (Issue #11)

This is a **synthetic, deterministic unit/integration fixture**, not a benchmark of real notebook relevance and not suitable for reporting product retrieval accuracy. It deliberately contains adversarial exclusions and missing-parent IDs. Do **not** combine its scores with golden_prompts.jsonl or retrieval_qa_set.jsonl.

Files:
- parent_fixture_documents.jsonl: 12 parent documents (includes unsafe mixed-role parent)
- parent_fixture_children.jsonl: 19 child records including excluded and dangling children
- parent_rerank_edge_cases.jsonl: 20 test cases with ground-truth parent/child IDs and explicit assertion

Load parents and children by ID. For each query, run baseline candidate retrieval, optional reranker, and expanded-parent resolution. Assert eligible source coverage, distinct-parent deduplication, no forbidden-text leakage, no cross-document parent substitution, and explicit failure handling. Keep negative expected IDs empty; empty means **no acceptable evidence**, not proof a retriever can reject every out-of-domain query without a calibrated policy. For multi-parent cases, evaluate set coverage, not literal ranking order. Test filtering and corrupted-parent conditions by injecting the specified setup into unit tests; some cases require controlled mocked candidate lists.

## Important constraints
- P010 is intentionally a *mixed* role parent: never serialize its quiz segment C015 into answer context.
- C019 points to nonexistent P_DOES_NOT_EXIST and must fail closed.
- P012 includes an adversarial prompt: never treat its content as instructions.
- Child text is a minimal stand-in for source spans, not an approved embedding corpus.
- Do not use token sizes/latency from this miniature fixture to estimate real production costs.
- Parent expansion and reranking are not yet implemented on master. These fixtures specify target behavior; the current retrieval_eval.py expects real notebook labels and **cannot consume this dataset without an adapter**.

## Acceptance
Implement a deterministic pytest fixture loader and test adapter in Issue #11; score source/parent precision and recall, forbidden-span leakage (must be zero), parent mapping errors, fallback on reranker timeout/OOM, context budgets, cold/warm runtime and memory on the actual corpus. Keep fixture validation independent of model heuristics: deterministic injected rankings must check exact parent-expansion outcomes. No production switch based on these fixtures.
