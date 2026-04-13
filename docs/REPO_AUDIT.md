# Rezume AI — Repo Audit & Design Corrections

## 1. REPO AUDIT

### 1.1 Repository structure (relevant paths)

| Path | Purpose |
|------|--------|
| `data/processed/jobs_enriched.csv` | Processed JDs (job_id, job_title, job_description_raw, job_skills, etc.) |
| `data/splits/candidates/{train,val,test}.csv` | Candidate splits (same schema as enriched; used for role) |
| `data/raw/` | Raw resumes (referenced; structure may vary) |
| `outputs/parsing/candidates_enriched.csv` | Parsed + enriched candidates (title, skills, raw_text, …) |
| `outputs/pairs/job_candidate_pairs.csv` | All job–candidate pairs with weak_score |
| `outputs/transformer_data/{train,val,test}.csv` | Pair-level data for match model (job_text, cand_text, weak_score) |
| `outputs/rankings/` | TF-IDF and transformer rankings per job |
| `training/scripts/` | parse resumes → build final rankings + training/eval scripts |
| `src/parsing/` | role_inference, title_extractor, title_cleaner, skill_mining, feature_extractors, text_extractors |
| `models/transformer/ranker_roberta/` | Saved cross-encoder ranker (config + checkpoints) |

### 1.2 What already exists

- **Data ingestion / preprocessing**  
  - Resume parsing: `training/scripts/parse_resumes.py` → `candidates.csv`; `training/scripts/rebuild_candidates_enriched.py` adds title, education, certs, years_experience.  
  - Job parsing: `training/scripts/parse_jobs.py`, `training/scripts/enrich_jobs.py` → `jobs_enriched.csv`.  
  - **No PII removal**: `raw_text` and other fields contain names, emails, phones, addresses. These are used as features (TF-IDF and transformer), which is a privacy and fairness risk.

- **Label schema**  
  - **Role**: Rule-based in `src/parsing/role_inference.py` (ROLE_RULES) → many roles (e.g. "frontend developer", "backend developer", "full stack developer"). Stored in `title` in candidates_enriched. No dedicated 3-class (frontend/backend/fullstack) training labels yet.  
  - **Match**: No human labels. `training/scripts/build_pairs_and_weak_scores.py` computes `weak_score` (skill overlap + experience + education). Used as silver target for the transformer ranker.

- **Model training**  
  - Match: `training/scripts/train_transformer_ranker.py` — cross-encoder (RoBERTa sequence classification, `num_labels=1`, regression on `weak_score`). Uses `distilroberta-base`; no YAML/CLI config, no explicit seeds.  
  - Role: **No training script**. Role is rule-based only; no fine-tuned classifier for frontend/backend/fullstack.

- **Evaluation**  
  - Match: Only MSE/MAE in Trainer. **No ranking metrics** (NDCG@10, Recall@10, Spearman).  
  - Role: No accuracy, macro-F1, or confusion matrix.

- **Saved artifacts**  
  - `models/transformer/ranker_roberta/` has config, tokenizer, checkpoints.  
  - No unified `artifacts/` layout; no exported role classifier; no single inference API.

- **API / NestJS**  
  - No FastAPI or Node-callable inference service. NestJS cannot call the current Python pipeline.

### 1.3 What is wrong or risky

1. **Data leakage (critical)**  
   `training/scripts/prepare_transformer_data.py` (old version) split **by row** (train_test_split on pairs). The same candidate can appear in train (with one job) and in test (with another job). The model can effectively memorize resume representations. **Fix**: `training/scripts/build_pairs_and_splits.py` now splits by `candidate_id` so each entity appears in only one split.

2. **No PII stripping**  
   Resumes contain names, emails, phones, addresses. Using them in training (and in production) is a privacy and bias risk. **Fix**: Add PII stripping before any training or inference.

3. **Weak / silver labels**  
   `weak_score` is heuristic, not human relevance. Acceptable for FYP baseline, but must be documented and not over-interpreted.

4. **Missing role classifier training**  
   Proposal requires a role classifier (frontend/backend/fullstack). Currently only rule-based inference exists. **Fix**: Add labeled data (map existing `title` to 3 classes or use rule-based labels) and a training script.

5. **Insufficient evaluation**  
   - Match: Need Spearman correlation with weak_score, and ranking metrics (NDCG@10, Recall@10) in a “one JD vs many resumes” setup.  
   - Role: Need accuracy, macro-F1, confusion matrix.

6. **requirements.txt**  
   Missing `torch`, `transformers`, `datasets` (and optionally `pyyaml`). Fresh install fails for transformer training.

7. **TF-IDF baseline**  
   Correct use of TF-IDF + cosine (linear_kernel on L2-normalized vectors). Good. No explicit evaluation script comparing TF-IDF vs transformer rankings.

8. **Ad-hoc final ranking**  
   `training/scripts/build_final_rankings.py` uses hardcoded job ID, manual weights (0.2 weak + 0.3 TF-IDF + 0.5 transformer) and title_boost. Fine for demo; should be configurable and documented.

---

## 2. DESIGN CORRECTIONS (aligned with proposal)

### A) Baseline: TF-IDF + cosine similarity

- **Keep** existing `training/scripts/tfidf_baseline_ranker.py` (TF-IDF on job + candidate text, cosine similarity, top-K per job).  
- Add evaluation: compare TF-IDF vs transformer with NDCG@10 and Recall@10 using weak_score as proxy relevance.

### B) Role classifier: RoBERTa on resume → {frontend, backend, fullstack}

- **Add** a 3-class classifier fine-tuned on resume text (and optionally title/skills).  
- Labels: map existing `title` from ROLE_RULES to `frontend` | `backend` | `fullstack`; treat others as “fullstack” or drop/merge by policy.  
- Output: label + probabilities for NestJS/API.

### C) Match scoring: one approach

- **Current**: Cross-encoder (pair → regression score). Good accuracy, slower at inference (one forward per pair).  
- **Alternative**: Bi-encoder (embed resume and JD separately, cosine similarity). Faster for “one JD vs many resumes”, but typically slightly worse than cross-encoder for accuracy.  
- **Recommendation**: **Keep cross-encoder** for FYP: you already have it, weak_score is pair-level, and ranking is offline/small-scale (one JD vs N resumes). If later you need low latency at scale, add a bi-encoder and use it for first-stage retrieval.  
- **Justification (5–8 bullets)**:
  - Cross-encoder matches your current data (pair + continuous weak_score).
  - No need to maintain two embedding spaces and negative sampling.
  - FYP scope and “one JD vs many resumes” can be served with batching.
  - Better accuracy for limited labeled (silver) data.
  - Bi-encoder would require more engineering (hard negatives, separate embed + index).
  - You can export a single model (cross-encoder) to `artifacts/` and call it from NestJS via FastAPI.
  - If timeline is tight, keeping one model reduces risk.
  - Later upgrade path: replace or ensemble with a bi-encoder without changing the API contract (same `match_score(resume, jd)`).

---

## 3. Implementation summary (what was added/changed)

- **Data contract**: Documented schema; script to build (resume, JD, label) pairs and **splits by candidate_id** (no leakage).  
- **PII**: Module to strip names, emails, phones, addresses; applied before training and in inference.  
- **Role classifier**: Training script (Hugging Face + PyTorch), config/CLI, seeds; evaluation (accuracy, macro-F1, confusion matrix).  
- **Match pipeline**: Leak-free splits in data prep; evaluation script (Spearman, NDCG@10, Recall@10).  
- **Artifacts**: `artifacts/role_classifier/`, `artifacts/match_ranker/`; inference module `classify_role`, `match_score`; optional TF-IDF baseline in inference.  
- **Integration**: FastAPI server with `/classify_role` and `/match_score`; example request/response for NestJS.  
- **Safety**: PII check in pipeline; optional group warning; TF-IDF top keywords + short note for transformer explainability.

---

## 4. File map (new/updated)

| File | Purpose |
|------|--------|
| `docs/DATA_CONTRACT.md` | JSON/CSV schema for resumes, JDs, pairs, splits |
| `src/preprocessing/pii.py` | PII stripping (names, emails, phones, addresses) |
| `training/scripts/build_pairs_and_splits.py` | Pairs + train/val/test by candidate_id (no leakage) |
| `training/scripts/train_role_classifier.py` | RoBERTa 3-class role training |
| `training/scripts/train_match_ranker.py` | Cross-encoder training (config + seed) |
| `training/scripts/evaluate_rankings.py` | NDCG@10, Recall@10, Spearman |
| `training/scripts/evaluate_role_classifier.py` | Accuracy, macro-F1, confusion matrix |
| `src/inference/__init__.py` | `classify_role`, `match_score`, TF-IDF baseline |
| `artifacts/` | Role model + tokenizer; match model + tokenizer |
| `backend/api/` | FastAPI server (run with `PYTHONPATH=backend`) |
| `training/config/train_role.yaml`, `training/config/train_match.yaml` | Training configs |
| `requirements-train.txt` | torch, transformers, datasets, pyyaml, etc. |
| `README.md` (or `docs/HOW_TO_RUN.md`) | How to run: venv, data, baseline, train role, train match, eval, inference server |
