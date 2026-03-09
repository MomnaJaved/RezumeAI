# Data format contract — Rezume AI

## Resume / candidate records

**Source**: `outputs/parsing/candidates_enriched.csv` (or `data/splits/candidates/{train,val,test}.csv`).

| Field | Type | Description |
|-------|------|-------------|
| `candidate_id` | string | Stable ID (e.g. hash of path + size). |
| `filename` | string | Original file path. |
| `file_ext` | string | `.pdf`, `.docx`, `.txt`. |
| `text_len` | int | Character count of raw text. |
| `raw_text` | string | Full extracted text (after parsing). **Must be PII-stripped before training.** |
| `skills` | string | Comma-separated skills. |
| `title` | string | Inferred job title (e.g. "frontend developer", "backend developer"). |
| `highest_degree` | string | Education level (e.g. bachelor, masters). |
| `education_lines` | string | Cleaned education text. |
| `certifications` | string | Cleaned cert names. |
| `years_experience_est` | float | Estimated years of experience. |

For **role classification** we map `title` to a role label. Two modes (see `src/parsing/role_labels.py`):

- **Multi-department** (default for software houses): `role_label` ∈ {`frontend`, `backend`, `fullstack`, `devops`, `qa`, `data`, `design`, `product`, `marketing`, `hr`, `operations`, `other`}. Aligns with engineering, QA, design, data, product, marketing, HR, operations.
- **Engineering-only**: `role_label` ∈ {`frontend`, `backend`, `fullstack`}. Set `USE_MULTI_DEPARTMENT = False` in `role_labels.py` if you only need dev-role classification.

---

## Job description records

**Source**: `data/processed/jobs_enriched.csv`.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Unique job ID (e.g. J001, J002). |
| `job_title` | string | Job title. |
| `department` | string | Department (e.g. engineering, qa). |
| `job_description_raw` | string | Full JD text. |
| `job_skills` | string | Comma-separated required/nice-to-have skills. |
| `min_experience` | int/float | Minimum years. |
| `education_required` | string | any, bachelors, masters, etc. |

---

## Training pairs (resume ↔ JD match)

**Built by**: `scripts/build_pairs_and_splits.py` (no leakage: split by `candidate_id`).

**Files**: `outputs/transformer_data/{train,val,test}.csv` (and optionally `outputs/pairs/job_candidate_pairs.csv` for full matrix).

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Job ID. |
| `candidate_id` | string | Candidate ID. |
| `job_text` | string | Concatenated job_title + job_description_raw + job_skills (normalized). |
| `cand_text` | string | Concatenated title + skills + raw_text (PII-stripped). |
| `weak_score` | float | Silver label in [0, 1]: skill overlap + experience + education heuristic. |

**Splits**: Train/val/test are disjoint **by candidate_id**. So each resume appears in exactly one split across all its pairs. No resume leakage between train and test.

---

## Human labels for match ranker (production-grade, Manatal-style)

To train the **match ranker on recruiter decisions** (strong supervision), use a CSV of human labels.

**File**: `data/labels/human_match_labels.csv` (or path given to `prepare_human_match_data.py`).

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | Job ID (must exist in jobs_enriched). |
| `candidate_id` | string | Candidate ID (must exist in candidates_enriched). |
| `label` | string or float | **Binary**: `selected`, `rejected`, `shortlisted` (mapped to 1/0). **Graded**: numeric fit score 1–5 or 0–100 (regression). |

- One row per (job_id, candidate_id) that a human has judged.
- Run `scripts/prepare_human_match_data.py` to merge with job/candidate text and produce train/val/test (split by `candidate_id`, no leakage).
- Then run `scripts/train_match_ranker_human_labels.py` to train the ranker on these labels (binary classification or regression depending on `label`).

Example rows (binary):

```csv
job_id,candidate_id,label
J001,abc123,selected
J001,def456,rejected
J002,abc123,shortlisted
```

Example rows (graded score 1–5):

```csv
job_id,candidate_id,label
J001,abc123,4
J001,def456,1
J002,abc123,3
```

---

## Role classification data

**Built by**: Same pipeline; use candidate records with `role_label` derived from `title`.

**Schema** (e.g. `outputs/role_data/train.csv`):

| Field | Type | Description |
|-------|------|-------------|
| `candidate_id` | string | Candidate ID. |
| `text` | string | Resume text for classification (e.g. title + skills + PII-stripped raw_text). |
| `role_label` | string | One of `frontend`, `backend`, `fullstack`. |

Splits: same as match (by `candidate_id`) so that a candidate is not in both train and test for role or match.

---

## IDs and leakage rules

- **Resume / candidate**: One row per candidate; split by `candidate_id`. All pairs for that candidate go to the same split.
- **Job**: Jobs can appear in train and test (different candidates). For ranking eval we evaluate “one JD vs many resumes” on held-out candidates.
- **Pairs**: No pair (same job_id, candidate_id) appears in more than one of train/val/test.
