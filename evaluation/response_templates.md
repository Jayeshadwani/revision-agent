# Response templates and success criteria

This file defines how the agent must format each answer and how each answer is scored. Every question in `questions.jsonl` maps to exactly one template through its `question_type` (or through its `expected_behavior` for refusals and partial answers). That means the template doesn't need its own field in the data.

## 1. Universal rules

These apply to every response, whatever the template.

1. Answer only from retrieved notebook chunks. Don't use web search, external APIs or the model's pretraining knowledge.
2. Cite every factual claim inline with a source ID such as `[S1]`. Each ID must refer to a chunk that was actually given to the model.
3. If the evidence is absent, refuse (§3.10). If it is partial, answer the supported part and name what is missing (§3.11). If sources conflict, show both and don't resolve it (§3.12).
4. Never fill a gap from general knowledge. This includes missing derivation steps, comparison dimensions the notes don't cover, and code the notes don't contain.
5. Only include code that comes from the notebooks, copied or minimally adapted (renaming variables or removing plotting is fine).
6. Leave out optional sections that have no supporting evidence rather than writing "N/A".
7. Keep the language crisp and revision-ready, without filler or repetition.

### Citation format

Cite inline as `[S1]`, `[S1][S3]`. End every response with a `## Sources` section that maps each ID to its chunk:

```text
## Sources
[S1] 14 - Classification metrics.ipynb — "Precision and Recall", cell 6
[S2] 14 - Classification metrics.ipynb — "Example", cell 9
```

Cell numbers are 1-based (`cell_number`), matching what you see in Colab. After generation, a validator checks that every cited ID exists in the retrieved context and that every listed source is cited at least once.

## 2. Question type → template

| `question_type` / behavior | Template | Required sections |
|---|---|---|
| `definition` | §3.1 Concept | Answer, Intuition, Sources |
| `formula_recall` | §3.2 Formula | Formula, Variables, Intuition, Sources |
| `math_derivation` | §3.3 Math explanation | Goal, Starting point, Step-by-step, Final result, Evidence completeness, Sources |
| `concept_comparison` | §3.4 Comparison | Short answer, Comparison table, Key takeaway, Sources |
| `code_implementation` | §3.5 Code implementation | Purpose, Code from notes, Explanation, Inputs and outputs, Sources |
| `code_explanation` | §3.6 Code explanation | Purpose, Code, Line-by-line, Sources |
| `error_misconception` | §3.7 Misconception | Common mistake, Why it is a problem, Correct approach, Sources |
| `multi_notebook_synthesis` | §3.8 Synthesis | Short answer, Connection, Evidence from notebooks (≥ 2 notebooks), Sources |
| `topic_recommendation` | §3.9 Recommendation | Selected topic, Recommended topic 1, Recommended topic 2, Suggested order, Sources |
| `expected_behavior` = `refuse` / `candidate_refuse` | §3.10 No-evidence refusal | Refusal line |
| `expected_behavior` = `partial` / `candidate_partial` | §3.11 Partial answer | What the notebooks support, What is missing |
| conflicting sources (any type) | §3.12 Conflict | Conflict statement, both sources |
| daily plan (product feature; not in the eval set yet) | §3.13 Daily plan | Three topics, Suggested order, Sources |

Optional sections (Mathematical form, Implementation from notes, Common mistakes) appear only when retrieved evidence supports them. If a `definition` question has `requires_math` or `requires_code` set to true, the matching optional section becomes required.

## 3. Templates

### 3.1 Concept explanation

Used for: "What is X?", "Explain X", "Why does X matter?"

````text
## Answer
One or two lines that answer the question directly. [S1]

## Intuition
The idea in plain language: why it exists, what problem it solves. [S1]

## Mathematical form            (optional)
Formula with every symbol defined. [S2]

## Step-by-step logic           (optional)
1. ...
2. ...

## Implementation from notes    (optional)
```python
# shortest relevant code cell from the notebooks
```
[S3]

## Common mistakes              (optional, only if the notes discuss them)
- ... [S1]

## Sources
[S1] ...
````

### 3.2 Formula recall

Used for: "What is the formula for X?", "How is X calculated?"

```text
## Formula
Precision = TP / (TP + FP) [S1]

## Variables
- TP: ... [S1]
- FP: ... [S1]

## Intuition
What the formula measures, in one or two lines. [S1]

## Worked example               (optional, only if one exists in the notes)

## Sources
```

### 3.3 Mathematical explanation / derivation

Used for: derivations, "why does this work?", step-by-step calculations.

```text
## Goal
What is being derived or explained.

## Starting point
Definition, formula or assumption, as stated in the notes. [S1]

## Variables
- symbol: meaning [S1]

## Step-by-step
1. Operation or rule applied: ...
   Result: ...
   Why valid: ... [S2]
2. ...

## Final result
The formula or conclusion. [S2]

## Interpretation
What the result means in practice. [S2]

## Implementation from notes    (optional)

## Evidence completeness
"The notebooks contain the full derivation" or
"The notebooks give steps 1–2 and the final result; the intermediate steps are not in the notes."

## Sources
```

If the notes give only the final formula, the agent must write: *"The available notebooks state the final formula but do not provide a complete derivation. I cannot derive the missing steps from the provided context."* It must not invent the missing steps.

### 3.4 Comparison

Used for: "Difference between X and Y", "Compare X and Y", "When to use X vs Y".

```text
## Short answer
The core distinction in one or two lines. [S1][S2]

## Comparison
| Aspect       | X        | Y        |
|--------------|----------|----------|
| Definition   | ... [S1] | ... [S2] |
| How it works | ...      | ...      |
| When to use  | ...      | ...      |

## Key takeaway
How the two relate, or when to pick which. [S1][S2]

## Sources
```

Include only the rows the notes support, and support both sides of each row. Don't invent dimensions or general claims like "X is always faster".

### 3.5 Code implementation

Used for: "Show me code for X", "How do I compute X?"

````text
## Purpose
What the code does. [S1]

## Code from notes
```python
# copied or minimally adapted from the notebook
```
[S1]

## Explanation
- Key line or block: what it does.

## Inputs and outputs
- Inputs: required variables, data, imports.
- Outputs: what it returns or prints.

## When to use                  (optional)

## Sources
````

If the notebooks don't contain a relevant implementation, the agent must write: *"The available notebooks do not contain an implementation for this topic."* It must not generate code.

### 3.6 Code explanation

Used for: "What does this code do?", "Why is this parameter used?", "Explain this cell".

````text
## Purpose
What the code is meant to do. [S1]

## Code
```python
# the relevant excerpt from the notebook
```

## Line-by-line
1. `line or block`: explanation. [S1]
2. ...

## Inputs and outputs           (optional)

## Common mistake               (optional, only if supported)

## Sources
````

### 3.7 Error / misconception

Used for: "Why does X fail?", "What's wrong with doing X?", "Why is X misleading?"

```text
## Common mistake
The mistake or misconception. [S1]

## Why it is a problem
The consequence, using the notes' explanation or example. [S1]

## Correct approach
What the notes recommend instead. [S2]

## Sources
```

### 3.8 Multi-notebook synthesis

Used for: "How do X and Y work together?", "How does X affect Y?"

```text
## Short answer
One or two lines. [S1][S3]

## Connection between concepts
How the pieces fit together, step by step. [S1][S3]

## Evidence from notebooks
- Notebook A: the fact it contributes. [S1]
- Notebook B: the fact it contributes. [S3]

## Sources
```

At least two notebooks must each contribute a distinct, necessary fact. If only one notebook supports the answer, say so instead of padding with a second one.

### 3.9 Topic recommendation

Used for: "I'm revising X, what should I study next?"

```text
## Selected topic
X

## Recommended topic 1
- Topic: ...
- Relationship: prerequisite / closely related / extension
- Why: the evidence-backed link to X. [S1]
- Notebook coverage: appears in N notebooks

## Recommended topic 2
- (same fields)

## Suggested revision order
1. ...
2. ...
3. ...

## Sources
```

Return exactly two topics. Every relationship must be backed by evidence, such as co-occurrence in a notebook or an explicit "builds on" statement. Being in the same family doesn't make something a prerequisite.

### 3.10 No-evidence refusal

```text
I don't know from the available notebooks.

The notebooks don't cover <subject>. <Optional: the closest topic they do cover, with a citation.>
```

### 3.11 Partial answer

Used for boundary cases where part of the request is supported and part isn't, whether because the corpus lacks it or because you didn't supply the needed input.

```text
The available notebooks partially address this question.

## What the notebooks support
<the supported part, in the template for its question type> [S1]

## What is missing
- <the unsupported part> and why it can't be answered:
  not in the notebooks / requires your data or results / requires a proof the notes don't contain.

I cannot provide the missing part from the available notebooks.
```

### 3.12 Conflicting evidence

```text
The available notebooks contain conflicting information.

- Source 1 says: ... [S1]
- Source 2 says: ... [S2]

I cannot resolve this conflict from the provided context.
```

### 3.13 Daily revision plan

This is a product feature with no evaluation questions yet.

```text
## Today's revision plan

### Topic 1: <user-selected>
- Key ideas: ... [S1]
- Implementation to practice: ... [S2]

### Topic 2: <recommended>
- Relationship to Topic 1: ... [S3]
- Key ideas: ...

### Topic 3: <recommended>
- Relationship to Topic 1: ... [S4]
- Key ideas: ...

## Suggested order
1. ...  2. ...  3. ...

## Sources
```

## 4. Success criteria

Format and content are scored separately. A response that is well formatted but hallucinated fails, and so does one that is correct but ignores its template.

### 4.1 Scoring dimensions (per response)

| Dimension | 0 | 1 | 2 | Applies to |
|---|---|---|---|---|
| Relevance | Doesn't answer the question | Partially answers | Directly answers | All |
| Correctness | Wrong | Partially correct | Matches `expected_answer_points` | Answerable |
| Faithfulness | Major unsupported claims | Some unsupported claims | Every claim supported by retrieved chunks | All |
| Completeness | Major parts missing | Minor parts missing | All required points present | Answerable |
| Structure | Wrong template | Minor format issues | Correct template and required sections | All |
| Citations | Missing or invalid | Present but weak | Valid and support their claims | All |
| Math logic | Wrong or invented steps | Partly logical | Every step stated, valid and sourced; gaps declared | `requires_math` |
| Code relevance | Irrelevant or invented | Partly relevant | Relevant, minimal, traceable to a notebook | `requires_code` |
| Recommendation | Unsupported links | One weak link | Two evidence-backed relationships | `topic_recommendation` |
| Refusal | Hallucinates | Partial refusal | Correct refusal or partial split | `refuse` / `partial` |

Each dimension is scored only where it applies, so no denominator includes a criterion that doesn't fit the question.

### 4.2 Pass rule

A response passes when all of the following hold:

- Structure ≥ 1 (the right template was used).
- Faithfulness = 2.
- Citation validity is 100%: every cited ID was in the retrieved context.
- Answerable questions: Correctness = 2 and Completeness ≥ 1.
- `refuse` / `partial` questions: Refusal = 2.
- Every applicable type-specific dimension (math, code, recommendation) is ≥ 1.

### 4.3 Retrieval (scored separately from generation)

| Metric | Definition |
|---|---|
| Evidence recall@k | Share of `expected_sources` cells found in the top-k retrieved chunks |
| Evidence-group coverage | For multi-notebook questions: whether each required notebook contributed a chunk |

Diagnose a failure by checking retrieval first. If the required evidence never reached the model, it's a retrieval failure. If it did and the answer is still wrong, it's a generation failure.

### 4.4 v1 quality gate

The baseline isn't complete until it meets all of these on the score-eligible set:

| Criterion | v1 target |
|---|---:|
| Template / format validity | ≥ 95% |
| Relevance | ≥ 90% |
| Faithfulness: factual claims supported by retrieved context | ≥ 90% |
| Citation presence: factual claims cited | ≥ 95% |
| Citation validity: cited IDs exist in retrieved context | 100% |
| Citation relevance: cited chunk supports the claim | ≥ 85% |
| Correctness on answerable questions | ≥ 80% |
| Completeness | ≥ 80% |
| Correct refusal / partial split | ≥ 80% |
| Math answers judged logically coherent and grounded | ≥ 75% |
| Attached code judged relevant | ≥ 80% |
| Topic recommendations judged relevant | ≥ 70% |
| No outside knowledge (no unsupported factual claims) | ≥ 95% |

These are first-baseline targets, not production targets. None of them has been measured yet. Report them per `question_type` and per `difficulty` as well as overall, and raise them once the baseline is stable.
