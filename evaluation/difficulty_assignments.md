# Question difficulty assignments

Applies to all 340 questions. Difficulty measures the required agent task, not answer length or topic importance. Factor values are judgment-based annotations, not empirical performance measurements.

Score = 0.35 × cognitive operation + 0.25 × retrieval breadth + 0.20 × mathematical demand + 0.20 × ambiguity/inference.

Easy: score < 0.40; medium: 0.40 ≤ score < 0.70; hard: score ≥ 0.70. Scores are stored to four decimal places so rounding cannot change the band.

## Operational anchors

| Factor | Low | Middle | High |
|---|---|---|---|
| Cognitive operation | 0.25: recall/restate | 0.65: explain/apply | 0.95–1: analyze/evaluate/synthesize/derive |
| Retrieval breadth | 0.25: one coherent evidence unit | 0.50–0.65: several closely related units | 0.80–1: multiple required evidence groups or notebooks |
| Math demand | 0: none; 0.25: formula meanings | 0.45–0.50: formula interpretation/calculation | 0.90–1: proof or multi-step derivation |
| Ambiguity/inference | 0.15: directly stated | 0.40–0.65: bounded interpretation | 0.70–0.90: judgment or separating partial support |

Retrieval breadth is the anticipated evidence scope required by the question. Chunking is not built yet, so these values are not actual chunk counts. Evidence verification may change these estimates. Multi-notebook requirements must still be validated; an unsupported synthesis request is not made answerable by labeling it hard.

A question containing “why” is not automatically hard. Explaining an explicitly stated limitation can be medium. A nominal definition can be hard when it explicitly requests a comparison. A worked scalar update can be medium without requiring a full derivation. Direct relationship recommendations are medium; selecting across a broader topic graph is hard.

The suggested 33%/42%/25% distribution is a diagnostic target, not a quota. The current inventory deliberately contains many comparisons and synthesis questions; labels were not lowered to match that distribution.

Question difficulty is distinct from topic difficulty and corpus answerability. Refusal candidates retain their pending evidence status; unknown should_refuse values were not converted to true merely because a difficulty was assigned. All existing score_eligible flags remain unchanged.

## Distribution

| Difficulty | Count | Percentage |
|---|---:|---:|
| easy | 24 | 7.1% |
| medium | 166 | 48.8% |
| hard | 150 | 44.1% |

## Every question

| ID | Difficulty | Score | Cognitive | Retrieval | Math | Inference | Rationale |
|---|---|---:|---:|---:|---:|---:|---|
| T01-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T01-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T01-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T01-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T01-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T01-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T01-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T01-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T02-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T02-02 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T02-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T02-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T02-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T02-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T02-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T02-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T03-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T03-02 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T03-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T03-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T03-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T03-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T03-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T03-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T04-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T04-02 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T04-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T04-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T04-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T04-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T04-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T04-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T05-01 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T05-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T05-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T05-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T05-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T05-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T05-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T05-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T06-01 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T06-02 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T06-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T06-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T06-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T06-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T06-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T06-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T07-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T07-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T07-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T07-04 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T07-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T07-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T07-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T07-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T08-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T08-02 | easy | 0.2300 | 0.25 | 0.25 | 0.25 | 0.15 | Retrieve the named parameter meanings or simple aggregation rule; no derivation or numerical application is requested. |
| T08-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T08-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T08-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T08-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T08-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T08-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T09-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T09-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T09-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T09-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T09-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T09-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T09-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T09-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T10-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T10-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T10-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T10-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T10-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T10-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T10-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T10-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T11-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T11-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T11-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T11-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T11-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T11-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T11-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T11-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T12-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T12-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T12-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T12-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T12-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T12-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T12-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T12-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T13-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T13-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T13-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T13-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T13-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T13-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T13-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T13-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T14-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T14-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T14-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T14-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T14-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T14-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T14-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T14-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T15-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T15-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T15-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T15-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T15-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T15-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T15-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T15-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T16-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T16-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T16-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T16-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T16-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T16-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T16-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T16-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T17-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T17-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T17-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T17-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T17-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T17-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T17-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T17-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T18-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T18-02 | hard | 0.8900 | 1 | 0.8 | 1 | 0.7 | Explain a multi-step mathematical argument or derive the relationship, beyond restating a formula. |
| T18-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T18-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T18-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T18-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T18-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T18-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T19-01 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T19-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T19-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T19-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T19-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T19-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T19-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T19-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T20-01 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T20-02 | hard | 0.8900 | 1 | 0.8 | 1 | 0.7 | Explain a multi-step mathematical argument or derive the relationship, beyond restating a formula. |
| T20-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T20-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T20-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T20-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T20-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T20-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T21-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T21-02 | hard | 0.8900 | 1 | 0.8 | 1 | 0.7 | Explain a multi-step mathematical argument or derive the relationship, beyond restating a formula. |
| T21-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T21-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T21-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T21-06 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T21-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T21-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T22-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T22-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. |
| T22-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T22-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T22-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T22-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T22-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T22-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T23-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T23-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T23-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T23-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T23-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T23-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T23-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T23-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T24-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T24-02 | easy | 0.2300 | 0.25 | 0.25 | 0.25 | 0.15 | Retrieve the named parameter meanings or simple aggregation rule; no derivation or numerical application is requested. |
| T24-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T24-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T24-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T24-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T24-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T24-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T25-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T25-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. |
| T25-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T25-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T25-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T25-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T25-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T25-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T26-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T26-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T26-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T26-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T26-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T26-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T26-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T26-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T27-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T27-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T27-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T27-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T27-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T27-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T27-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T27-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T28-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T28-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T28-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T28-04 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T28-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T28-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T28-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T28-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T29-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T29-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. |
| T29-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T29-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T29-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T29-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T29-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T29-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T30-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T30-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T30-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T30-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T30-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T30-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T30-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T30-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T31-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T31-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. The existing math_derivation category does not make this a proof task; it asks for explanation/application. |
| T31-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T31-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T31-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T31-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T31-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T31-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T32-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T32-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T32-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T32-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T32-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T32-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T32-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T32-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T33-01 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T33-02 | medium | 0.5325 | 0.65 | 0.5 | 0.5 | 0.4 | Apply a stated calculation or update to a worked example; no full derivation is required. |
| T33-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T33-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T33-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T33-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T33-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T33-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T34-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T34-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T34-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T34-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T34-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T34-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T34-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T34-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T35-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T35-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T35-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T35-04 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T35-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T35-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T35-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T35-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T36-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T36-02 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T36-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T36-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T36-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T36-06 | hard | 0.7150 | 0.95 | 0.85 | 0 | 0.85 | Diagnose an indirect cause or evaluate a conditional decision rather than restating a warning. |
| T36-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T36-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T37-01 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T37-02 | medium | 0.5225 | 0.65 | 0.5 | 0.45 | 0.4 | Explain a formula and its role without deriving it. |
| T37-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T37-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T37-05 | medium | 0.4750 | 0.65 | 0.55 | 0 | 0.55 | Interpret behavior of a source code excerpt and connect parameters to outputs. |
| T37-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T37-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T37-08 | medium | 0.5550 | 0.75 | 0.65 | 0 | 0.65 | Select two related topics and justify direct supported links; no prerequisite ordering is requested. |
| T38-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T38-02 | hard | 0.8900 | 1 | 0.8 | 1 | 0.7 | Explain a multi-step mathematical argument or derive the relationship, beyond restating a formula. |
| T38-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T38-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T38-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T38-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T38-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T38-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T39-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T39-02 | hard | 0.8900 | 1 | 0.8 | 1 | 0.7 | Explain a multi-step mathematical argument or derive the relationship, beyond restating a formula. |
| T39-03 | hard | 0.7050 | 0.95 | 0.85 | 0 | 0.8 | Contrast alternatives or judge a choice using evidence for both sides. |
| T39-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T39-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T39-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T39-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T39-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| T40-01 | easy | 0.1800 | 0.25 | 0.25 | 0 | 0.15 | Retrieve and restate a directly stated definition or property. |
| T40-02 | hard | 0.8900 | 1 | 0.8 | 1 | 0.7 | Explain a multi-step mathematical argument or derive the relationship, beyond restating a formula. |
| T40-03 | hard | 0.7850 | 0.95 | 0.85 | 0.4 | 0.8 | Compare mathematical mechanisms and their implications using evidence for both sides. |
| T40-04 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Locate a suitable source implementation and explain its required inputs and use. |
| T40-05 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Explain or assemble interacting processing/training components and their data flow. |
| T40-06 | medium | 0.4650 | 0.65 | 0.55 | 0 | 0.5 | Explain a mechanism or interpret a relationship using related evidence. |
| T40-07 | hard | 0.7700 | 1 | 1 | 0 | 0.85 | Combine distinct required facts from multiple notebooks into one explanation. |
| T40-08 | hard | 0.7275 | 0.95 | 0.9 | 0 | 0.85 | Choose across alternative topic relationships and justify a learning-oriented connection. |
| B01 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B02 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B03 | medium | 0.5075 | 0.65 | 0.6 | 0 | 0.65 | Recognize that a requested fact is unsupported and abstain; do not generate it from general knowledge. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B04 | hard | 0.9450 | 1 | 0.9 | 1 | 0.85 | Judge support for a requested multi-step coverage proof and abstain if it is absent. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B05 | medium | 0.5075 | 0.65 | 0.6 | 0 | 0.65 | Recognize that a requested fact is unsupported and abstain; do not generate it from general knowledge. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B06 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B07 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B08 | hard | 0.9350 | 1 | 0.9 | 0.9 | 0.9 | Assess mathematical coverage and distinguish supported steps from an unsupported proof or guarantee. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B09 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B10 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B11 | hard | 0.9350 | 1 | 0.9 | 0.9 | 0.9 | Assess mathematical coverage and distinguish supported steps from an unsupported proof or guarantee. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B12 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B13 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B14 | hard | 0.9350 | 1 | 0.9 | 0.9 | 0.9 | Assess mathematical coverage and distinguish supported steps from an unsupported proof or guarantee. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B15 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B16 | hard | 0.9350 | 1 | 0.9 | 0.9 | 0.9 | Assess mathematical coverage and distinguish supported steps from an unsupported proof or guarantee. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B17 | medium | 0.5075 | 0.65 | 0.6 | 0 | 0.65 | Recognize that a requested fact is unsupported and abstain; do not generate it from general knowledge. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B18 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B19 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
| B20 | hard | 0.7475 | 0.95 | 0.9 | 0.1 | 0.85 | Separate a supported explanation from unavailable evidence or missing user inputs. Corpus answerability and should_refuse status remain separate evidence-review decisions. |
