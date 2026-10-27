# Revision Agent — final evaluation set proposal

## Proposed scope

**340 questions: 8 core questions for each of the finalized 40 topics (320), plus 20 boundary cases.** All 20 active questions from the reviewed batch are retained with their exact wording and legacy IDs. Q02, Q06 and Q11 remain retired; Q09 is the accepted Bayes replacement. The eight-question layout is a coverage guide, not a reason to invent unsupported content.

This is a proposed final QUESTION INVENTORY. It is not a completed golden benchmark: most source cells, expected answers and scoring rubrics still need verification. All proposal rows have score_eligible=false until the final answer-key review. Verified evidence from the original batch is carried over, not discarded. Question difficulty has now been assigned using the supplied four-factor rubric. This does not finalize the separate topic-level importance/difficulty scoring rules.

## Question types

The supplied reference lists 10 types. Use all ten across the set: definition, formula recall, math derivation/reasoning, comparison, code implementation, code explanation, misconception/debugging, multi-notebook synthesis, recommendation, refusal/partial answer. Each topic receives 7–8 distinct types. Formula and derivation share one slot according to fit; five topics without a suitable math objective receive another practical reasoning/misconception question instead. A slot can be relabeled or removed when source review shows it is inapplicable.

The source reference's question examples are inspiration, not answerability labels. XGBoost/LightGBM and Transformer attention are present in this corpus and cannot automatically be used as refusal cases. A formula request does not imply a full proof exists. Missing images must be processed or explicitly excluded from the declared corpus scope.

## Per-topic layout

1. Definition / conceptual understanding.
2. Formula, derivation or practical reasoning, whichever fits.
3. Comparison or choice between alternatives.
4. Retrieve a relevant implementation.
5. Explain a particular implementation detail.
6. Diagnose an error or misconception.
7. Combine concepts with evidence from multiple notebooks.
8. Recommend two topics with evidence for their relationships.

Implementations should include dependencies and required existing inputs. They must be retrieved from source code; generated replacements are outside this evaluation policy. Code explanation questions require a frozen source excerpt in the final test input or an unambiguous notebook anchor before scoring. Notebooks are never executed automatically.

## Evidence and review gates

1. Map each question to exact notebook/cell evidence and distinct required evidence groups.
2. Write answer points and claim-to-source mappings. Distinguish stated facts from bounded deductions.
3. For math, verify formulas, variable definitions and each requested step. If steps are absent, change expected behavior to partial.
4. For comparisons, require support for each side and the recommendation dimensions. Do not infer universal runtime or accuracy rankings.
5. For multi-notebook synthesis, require two notebooks to contribute distinct necessary facts, not just duplicate text. Reclassify otherwise.
6. For recommendations, accept alternatives only with evidence-backed relationships; family membership does not automatically establish a prerequisite.
7. For refusal, search synonyms and inspect relevant image content before asserting corpus absence. Missing user inputs can justify declining only the unsupported portion without claiming the subject is absent.
8. Finalize rubrics, question difficulty and user review, then freeze the benchmark version.

No additional permission checkpoint is required to prepare evidence or answer keys. This proposal is for scope/wording review.

## Scoring and data split proposal

Track retrieval evidence coverage, factual correctness, unsupported-claim rate, citation correctness and behavior correctness separately. Math steps, code relevance, comparison completeness and recommendation relationships get type-specific rubrics. Structure is secondary to correctness. Refusal, math and code criteria are applied only where relevant; no denominator includes irrelevant criteria.

Do not diagnose every definition failure as retrieval failure: first check whether required evidence reached the model; a model can fail even with correct retrieval. Likewise math failures may originate in image extraction, retrieval or generation.

Reserve approximately 20% as held-out tests only AFTER evidence verification and near-duplicate grouping. Keep related paraphrases and evidence-equivalent questions together, including the linked boundary/core pairs. The full current proposal has been exposed during development; a stronger blind test will require an independently authored later batch. A split alone does not make exposed questions blind.

Retain the Phase 0 performance targets, but do not claim they have been measured. Finalize their denominators and per-type rubrics separately from this question inventory.

## Category counts

| Type | Questions |
|---|---:|
| code_explanation | 40 |
| code_implementation | 40 |
| concept_comparison | 40 |
| definition | 40 |
| error_misconception | 45 |
| formula_recall | 22 |
| math_derivation | 13 |
| multi_notebook_synthesis | 40 |
| refusal_partial | 20 |
| topic_recommendation | 40 |

## All 40 topics

### T01 — NumPy

Candidate notebook anchors: 01,02,03. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T01-01 | definition | medium | 0.4650 | What is NumPy broadcasting, and when can two array shapes be broadcast together? |
| T01-02 | math_derivation | medium | 0.5325 | Explain matrix multiplication with a small example and show how the input shapes determine the output shape. |
| T01-03 | concept_comparison | hard | 0.7050 | How do element-wise multiplication and matrix multiplication differ? |
| T01-04 | code_implementation | medium | 0.4650 | Show how to filter a NumPy array using a Boolean mask. |
| T01-05 | code_explanation | medium | 0.4750 | Explain what axis=0 and axis=1 mean in the array aggregation example. |
| T01-06 | error_misconception | medium | 0.4650 | Why does adding arrays with incompatible shapes fail? |
| T01-07 | multi_notebook_synthesis | hard | 0.7700 | How do NumPy arrays support the tabular calculations later performed in pandas? |
| T01-08 | topic_recommendation | medium | 0.5550 | I am revising NumPy. Recommend two related topics and explain each connection. |

### T02 — Pandas

Candidate notebook anchors: 04,05,06. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T02-01 | definition | medium | 0.4650 | What are a Series and a DataFrame, and how are they related? |
| T02-02 | error_misconception | hard | 0.7150 | How can a join change the number of rows when the join keys contain duplicates? |
| T02-03 | concept_comparison | hard | 0.7050 | How do loc and iloc differ when selecting rows and columns? |
| T02-04 (retains Q10) | code_implementation | medium | 0.4650 | How do I fill missing values for a column in pandas? |
| T02-05 | code_explanation | medium | 0.4750 | Explain how groupby followed by aggregation produces one result per group. |
| T02-06 | error_misconception | medium | 0.4650 | Why can selecting rows by label return different results from selecting by position? |
| T02-07 | multi_notebook_synthesis | hard | 0.7700 | How can joins, grouped aggregation and reshaping be combined to answer a sales-analysis question? |
| T02-08 | topic_recommendation | medium | 0.5550 | I am revising pandas. Recommend two related topics and explain each connection. |

### T03 — Exploratory data analysis

Candidate notebook anchors: 01,04,05,06,07. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T03-01 | definition | medium | 0.4650 | What is exploratory data analysis, and how does it help frame a modeling problem? |
| T03-02 | error_misconception | hard | 0.7150 | How would you investigate a column with missing values before choosing how to handle them? |
| T03-03 | concept_comparison | hard | 0.7050 | When would you remove missing rows, and when would you consider imputation? |
| T03-04 | code_implementation | medium | 0.4650 | Show how to inspect missing values and duplicate rows in a DataFrame. |
| T03-05 | code_explanation | medium | 0.4750 | Explain what info() and describe() reveal about a dataset. |
| T03-06 (retains Q04) | error_misconception | medium | 0.4650 | How do I handle missing values in a dataset? |
| T03-07 | multi_notebook_synthesis | hard | 0.7700 | How do data inspection, cleaning and visualization work together in exploratory analysis? |
| T03-08 | topic_recommendation | medium | 0.5550 | I am revising exploratory data analysis. Recommend two related topics and explain each connection. |

### T04 — Data visualization

Candidate notebook anchors: 06,07. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T04-01 | definition | easy | 0.1800 | What do univariate, bivariate and multivariate visualizations examine? |
| T04-02 | error_misconception | hard | 0.7150 | How would you choose a plot for comparing a numeric distribution across categories? |
| T04-03 | concept_comparison | hard | 0.7050 | When would you use a histogram, a box plot or a scatter plot? |
| T04-04 | code_implementation | medium | 0.4650 | Show how to create a box plot comparing a numeric variable across categories. |
| T04-05 | code_explanation | medium | 0.4750 | Explain how hue changes the information conveyed by a plot. |
| T04-06 | error_misconception | medium | 0.4650 | Why can a single average hide important differences visible in a distribution plot? |
| T04-07 | multi_notebook_synthesis | hard | 0.7700 | How can visualization reveal data-quality problems that summary statistics miss? |
| T04-08 | topic_recommendation | medium | 0.5550 | I am revising data visualization. Recommend two related topics and explain each connection. |

### T05 — Probability

Candidate notebook anchors: 08. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T05-01 | definition | hard | 0.7050 | How do independent and dependent events differ? |
| T05-02 (retains Q09) | math_derivation | medium | 0.5325 | Explain Bayes’ theorem with an example. |
| T05-03 | concept_comparison | hard | 0.7050 | How do marginal, joint and conditional probabilities differ? |
| T05-04 | code_implementation | medium | 0.4650 | Show how to estimate a conditional probability from the cricket dataset. |
| T05-05 | code_explanation | medium | 0.4750 | Explain how filtering and counting rows implements a probability calculation. |
| T05-06 | error_misconception | medium | 0.4650 | Why can P(A given B) differ from P(B given A)? |
| T05-07 | multi_notebook_synthesis | hard | 0.7700 | How does Bayes’ theorem connect the probability chapter to Naive Bayes classification? |
| T05-08 | topic_recommendation | medium | 0.5550 | I am revising conditional probability. Recommend two related topics and explain each connection. |

### T06 — Machine learning workflow

Candidate notebook anchors: 09. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T06-01 | definition | hard | 0.7050 | How do supervised and unsupervised learning differ? |
| T06-02 | error_misconception | hard | 0.7150 | How do you turn a business objective into a prediction task with inputs and a target? |
| T06-03 | concept_comparison | hard | 0.7050 | How do regression, classification and clustering differ? |
| T06-04 | code_implementation | medium | 0.4650 | Show the sequence of fitting a model and generating predictions in a basic supervised-learning example. |
| T06-05 | code_explanation | medium | 0.4750 | Explain what fit() and predict() do at different stages of the workflow. |
| T06-06 | error_misconception | medium | 0.4650 | Why does a model's training score alone fail to establish its usefulness on new data? |
| T06-07 | multi_notebook_synthesis | hard | 0.7700 | How do problem framing, preprocessing and evaluation depend on one another? |
| T06-08 | topic_recommendation | hard | 0.7275 | I am revising the machine-learning workflow. Recommend two related topics and explain each connection. |

### T07 — Preprocessing and pipelines

Candidate notebook anchors: 11,12. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T07-01 | definition | medium | 0.4650 | What is a preprocessing pipeline, and why combine transformations with a model? |
| T07-02 | formula_recall | medium | 0.5225 | Explain standardization and min–max scaling, including the quantities used in each calculation. |
| T07-03 | concept_comparison | hard | 0.7850 | How do standardization and min–max scaling differ? |
| T07-04 | code_implementation | hard | 0.7475 | Show how to combine numeric and categorical preprocessing using ColumnTransformer and Pipeline. |
| T07-05 | code_explanation | medium | 0.4750 | Explain the role of fit_transform() during training and transform() on held-out data. |
| T07-06 | error_misconception | hard | 0.7150 | Why can fitting a preprocessing transformation before the train–test split contaminate evaluation? |
| T07-07 | multi_notebook_synthesis | hard | 0.7700 | How do preprocessing pipelines and cross-validation help keep model evaluation consistent? |
| T07-08 | topic_recommendation | hard | 0.7275 | I am revising preprocessing pipelines. Recommend two related topics and explain each connection. |

### T08 — Model validation and tuning

Candidate notebook anchors: 11,12,17. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T08-01 | definition | easy | 0.1800 | What is cross-validation, and what problem does it address? |
| T08-02 | formula_recall | easy | 0.2300 | How is the validation result combined across the folds in K-fold cross-validation? |
| T08-03 | concept_comparison | hard | 0.7050 | How do training, validation and test sets serve different purposes? |
| T08-04 | code_implementation | medium | 0.4650 | Show how to tune a model hyperparameter with cross-validation. |
| T08-05 | code_explanation | hard | 0.7475 | Explain how a parameter grid and cross-validation interact in GridSearchCV. |
| T08-06 (retains Q21) | error_misconception | medium | 0.4650 | Why is data leakage a problem in model evaluation? |
| T08-07 | multi_notebook_synthesis | hard | 0.7700 | How do validation and regularization work together when selecting model complexity? |
| T08-08 | topic_recommendation | hard | 0.7275 | I am revising cross-validation. Recommend two related topics and explain each connection. |

### T09 — Generalization and regularization

Candidate notebook anchors: 11,12. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T09-01 | definition | easy | 0.1800 | What is the bias–variance tradeoff? |
| T09-02 | formula_recall | medium | 0.5225 | Explain the L1 and L2 penalty terms and how they change the optimization objective. |
| T09-03 | concept_comparison | hard | 0.7850 | How do L1 and L2 regularization differ? |
| T09-04 | code_implementation | medium | 0.4650 | Show how to fit Ridge and Lasso regression in a simple example. |
| T09-05 | code_explanation | medium | 0.4750 | Explain what changing the regularization parameter changes in the fitted model. |
| T09-06 | error_misconception | medium | 0.4650 | Why can increasing model complexity improve training performance but worsen test performance? |
| T09-07 | multi_notebook_synthesis | hard | 0.7700 | How do regularization, model complexity and cross-validation connect when choosing a model? |
| T09-08 | topic_recommendation | hard | 0.7275 | I am revising overfitting. Recommend two related topics and explain each connection. |

### T10 — Linear regression

Candidate notebook anchors: 09,10,11. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T10-01 | definition | medium | 0.4650 | What does linear regression model, and what do its coefficients represent? |
| T10-02 | formula_recall | medium | 0.5225 | Explain mean squared error and how it measures the fit of a regression model. |
| T10-03 | concept_comparison | hard | 0.7050 | How do simple linear regression and multiple linear regression differ? |
| T10-04 | code_implementation | medium | 0.4650 | Show a simple linear-regression implementation with training and prediction. |
| T10-05 | code_explanation | medium | 0.4750 | Explain the input shape expected by the linear-regression fit example. |
| T10-06 | error_misconception | hard | 0.7150 | Why can a high R-squared value be insufficient to judge whether a regression model is useful? |
| T10-07 | multi_notebook_synthesis | hard | 0.7700 | How do scaling, coefficient interpretation and regularization connect in linear regression? |
| T10-08 | topic_recommendation | medium | 0.5550 | I am revising linear regression. Recommend two related topics and explain each connection. |

### T11 — Logistic regression

Candidate notebook anchors: 13. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T11-01 | definition | medium | 0.4650 | How does logistic regression produce a binary-class probability? |
| T11-02 | formula_recall | medium | 0.5225 | Explain the sigmoid function, define its input and output, and relate it to a decision threshold. |
| T11-03 | concept_comparison | hard | 0.7850 | How do linear regression and logistic regression differ in their outputs and losses? |
| T11-04 | code_implementation | medium | 0.4650 | Show how to fit logistic regression and obtain class probabilities. |
| T11-05 | code_explanation | medium | 0.4750 | Explain how predict_proba() differs from predict() in the logistic-regression example. |
| T11-06 | error_misconception | medium | 0.4650 | Why should a predicted probability and a predicted class label not be treated as the same output? |
| T11-07 | multi_notebook_synthesis | hard | 0.7700 | How do logistic-regression probabilities, classification thresholds and precision–recall tradeoffs connect? |
| T11-08 | topic_recommendation | medium | 0.5550 | I am revising logistic regression. Recommend two related topics and explain each connection. |

### T12 — Classification evaluation

Candidate notebook anchors: 13,14. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T12-01 (retains Q01) | definition | medium | 0.4650 | Explain precision and recall. Include an example if available. |
| T12-02 | formula_recall | medium | 0.5225 | Explain how the F1 score is calculated from precision and recall. |
| T12-03 | concept_comparison | hard | 0.7850 | How do precision, recall and ROC-AUC answer different evaluation questions? |
| T12-04 | code_implementation | medium | 0.4650 | Show how to compute precision, recall and F1 using scikit-learn. |
| T12-05 | code_explanation | medium | 0.4750 | Explain how the entries of a confusion matrix correspond to classification outcomes. |
| T12-06 | error_misconception | medium | 0.4650 | Why can accuracy be misleading when one class is much more common than the other? |
| T12-07 | multi_notebook_synthesis | hard | 0.7700 | How do class imbalance, false-positive costs and false-negative costs affect metric selection? |
| T12-08 | topic_recommendation | medium | 0.5550 | I am revising classification metrics. Recommend two related topics and explain each connection. |

### T13 — K-nearest neighbors

Candidate notebook anchors: 15. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T13-01 | definition | easy | 0.1800 | How does K-nearest neighbors make a prediction? |
| T13-02 | formula_recall | medium | 0.5225 | Explain Euclidean distance and how it determines which observations are nearest. |
| T13-03 | concept_comparison | hard | 0.7850 | How do ordinary KNN and distance-weighted KNN differ? |
| T13-04 | code_implementation | medium | 0.4650 | Show how to train and evaluate a KNN classifier. |
| T13-05 | code_explanation | medium | 0.4750 | Explain what changing n_neighbors changes in the KNN example. |
| T13-06 | error_misconception | medium | 0.4650 | Why can features measured on different scales distort KNN predictions? |
| T13-07 | multi_notebook_synthesis | hard | 0.7700 | How do scaling and dimensionality reduction affect distance-based classification? |
| T13-08 | topic_recommendation | medium | 0.5550 | I am revising KNN. Recommend two related topics and explain each connection. |

### T14 — Class imbalance

Candidate notebook anchors: 15. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T14-01 | definition | easy | 0.1800 | What is class imbalance, and why does it matter in classification? |
| T14-02 | formula_recall | medium | 0.5225 | Explain how a class-weighted loss changes the contribution of different classes. |
| T14-03 | concept_comparison | hard | 0.7850 | How do class weighting, random oversampling and SMOTE differ? |
| T14-04 | code_implementation | medium | 0.4650 | Show how to apply the class-imbalance treatment used in the churn example. |
| T14-05 | code_explanation | medium | 0.4750 | Explain the class_weight or resampling step in the selected implementation. |
| T14-06 | error_misconception | medium | 0.4650 | Why can improving overall accuracy make minority-class detection worse? |
| T14-07 | multi_notebook_synthesis | hard | 0.7700 | How should class-imbalance treatment and evaluation metrics be considered together? |
| T14-08 | topic_recommendation | medium | 0.5550 | I am revising class imbalance. Recommend two related topics and explain each connection. |

### T15 — Decision trees

Candidate notebook anchors: 16. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T15-01 | definition | easy | 0.1800 | How does a decision tree partition the feature space? |
| T15-02 | math_derivation | medium | 0.5325 | Explain entropy and Gini impurity with a supported split example. |
| T15-03 (retains Q23) | concept_comparison | hard | 0.7050 | When would you choose a decision tree over a random forest? |
| T15-04 | code_implementation | medium | 0.4650 | Show how to fit and visualize a decision-tree classifier. |
| T15-05 | code_explanation | medium | 0.4750 | Explain how max_depth and min_samples_leaf control the fitted tree. |
| T15-06 | error_misconception | medium | 0.4650 | Why can a very deep decision tree overfit its training data? |
| T15-07 | multi_notebook_synthesis | hard | 0.7700 | How do tree depth, validation and ensemble learning offer different ways to manage overfitting? |
| T15-08 | topic_recommendation | medium | 0.5550 | I am revising decision trees. Recommend two related topics and explain each connection. |

### T16 — Bagging and random forests

Candidate notebook anchors: 17. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T16-01 (retains Q03) | definition | medium | 0.4650 | What is ensemble learning, and how does it differ from training one decision tree? |
| T16-02 | formula_recall | medium | 0.5225 | Explain the aggregation of base-learner predictions for classification and regression. |
| T16-03 | concept_comparison | hard | 0.7050 | How does a random forest differ from a single decision tree? |
| T16-04 | code_implementation | medium | 0.4650 | Show how to fit a random-forest classifier and tune a relevant hyperparameter. |
| T16-05 | code_explanation | medium | 0.4750 | Explain the role of n_estimators and max_features in the random-forest example. |
| T16-06 | error_misconception | medium | 0.4650 | Why does combining many identical base learners provide little benefit? |
| T16-07 | multi_notebook_synthesis | hard | 0.7700 | How does bagging address the high-variance behavior of deep decision trees? |
| T16-08 (retains Q14) | topic_recommendation | medium | 0.5550 | I am revising ensemble learning. Recommend two related study topics and explain the relationship. |

### T17 — Boosting

Candidate notebook anchors: 18. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T17-01 | definition | medium | 0.4650 | What is boosting, and how do later learners depend on earlier learners? |
| T17-02 | math_derivation | medium | 0.5325 | Explain one supported numerical example of updating a boosted model using previous errors. |
| T17-03 (retains Q12) | concept_comparison | hard | 0.7050 | How do bagging and boosting differ in how their base learners are trained? |
| T17-04 | code_implementation | medium | 0.4650 | Show how to fit a gradient-boosted tree model in the classification example. |
| T17-05 | code_explanation | medium | 0.4750 | Explain the learning-rate and estimator-count parameters in the boosting implementation. |
| T17-06 | error_misconception | medium | 0.4650 | Why does adding more boosting stages not guarantee better test performance? |
| T17-07 | multi_notebook_synthesis | hard | 0.7700 | How do boosting, tree complexity and validation connect when controlling overfitting? |
| T17-08 | topic_recommendation | medium | 0.5550 | I am revising boosting. Recommend two related topics and explain each connection. |

### T18 — Naive Bayes

Candidate notebook anchors: 19. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T18-01 | definition | easy | 0.1800 | What is the naive assumption in Naive Bayes classification? |
| T18-02 | math_derivation | hard | 0.8900 | Explain how Bayes’ rule and the conditional-independence assumption combine in Naive Bayes. |
| T18-03 | concept_comparison | hard | 0.7850 | How does multinomial Naive Bayes differ from logistic regression for text classification? |
| T18-04 | code_implementation | medium | 0.4650 | Show how to train the multinomial Naive Bayes spam classifier. |
| T18-05 | code_explanation | medium | 0.4750 | Explain the role of the text representation and smoothing parameter in the classifier. |
| T18-06 | error_misconception | medium | 0.4650 | Why can an unseen word create a zero-probability problem without smoothing? |
| T18-07 | multi_notebook_synthesis | hard | 0.7700 | How do text preprocessing, feature representation and Naive Bayes combine in spam classification? |
| T18-08 | topic_recommendation | hard | 0.7275 | I am revising Naive Bayes. Recommend two related topics and explain each connection. |

### T19 — Clustering

Candidate notebook anchors: 20,21,22. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T19-01 | definition | hard | 0.7050 | What is clustering, and how does it differ from classification? |
| T19-02 (retains Q07) | math_derivation | medium | 0.5325 | Explain the silhouette score with an example. |
| T19-03 | concept_comparison | hard | 0.7050 | How do K-means and DBSCAN differ in their assumptions and treatment of noise? |
| T19-04 | code_implementation | medium | 0.4650 | Show how to fit a clustering model and obtain cluster assignments. |
| T19-05 | code_explanation | hard | 0.7475 | Explain how the K-means silhouette-analysis loop compares candidate cluster counts. |
| T19-06 | error_misconception | medium | 0.4650 | Why can K-means produce different cluster assignments across runs? |
| T19-07 | multi_notebook_synthesis | hard | 0.7700 | How do scaling, initialization and cluster evaluation affect a segmentation workflow? |
| T19-08 | topic_recommendation | medium | 0.5550 | I am revising clustering. Recommend two related topics and explain each connection. |

### T20 — Anomaly detection

Candidate notebook anchors: 23. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T20-01 | definition | hard | 0.7050 | What is the difference between outlier detection and novelty detection? |
| T20-02 | math_derivation | hard | 0.8900 | Explain the local-density reasoning behind Local Outlier Factor. |
| T20-03 | concept_comparison | hard | 0.7850 | How do Isolation Forest and Local Outlier Factor identify unusual observations differently? |
| T20-04 | code_implementation | medium | 0.4650 | Show an anomaly-detection implementation and how its outputs identify unusual observations. |
| T20-05 | code_explanation | medium | 0.4750 | Explain the label or score output of the selected anomaly detector. |
| T20-06 | error_misconception | hard | 0.7150 | Why should a detected anomaly not automatically be treated as an incorrect record? |
| T20-07 | multi_notebook_synthesis | hard | 0.7700 | How do data cleaning, scaling and anomaly detection interact before model training? |
| T20-08 | topic_recommendation | medium | 0.5550 | I am revising anomaly detection. Recommend two related topics and explain each connection. |

### T21 — Dimensionality reduction

Candidate notebook anchors: 24. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T21-01 | definition | easy | 0.1800 | What is dimensionality reduction, and why might it be useful? |
| T21-02 | math_derivation | hard | 0.8900 | Explain how PCA chooses directions that preserve variance. |
| T21-03 | concept_comparison | hard | 0.7850 | How do PCA and t-SNE differ in purpose and limitations? |
| T21-04 | code_implementation | medium | 0.4650 | Show how to apply PCA and inspect explained variance. |
| T21-05 | code_explanation | medium | 0.4750 | Explain how the component-count choice affects the PCA output shape. |
| T21-06 (retains Q05) | error_misconception | easy | 0.1800 | What are the limitations of PCA? |
| T21-07 | multi_notebook_synthesis | hard | 0.7700 | How can PCA connect feature preprocessing, similarity search and visualization? |
| T21-08 | topic_recommendation | hard | 0.7275 | I am revising PCA. Recommend two related topics and explain each connection. |

### T22 — Time-series structure and preparation

Candidate notebook anchors: 25. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T22-01 | definition | easy | 0.1800 | What are trend, seasonality and residual components in a time series? |
| T22-02 (retains Q08) | formula_recall | medium | 0.5325 | Explain moving average with an example. |
| T22-03 | concept_comparison | hard | 0.7050 | How do trailing and centered moving averages differ? |
| T22-04 | code_implementation | medium | 0.4650 | Show how to smooth a time series or decompose it into components. |
| T22-05 | code_explanation | medium | 0.4750 | Explain the window and alignment used by the selected moving-average implementation. |
| T22-06 | error_misconception | hard | 0.7150 | Why can randomly splitting a time series give a misleading forecasting evaluation? |
| T22-07 | multi_notebook_synthesis | hard | 0.7700 | How do missing-value treatment, decomposition and forecasting preparation fit together? |
| T22-08 | topic_recommendation | medium | 0.5550 | I am revising time-series decomposition. Recommend two related topics and explain each connection. |

### T23 — Forecasting baselines and smoothing

Candidate notebook anchors: 26. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T23-01 | definition | medium | 0.4650 | What makes a forecast a useful baseline? |
| T23-02 | formula_recall | medium | 0.5225 | Explain simple exponential smoothing and how alpha changes the update. |
| T23-03 (retains Q13) | concept_comparison | hard | 0.7050 | Compare naive and seasonal naive forecasting. Which past observation supplies each forecast? |
| T23-04 | code_implementation | medium | 0.4650 | Show a naive forecast and a smoothing-based forecast for the same series. |
| T23-05 | code_explanation | medium | 0.4750 | Explain the forecasting horizon and fitted smoothing parameters in the example. |
| T23-06 | error_misconception | medium | 0.4650 | Why can MAPE become problematic when actual values are zero or near zero? |
| T23-07 | multi_notebook_synthesis | hard | 0.7700 | How do trend and seasonality guide the choice between simple, Holt and Holt–Winters smoothing? |
| T23-08 | topic_recommendation | medium | 0.5550 | I am revising forecasting baselines. Recommend two related topics and explain each connection. |

### T24 — Statistical forecasting

Candidate notebook anchors: 26,27. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T24-01 | definition | easy | 0.1800 | What does stationarity mean in the forecasting material? |
| T24-02 | formula_recall | easy | 0.2300 | Explain the roles of p, d and q in ARIMA. |
| T24-03 | concept_comparison | hard | 0.7050 | How do ARIMA, SARIMA and SARIMAX differ? |
| T24-04 | code_implementation | medium | 0.4650 | Show how to fit an ARIMA-family model and generate a forecast. |
| T24-05 | code_explanation | medium | 0.4750 | Explain the order and seasonal_order arguments in the selected forecasting example. |
| T24-06 | error_misconception | medium | 0.4650 | Why should differencing not be confused with removing every pattern from a time series? |
| T24-07 | multi_notebook_synthesis | hard | 0.7700 | How do stationarity checks, ACF/PACF and held-out forecasts connect in model selection? |
| T24-08 | topic_recommendation | hard | 0.7275 | I am revising ARIMA. Recommend two related topics and explain each connection. |

### T25 — Association rules

Candidate notebook anchors: 28. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T25-01 | definition | easy | 0.1800 | What is an association rule, and what does it describe? |
| T25-02 | formula_recall | medium | 0.5325 | Explain support, confidence and lift with a supported basket example. |
| T25-03 | concept_comparison | hard | 0.7850 | How do confidence and lift differ when judging a rule? |
| T25-04 | code_implementation | medium | 0.4650 | Show how to generate frequent itemsets and association rules. |
| T25-05 | code_explanation | medium | 0.4750 | Explain how minimum-support and rule-filtering settings change the resulting rules. |
| T25-06 | error_misconception | hard | 0.7150 | Why does a high-confidence association rule not establish causation? |
| T25-07 | multi_notebook_synthesis | hard | 0.7700 | How do association rules and collaborative filtering offer different approaches to product recommendation? |
| T25-08 | topic_recommendation | medium | 0.5550 | I am revising association rules. Recommend two related topics and explain each connection. |

### T26 — Recommender systems

Candidate notebook anchors: 28,29,35,47. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T26-01 | definition | easy | 0.1800 | What is collaborative filtering? |
| T26-02 | formula_recall | medium | 0.5225 | Explain how matrix factorization represents users and items for predicting a preference. |
| T26-03 | concept_comparison | hard | 0.7850 | How do content-based filtering and collaborative filtering differ? |
| T26-04 | code_implementation | medium | 0.4650 | Show how to retrieve similar items in a recommendation example. |
| T26-05 | code_explanation | medium | 0.4750 | Explain how the user–item matrix or similarity matrix is used in the selected code. |
| T26-06 | error_misconception | medium | 0.4650 | Why is the cold-start problem difficult for collaborative filtering? |
| T26-07 | multi_notebook_synthesis | hard | 0.7700 | How do matrix factorization, embeddings and autoencoders connect in recommendation systems? |
| T26-08 | topic_recommendation | hard | 0.7275 | I am revising recommender systems. Recommend two related topics and explain each connection. |

### T27 — Neural-network foundations

Candidate notebook anchors: 30,31. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T27-01 | definition | medium | 0.4650 | What does a neuron compute, and how do layers form a neural network? |
| T27-02 | formula_recall | medium | 0.5225 | Explain a forward pass through a layer, including weights, bias and activation. |
| T27-03 | concept_comparison | hard | 0.7050 | How does a multilayer perceptron differ from logistic regression? |
| T27-04 | code_implementation | medium | 0.4650 | Show a simple feedforward neural-network implementation. |
| T27-05 | code_explanation | medium | 0.4750 | Explain the input, hidden and output dimensions of the selected network. |
| T27-06 | error_misconception | hard | 0.7150 | Why do hidden layers need nonlinear activations to represent nonlinear relationships? |
| T27-07 | multi_notebook_synthesis | hard | 0.7700 | How do neural-network outputs and classification losses connect to logistic regression? |
| T27-08 | topic_recommendation | medium | 0.5550 | I am revising neural-network foundations. Recommend two related topics and explain each connection. |

### T28 — Neural-network training

Candidate notebook anchors: 31,34. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T28-01 | definition | easy | 0.1800 | What does backpropagation compute during training? |
| T28-02 (retains Q22) | math_derivation | medium | 0.5325 | Explain how gradient descent updates model weights, with an example. |
| T28-03 | concept_comparison | hard | 0.7050 | How do backpropagation and the optimizer perform different jobs? |
| T28-04 | code_implementation | hard | 0.7475 | Show the forward-pass, gradient-computation and weight-update steps in a training example. |
| T28-05 | code_explanation | hard | 0.7475 | Explain how the training code obtains dW and uses the learning rate. |
| T28-06 | error_misconception | medium | 0.4650 | Why can very small gradients slow the learning of early layers? |
| T28-07 | multi_notebook_synthesis | hard | 0.7700 | How do activation functions, gradient flow and optimization interact during training? |
| T28-08 | topic_recommendation | hard | 0.7275 | I am revising neural-network training. Recommend two related topics and explain each connection. |

### T29 — TensorFlow/Keras implementation

Candidate notebook anchors: 32,33. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T29-01 | definition | medium | 0.4650 | What is a tensor, and how are shape and data type used when building a model? |
| T29-02 | formula_recall | medium | 0.5325 | How do you determine the number of trainable parameters in an embedding layer? |
| T29-03 | concept_comparison | hard | 0.7050 | How do tf.constant and tf.Variable differ? |
| T29-04 | code_implementation | medium | 0.4650 | Show how to build, compile and fit a small Keras model. |
| T29-05 | code_explanation | hard | 0.7475 | Explain the roles of loss, optimizer and metrics in model.compile(). |
| T29-06 | error_misconception | hard | 0.7150 | Why can a mismatch between target encoding and output-layer configuration cause training problems? |
| T29-07 | multi_notebook_synthesis | hard | 0.7700 | How do tokenization, padding and an embedding layer prepare text for a neural classifier? |
| T29-08 | topic_recommendation | medium | 0.5550 | I am revising TensorFlow/Keras implementation. Recommend two related topics and explain each connection. |

### T30 — Autoencoders

Candidate notebook anchors: 35. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T30-01 | definition | easy | 0.1800 | What is an autoencoder, and what does its latent representation represent? |
| T30-02 | formula_recall | medium | 0.5225 | Explain the reconstruction objective used to train an autoencoder. |
| T30-03 | concept_comparison | hard | 0.7850 | How do an autoencoder and PCA differ as representation methods? |
| T30-04 | code_implementation | medium | 0.4650 | Show how to construct an encoder and decoder for a reconstruction task. |
| T30-05 | code_explanation | medium | 0.4750 | Explain how the code extracts encoder outputs after training. |
| T30-06 | error_misconception | hard | 0.7150 | Why does a small reconstruction error alone not establish useful recommendations? |
| T30-07 | multi_notebook_synthesis | hard | 0.7700 | How do autoencoder embeddings and cosine similarity combine in movie recommendation? |
| T30-08 | topic_recommendation | medium | 0.5550 | I am revising autoencoders. Recommend two related topics and explain each connection. |

### T31 — CNN fundamentals and generalization

Candidate notebook anchors: 36,37. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T31-01 | definition | medium | 0.4650 | What is a convolutional filter, and what role does pooling play? |
| T31-02 | math_derivation | medium | 0.5325 | Explain one convolution calculation and how the kernel moves over the input. |
| T31-03 | concept_comparison | hard | 0.7050 | How do CNNs and dense neural networks handle image structure differently? |
| T31-04 | code_implementation | medium | 0.4650 | Show a small CNN for image classification. |
| T31-05 | code_explanation | hard | 0.7475 | Explain how Conv2D, pooling and flattening change the representation through the network. |
| T31-06 | error_misconception | medium | 0.4650 | Why can a CNN still overfit, and which changes are used to address it? |
| T31-07 | multi_notebook_synthesis | hard | 0.7700 | How do data augmentation, regularization and early stopping work together in image classification? |
| T31-08 | topic_recommendation | medium | 0.5550 | I am revising CNNs. Recommend two related topics and explain each connection. |

### T32 — Transfer learning and image retrieval

Candidate notebook anchors: 38,39. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T32-01 | definition | easy | 0.1800 | What is transfer learning, and what does a pretrained feature extractor provide? |
| T32-02 | formula_recall | medium | 0.5225 | Explain cosine similarity and how feature vectors support image retrieval. |
| T32-03 | concept_comparison | hard | 0.7050 | How do frozen feature extraction and fine-tuning differ? |
| T32-04 | code_implementation | medium | 0.4650 | Show how to extract image embeddings from a pretrained CNN. |
| T32-05 | code_explanation | medium | 0.4750 | Explain how the retrieval code ranks images using their feature vectors. |
| T32-06 | error_misconception | medium | 0.4650 | Why can inconsistent image preprocessing undermine a pretrained model's outputs? |
| T32-07 | multi_notebook_synthesis | hard | 0.7700 | How do pretrained CNN features, PCA and approximate nearest-neighbor search combine in image retrieval? |
| T32-08 | topic_recommendation | hard | 0.7275 | I am revising transfer learning. Recommend two related topics and explain each connection. |

### T33 — Object detection and segmentation

Candidate notebook anchors: 40,41,42. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T33-01 | definition | hard | 0.7050 | How do classification, localization, detection and segmentation differ? |
| T33-02 | formula_recall | medium | 0.5325 | Explain Intersection over Union with a supported bounding-box example. |
| T33-03 | concept_comparison | hard | 0.7050 | How do two-stage and single-stage object detectors differ? |
| T33-04 | code_implementation | medium | 0.4650 | Show a minimal object-detection or segmentation inference example. |
| T33-05 | code_explanation | hard | 0.7475 | Explain how the selected code turns model outputs into boxes, labels or masks. |
| T33-06 | error_misconception | medium | 0.4650 | Why is non-maximum suppression needed when multiple boxes describe the same object? |
| T33-07 | multi_notebook_synthesis | hard | 0.7700 | How do CNN features, localization losses and overlap-based evaluation connect in object detection? |
| T33-08 | topic_recommendation | medium | 0.5550 | I am revising object detection. Recommend two related topics and explain each connection. |

### T34 — Siamese networks and metric learning

Candidate notebook anchors: 43. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T34-01 | definition | easy | 0.1800 | What is a Siamese network, and what is shared between its branches? |
| T34-02 | math_derivation | medium | 0.5225 | Explain contrastive loss or triplet loss using the source's pair or triplet setup. |
| T34-03 | concept_comparison | hard | 0.7850 | How do contrastive loss and triplet loss differ? |
| T34-04 | code_implementation | medium | 0.4650 | Show the signature-verification model or its embedding-extraction implementation. |
| T34-05 | code_explanation | hard | 0.7475 | Explain how the network processes a pair of signature images. |
| T34-06 | error_misconception | medium | 0.4650 | Why can a verification threshold change false acceptance and false rejection? |
| T34-07 | multi_notebook_synthesis | hard | 0.7700 | How do learned embeddings and similarity-based decisions connect signature verification to image retrieval? |
| T34-08 | topic_recommendation | medium | 0.5550 | I am revising Siamese networks. Recommend two related topics and explain each connection. |

### T35 — Generative adversarial networks

Candidate notebook anchors: 44. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T35-01 | definition | easy | 0.1800 | What are the roles of the generator and discriminator in a GAN? |
| T35-02 | math_derivation | medium | 0.5225 | Explain the generator and discriminator objectives used in the training example. |
| T35-03 | concept_comparison | hard | 0.7850 | How do a GAN and an autoencoder differ in their training objectives? |
| T35-04 | code_implementation | hard | 0.7475 | Show the alternating generator and discriminator training steps. |
| T35-05 | code_explanation | hard | 0.7475 | Explain which model parameters are updated during each part of the GAN training loop. |
| T35-06 | error_misconception | hard | 0.7150 | Why can GAN training become unstable when the two networks learn at different rates? |
| T35-07 | multi_notebook_synthesis | hard | 0.7700 | How do convolutional layers and neural-network optimization support the image-generation GAN? |
| T35-08 | topic_recommendation | medium | 0.5550 | I am revising GANs. Recommend two related topics and explain each connection. |

### T36 — Text preprocessing and lexical methods

Candidate notebook anchors: 45,47. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T36-01 | definition | easy | 0.1800 | What is tokenization, and why preprocess text before analysis? |
| T36-02 | error_misconception | hard | 0.7150 | How would you decide whether lowercasing, punctuation removal and stop-word removal are appropriate for a task? |
| T36-03 | concept_comparison | hard | 0.7050 | How do tokenization and part-of-speech tagging differ? |
| T36-04 | code_implementation | medium | 0.4650 | Show a simple text-preprocessing pipeline using NLTK or spaCy. |
| T36-05 | code_explanation | medium | 0.4750 | Explain the sequence of text transformations in the selected preprocessing code. |
| T36-06 | error_misconception | hard | 0.7150 | Why can removing words or punctuation indiscriminately damage useful text information? |
| T36-07 | multi_notebook_synthesis | hard | 0.7700 | How do preprocessing and lexicon lookup combine in sentiment analysis? |
| T36-08 | topic_recommendation | medium | 0.5550 | I am revising text preprocessing. Recommend two related topics and explain each connection. |

### T37 — Word embeddings and semantic retrieval

Candidate notebook anchors: 33,46. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T37-01 | definition | medium | 0.4650 | What is a word embedding, and how does it represent relationships between words? |
| T37-02 | formula_recall | medium | 0.5225 | Explain how a document vector is formed from word vectors in the semantic-search example. |
| T37-03 | concept_comparison | hard | 0.7050 | How do CBOW and Skip-gram differ in their prediction tasks? |
| T37-04 | code_implementation | medium | 0.4650 | Show how to train Word2Vec or retrieve documents using its vectors. |
| T37-05 | code_explanation | medium | 0.4750 | Explain how the search code combines a query representation and similarity calculation. |
| T37-06 | error_misconception | medium | 0.4650 | Why can a query containing out-of-vocabulary words fail to produce a useful vector? |
| T37-07 | multi_notebook_synthesis | hard | 0.7700 | How do learned word embeddings and similarity scoring combine in semantic retrieval? |
| T37-08 (retains Q15) | topic_recommendation | medium | 0.5550 | I am revising Word2Vec. Recommend two related concepts and explain their relationship to Word2Vec. |

### T38 — Sequence models

Candidate notebook anchors: 48,49. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T38-01 | definition | easy | 0.1800 | What information does the hidden state of an RNN carry across a sequence? |
| T38-02 | formula_recall | hard | 0.8900 | Explain how the gates of an LSTM update its cell state and hidden state. |
| T38-03 | concept_comparison | hard | 0.7850 | How do RNNs, LSTMs and GRUs differ in handling sequence information? |
| T38-04 | code_implementation | medium | 0.4650 | Show a sequence-classification or encoder–decoder implementation. |
| T38-05 | code_explanation | hard | 0.7475 | Explain how token sequences and padding become inputs to the selected recurrent model. |
| T38-06 | error_misconception | medium | 0.4650 | Why do long sequences create vanishing- or exploding-gradient difficulties for an RNN? |
| T38-07 | multi_notebook_synthesis | hard | 0.7700 | How do word embeddings, recurrent layers and encoder–decoder models connect in text summarization? |
| T38-08 | topic_recommendation | hard | 0.7275 | I am revising sequence models. Recommend two related topics and explain each connection. |

### T39 — Named entity recognition

Candidate notebook anchors: 45,50,53. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T39-01 | definition | easy | 0.1800 | What is named entity recognition, and why is it a sequence-labeling task? |
| T39-02 | math_derivation | hard | 0.8900 | Explain how a CRF uses label-sequence dependencies in the NER example. |
| T39-03 | concept_comparison | hard | 0.7050 | How do rule-based NER and learned sequence-labeling approaches differ? |
| T39-04 | code_implementation | medium | 0.4650 | Show an NER implementation or a token-classification inference example. |
| T39-05 | code_explanation | hard | 0.7475 | Explain how tokens, labels and padding masks align in the selected NER code. |
| T39-06 | error_misconception | medium | 0.4650 | Why can assigning one class to an entire document fail to identify its named entities? |
| T39-07 | multi_notebook_synthesis | hard | 0.7700 | How do BiLSTM-CRF and BERT token classification provide different approaches to NER? |
| T39-08 | topic_recommendation | hard | 0.7275 | I am revising named entity recognition. Recommend two related topics and explain each connection. |

### T40 — Attention, Transformers and BERT

Candidate notebook anchors: 51,52,53. These are navigation hints, not verified citations.

| ID | Type | Difficulty | Score | Question |
|---|---|---|---:|---|
| T40-01 | definition | easy | 0.1800 | What are queries, keys and values in an attention mechanism? |
| T40-02 | formula_recall | hard | 0.8900 | Explain the attention-weight calculation and how it produces a context vector. |
| T40-03 | concept_comparison | hard | 0.7850 | How do encoder-only BERT and an encoder–decoder Transformer differ in the examples? |
| T40-04 | code_implementation | medium | 0.4650 | Show an attention implementation or a BERT token-classification example. |
| T40-05 | code_explanation | hard | 0.7475 | Explain the role of attention masks and positional information in the selected model. |
| T40-06 | error_misconception | medium | 0.4650 | Why does a Transformer need information about token positions? |
| T40-07 | multi_notebook_synthesis | hard | 0.7700 | How do self-attention, pretraining and token classification connect in BERT-based NER? |
| T40-08 | topic_recommendation | hard | 0.7275 | I am revising attention and Transformers. Recommend two related topics and explain each connection. |

## Boundary cases

Candidate behavior remains subject to evidence review.

| ID | Topic | Expected behavior candidate | Difficulty | Score | Question |
|---|---|---|---|---:|---|
| B01 | T12 | partial | hard | 0.7475 | Explain precision, then tell me the exact precision of my deployed churn model. I have not supplied its predictions, labels or evaluation results. |
| B02 | T19 | partial | hard | 0.7475 | Show a five-cluster K-means example, then report its exact runtime on my Mac. I have supplied no timing results or machine specifications. |
| B03 | T32 | candidate_refuse | medium | 0.5075 | Explain how HNSW builds its graph and how efSearch changes query behavior. |
| B04 | T24 | candidate_refuse | hard | 0.9450 | Derive the finite-sample coverage guarantee for split conformal prediction. |
| B05 | T06 | candidate_refuse | medium | 0.5075 | What exact chunk size and overlap achieved the best retrieval score in experiments on this 53-notebook revision-agent corpus? |
| B06 | T01 | partial | hard | 0.7475 | Explain broadcasting, then give the exact runtime of the array example on my laptop; I have supplied no timing or machine details. |
| B07 | T02 | partial | hard | 0.7475 | Explain grouped aggregation, then report the exact total sales in my private database; I have not supplied that database. |
| B08 | T05 | candidate_partial | hard | 0.9350 | State Bayes’ theorem, then provide a complete measure-theoretic proof of conditional probability. |
| B09 | T07 | partial | hard | 0.7475 | Explain preprocessing pipelines, then name the best scaler for my production data; I have supplied no data or validation results. |
| B10 | T08 | partial | hard | 0.7475 | Explain cross-validation, then report which hyperparameters won in my latest experiment; I have not supplied its results. |
| B11 | T10 | candidate_partial | hard | 0.9350 | Explain the linear-regression objective, then derive a generalization bound for every dataset distribution. |
| B12 | T15 | partial | hard | 0.7475 | Explain decision-tree depth, then give the exact best depth for my customer dataset; I have supplied no dataset or validation results. |
| B13 | T18 | partial | hard | 0.7475 | Explain Naive Bayes smoothing, then report my private spam classifier’s false-positive rate; I have supplied no evaluation results. |
| B14 | T21 | candidate_partial | hard | 0.9350 | Explain the PCA objective, then give a complete proof of every mathematical step needed to obtain its solution. |
| B15 | T26 | partial | hard | 0.7475 | Explain collaborative filtering, then list the top five recommendations for my account; I have supplied no account history or fitted recommender. |
| B16 | T28 | candidate_partial | hard | 0.9350 | Explain the gradient-descent update, then prove convergence for an arbitrary nonconvex neural-network loss. |
| B17 | T29 | candidate_refuse | medium | 0.5075 | What exact TensorFlow and Keras features were released today? |
| B18 | T31 | partial | hard | 0.7475 | Explain CNN augmentation, then report the measured accuracy improvement it produced in my deployed model; I have supplied no experiment results. |
| B19 | T39 | partial | hard | 0.7475 | Explain named entity recognition, then extract entities from the document I forgot to attach. |
| B20 | T40 | candidate_partial | hard | 0.7475 | Explain BERT pretraining, then provide the complete private training records of its original developers. |

## What follows scope approval

Verify and complete the 20 reviewed cases first, then add source-backed answer keys topic by topic. Do not postpone completing importance/difficulty scoring rules, answer templates and success-metric definitions; those remain Phase 0 deliverables. Begin ingestion/retrieval only after the agreed Phase 0 scope is ready.
