from __future__ import annotations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
IN_DIR = ROOT / "data" / "raw" / "jobs_inbox"
IN_DIR.mkdir(parents=True, exist_ok=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/03_add_job.py 'Backend Developer Node.js'")
        raise SystemExit(1)

    title = sys.argv[1].strip()
    fname = title.lower().replace("/", " ").replace("\\", " ").replace("  ", " ").replace(" ", "_")
    path = IN_DIR / f"{fname}.txt"

    print("Paste job description. End with CTRL+D (mac) / CTRL+Z (windows).")
    jd = sys.stdin.read().strip()

    if not jd:
        raise SystemExit("No text received.")

    path.write_text(jd, encoding="utf-8")
    print("✅ Saved:", path)

if __name__ == "__main__":
    main()
