# Revision Agent evaluation set

340 questions spanning the finalized 40-topic catalog: 320 topic questions and 20 partial-answer/refusal cases. All 20 active questions from the first reviewed batch are retained through `legacy_question_id`.

## Files

- `final_set_proposal.json`: structured question records, available source evidence, review status and difficulty factors.
- `final_set_proposal.csv`: the same records as CSV; nested fields contain JSON strings.
- `final_set_proposal.md`: readable question inventory with difficulty labels and scores.
- `difficulty_assignments.md`: rubric, factor anchors and per-question difficulty rationales.
- `difficulty_summary.json`: rubric weights, assignment profiles and aggregate counts.
- `topic_coverage.csv`: coverage and difficulty counts by topic.
- `approved_batch_01_snapshot.json`: original reviewed batch, retained for traceability; the current 340-row files are authoritative for question difficulty.

## Current status

This is a question inventory with assigned difficulty, not a fully validated golden benchmark. Most expected answers and notebook/cell evidence remain pending. All `score_eligible` values remain false until final answer-key review. Candidate notebook numbers are navigation hints, not verified citations.

Difficulty is based on question demand: 24 easy, 166 medium and 150 hard. The weighted factors are cognitive operation (0.35), anticipated retrieval breadth (0.25), mathematical demand (0.20) and ambiguity/inference (0.20). Easy is below 0.40; medium is 0.40 to below 0.70; hard is 0.70 or above. Retrieval breadth is estimated until evidence mapping and chunking are complete.

Question difficulty does not establish corpus answerability. Refusal labels remain provisional where absence has not been checked against image content. The source notebook code was not automatically executed. See the proposal document for evidence gates and split-group guidance.
