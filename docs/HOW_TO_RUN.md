# How to Run — Rezume AI Training & Inference

## 1. Create venv and install dependencies

```bash
cd /path/to/RezumeAI
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-train.txt
```

## 2. Prepare data

- **Resumes**: Place PDF/DOCX/TXT resumes in `data/raw/resumes_extracted/` (or your configured raw path).
- **Jobs**: Ensure `data/processed/jobs_enriched.csv` exists (run job parsing/enrichment if needed).

```bash
# Parse resumes -> candidates.csv
python scripts/parse_resumes.py

# Enrich candidates (title, skills, education, etc.) -> candidates_enriched.csv
python scripts/rebuild_candidates_enriched.py
```

## 3. Build pairs and splits (no leakage)

Splits by `candidate_id` so each resume appears in only one of train/val/test.

```bash
python scripts/build_pairs_and_splits.py --train 0.8 --val 0.1 --seed 42
# Optional: --sample-per-job 2000 to subsample pairs per job for faster training
```

Output: `outputs/transformer_data/train.csv`, `val.csv`, `test.csv` (columns: job_id, candidate_id, job_text, cand_text, weak_score).

## 4. Run TF-IDF baseline

```bash
python scripts/tfidf_baseline_ranker.py
```

Output: `outputs/rankings/tfidf_rankings.csv` (top-K candidates per job by cosine similarity).

## 5. Prepare role data and train role classifier

```bash
python scripts/prepare_role_data.py
python scripts/train_role_classifier.py --config config/train_role.yaml
```

Optional: `--model distilroberta-base`, `--epochs 3`, `--output-dir artifacts/role_classifier`.  
Model and tokenizer are saved under `artifacts/role_classifier/`.

## 6. Train match ranker (weak supervision)

Uses the same leak-free splits from step 3. Labels = **weak_score** (heuristic), not human decisions.

```bash
python scripts/train_match_ranker.py --config config/train_match.yaml
```

Optional: `--model roberta-base`, `--epochs 2`, `--output-dir artifacts/match_ranker`.  
Model and tokenizer are saved under `artifacts/match_ranker/`.

## 7. Run evaluation

**Role classifier** (accuracy, macro-F1, confusion matrix):

```bash
python scripts/evaluate_role_classifier.py
```

**Match / ranking** (Spearman, NDCG@10, Recall@10 on test set):

```bash
python scripts/evaluate_rankings.py
```

## 8. Start inference server (for NestJS)

```bash
python api/inference_server.py
# Or: uvicorn api.inference_server:app --host 0.0.0.0 --port 8000
```

- **Health**: `GET http://localhost:8000/health`
- **Classify role**: `POST http://localhost:8000/classify_role`  
  Body: `{"resume_text": "Experienced developer with React and Node.js..."}`  
  Response: `{"label": "fullstack", "probs": {"frontend": 0.1, "backend": 0.2, "fullstack": 0.7}}`
- **Match score**: `POST http://localhost:8000/match_score`  
  Body: `{"resume_text": "...", "jd_text": "We are hiring a Backend Developer..."}`  
  Response: `{"score": 0.82}`

NestJS can call these endpoints via HTTP client (e.g. axios or fetch).

## 9. Safety checks (optional)

```bash
python scripts/safety_checks.py
```

Checks for PII in training data and prints a short recommendation. Run after building pairs/role data.

---

## Quick reference

| Step | Command |
|------|--------|
| Venv + deps | `pip install -r requirements.txt && pip install -r requirements-train.txt` |
| Parse resumes | `python scripts/02_parse_resumes.py` |
| Enrich candidates | `python scripts/10_rebuild_candidates_enriched.py` |
| Pairs + splits | `python scripts/build_pairs_and_splits.py` |
| TF-IDF baseline | `python scripts/05_tfidf_baseline.py` |
| Role data | `python scripts/prepare_role_data.py` |
| Train role | `python scripts/train_role_classifier.py` |
| Train match | `python scripts/train_match_ranker.py` |
| Eval role | `python scripts/evaluate_role_classifier.py` |
| Eval ranking | `python scripts/evaluate_rankings.py` |
| Inference server | `python api/inference_server.py` |
