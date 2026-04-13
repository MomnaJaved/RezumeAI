# Model evaluation (Rezume AI)

## Ranker (cross-encoder)

Script: `training/evaluation/evaluate_ranker.py`

**Metrics (weak supervision):**

- Spearman correlation between model scores and `weak_score` (continuous silver label).
- **NDCG@K** using graded `weak_score` in model sort order.
- **MAP** with binary relevance (`weak_score >= 0.5`).
- **Precision@K** and **Recall@K** with the same binary definition.

**Data:**

- Default: `outputs/transformer_data/test.csv` (held-out pairs, leak-safe splits from training).
- Fallback: `python training/evaluation/evaluate_ranker.py --mock` generates `training/evaluation/fixtures/mock_rank_pairs.csv` if needed.

**Outputs:**

- `outputs/evaluation/ranker_metrics.json`
- `outputs/evaluation/ranker_metrics.csv`

**Run (repo root, venv with `requirements-train.txt`):**

```bash
export PYTHONPATH="${PWD}:${PYTHONPATH}"
python training/evaluation/evaluate_ranker.py
python training/evaluation/evaluate_ranker.py --mock --k 10
```

Requires `artifacts/match_ranker/` (train with `training/scripts/train_match_ranker.py`).

**Legacy script:** `training/scripts/evaluate_rankings.py` (subset of metrics; prefer `training/evaluation/`).

---

## Role classifier

Script: `training/evaluation/evaluate_classifier.py`

**Metrics:**

- Accuracy, macro precision, recall, F1 (plus per-class report and confusion matrix in JSON).

**Data:**

- Default: `outputs/role_data/test.csv`
- `--mock` writes `training/evaluation/fixtures/mock_role_test.csv` if missing.

**Outputs:**

- `outputs/evaluation/classifier_metrics.json`
- `outputs/evaluation/classifier_metrics.csv` (summary row)

**Run:**

```bash
python training/evaluation/evaluate_classifier.py
python training/evaluation/evaluate_classifier.py --mock
```

Requires `artifacts/role_classifier/`.

---

## Human labels (best hiring proxy)

Weak scores are **heuristic**, not recruiter judgments. For thesis-quality evaluation, use **real human judgments**.

### Human-in-the-loop from the ranking UI (your idea)

When the model shows a ranked list and the recruiter **clicks “shortlist” / “select” / “reject”**, that action is a **valid supervision signal**:

- **Positive signal:** “I want this person for this job” (or shortlist) → treat as **relevant** (label 1) for the (job, resume) pair.
- **Negative signal:** explicit reject → **not relevant** (label 0).

**Important:** The running API does **not** change neural network weights in real time. Learning happens in a **second phase**:

1. **Log** each action (job id, candidate id, action, rank shown, model score at click).
2. **Export** to CSV (see below).
3. **Merge** with `job_text` / `cand_text` from your DB or enriched CSVs.
4. **Retrain or fine-tune** the cross-encoder (or train a small reranker) on those pairs with held-out evaluation.

That is standard **implicit feedback** / **learning-to-rank** practice: same idea as “which search result did the user click?”

**Caveats for the write-up:**

- **Position bias:** people click top results more often; store `rank_position_shown` and discuss in the thesis.
- **Sparse negatives:** if you only log positives, add a policy for negatives (e.g. random non-selected from top-10, or explicit reject only).
- **Leakage:** split by `candidate_id` or time when building train/test.

### API + export (implemented in repo)

- **`POST /api/v1/feedback/ranking-selection`** — body: `job_external_id`, `candidate_external_id`, `action`, optional `rank_position_shown`, `model_score_at_feedback`, `notes`.
- **`GET /api/v1/feedback/ranking-selection/summary`** — count of logged events.
- **Export:** `python training/scripts/export_human_feedback.py` → `outputs/evaluation/human_feedback_export.csv` (uses same `DATABASE_URL` as the API).

- **Merge (ranker training shape):** `python training/scripts/merge_human_feedback_for_ranker.py` → `outputs/evaluation/human_feedback_for_ranker.csv` with columns `job_text`, `cand_text`, `weak_score` (mapped from action: **Select** → 1.0, **Shortlist** → 0.85, **Reject** → 0.0) plus `job_id`, `candidate_id`, and audit fields. Default source is the **API database**; use `--source csv` with `--jobs-csv` / `--candidates-csv` if you only have enriched CSVs. By default the script keeps the **latest** event per (job, candidate); pass `--no-dedupe` to keep every click.

**Frontend:** On the job detail page, each ranking table has **Select / Shortlist / Reject**, which call `POST /api/v1/feedback/ranking-selection` with **1-based rank** and **cross-encoder score** at click time.

**Fine-tune the cross-encoder** (small human set + silver validation is a common pattern):

```bash
export PYTHONPATH="${PWD}:${PYTHONPATH}"
python training/scripts/train_match_ranker.py \
  --train outputs/evaluation/human_feedback_for_ranker.csv \
  --val outputs/transformer_data/val.csv
```
