# Why Two Models? Which Models? Weak vs Strong Supervision

## Why two trained models?

Rezume AI (like Manatal-style ATS) needs **two different tasks**:

1. **Role classification** — “What role/department is this candidate?”  
   - Input: resume text.  
   - Output: label (e.g. frontend, backend, fullstack, devops, qa, data, design, …).  
   - Use: routing, filters, AI insights (“this candidate is a backend developer”), dashboards.

2. **Match / ranking** — “How well does this candidate fit this job?”  
   - Input: (resume text, job description text).  
   - Output: match score (for ranking and candidate selection).  
   - Use: shortlisting, ranking, “top 10 for this JD”, selection decisions.

We use **two separate fine-tuned models** (one per task) because:
- Different inputs/outputs (single text vs pair; classification vs score).
- Cleaner training and evaluation (no multi-task balancing).
- You can improve or replace one without retraining the other.

Manatal and similar ATS often use multiple models or multi-task setups; our two-model design is a clear, production-ready split.

---

## Which models are these? (BERT vs RoBERTa)

- **Base architectures**: We use the **RoBERTa** family (DistilRoBERTa for speed, RoBERTa-base for accuracy).  
  - RoBERTa is an improved BERT (same encoder style, better pretraining).  
  - So we **are** using “BERT-like” transformers; RoBERTa is the preferred choice in our configs.

- **Model 1 — Role classifier**  
  - Base: `distilroberta-base` or `roberta-base` (see `config/train_role.yaml`).  
  - Fine-tuned on: resume text → role_label (multi-department or engineering-only).  
  - Artifact: `artifacts/role_classifier/`.

- **Model 2 — Match ranker**  
  - Base: `distilroberta-base` or `roberta-base` (see `config/train_match.yaml`).  
  - Fine-tuned on: (resume, JD) pair → score (for ranking / candidate selection).  
  - Artifact: `artifacts/match_ranker/`.

Both are **fine-tuned** for your tasks; they are not “just BERT/RoBERTa out of the box.” You can switch `model_name` in the YAML to `roberta-base` for higher quality or keep `distilroberta-base` for faster training and inference.

---

## Why is this “weakly supervised” (FYP)?

**Weak supervision** = training labels are **not** human-annotated; they are **derived by rules or heuristics**.

- **Match ranker (current)**  
  - Labels come from **weak_score**: a formula (skill overlap + experience + education).  
  - No human “selected” / “rejected” or “fit 1–5” labels.  
  - So the model learns to mimic the heuristic, not true recruiter decisions.  
  - Good for FYP baseline and demos; not production-grade for real hiring.

- **Role classifier (current)**  
  - Labels come from **rule-based mapping** of parsed title/skills to role (e.g. “backend developer” → backend).  
  - No human-verified “this resume is backend” labels.  
  - Again, fine for FYP; for production you’d want human or verified role labels.

For a **stronger, production-grade system (e.g. like Manatal)** you need **human labels**, e.g.:
- **Selection**: “selected”, “rejected”, “shortlisted”.  
- **Fit score**: 1–5 or 0–100 from recruiters.  
- Optionally: human-verified role per resume.

Then you train the **match ranker** (and optionally the role classifier) on those human labels. See below and `docs/DATA_CONTRACT.md` (human labels) for the schema and `scripts/train_match_ranker_human_labels.py` for the training path.

---

## Summary

| Piece            | What it is                          | Base model        | Current labels     | Production upgrade        |
|------------------|-------------------------------------|-------------------|--------------------|---------------------------|
| Role classifier  | Resume → role (routing, insights)   | RoBERTa/DistilRoBERTa | Rule-based role   | Human role labels         |
| Match ranker     | (Resume, JD) → score (ranking)      | RoBERTa/DistilRoBERTa | weak_score (heuristic) | Human selected/rejected or fit 1–5 |

Both models are **real, fine-tuned transformers** used for candidate selection, ranking, and AI insights; the “weak” part is the **source of the labels**, not the model architecture.
