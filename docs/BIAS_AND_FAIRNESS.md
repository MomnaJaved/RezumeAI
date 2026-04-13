# Bias, PII, and fairness (Rezume AI)

## What the code does today

1. **`strip_pii` (`src/preprocessing/pii.py`)**  
   Replaces emails, phone-like patterns, and common URL/social patterns with placeholders before model inference and in parts of training. This reduces the chance that the model uses **contact strings** or profile URLs as shortcuts.

2. **Structured features**  
   Explainability endpoints combine **job skills vs candidate skills**, **experience vs `min_experience`**, and **education vs `education_required`** so reviewers can see a transparent, rule-based breakdown alongside the neural score.

3. **No “fairness by regex” on pronouns**  
   Aggressively stripping words like *he/she* from running text is **not** enabled by default: it breaks legitimate sentences (including job descriptions) and is a weak substitute for real fairness evaluation.

## What still requires human process

- **Historical bias** in resumes and JDs is not removed by PII stripping.
- **Silver labels** (`weak_score`) encode heuristic assumptions; they are not neutral “ground truth.”
- **Disparate impact** should be measured when you have sensitive attributes or proxies and **human relevance labels**.

## Recommendations for an FYP write-up

- State clearly that automation **supports** but does not replace human hiring decisions.
- Document PII handling and the limitations above.
- If possible, report error analysis by cohort (when labels exist) and describe mitigation (human review, threshold tuning, retraining).
