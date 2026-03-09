#!/usr/bin/env bash
set -euo pipefail

INBOX_DIR="data/raw/resumes_inbox"
OUT_DIR="data/raw/resumes_extracted"

mkdir -p "$OUT_DIR"

# Find the first zip in inbox (you can change to a specific name if you want)
ZIP_FILE="$(ls -1 "$INBOX_DIR"/*.zip 2>/dev/null | head -n 1 || true)"

if [[ -z "${ZIP_FILE}" ]]; then
  echo "❌ No .zip found in: $INBOX_DIR"
  echo "Put a zip like resumes.zip into $INBOX_DIR and rerun."
  exit 1
fi

echo "✅ Using ZIP: $ZIP_FILE"
echo "🧹 Cleaning previous extraction folder: $OUT_DIR"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

echo "📦 Extracting with system unzip..."
# -q quiet, -o overwrite, -d destination
unzip -q -o "$ZIP_FILE" -d "$OUT_DIR"

echo "🔎 Summary:"
echo "  Total files extracted: $(find "$OUT_DIR" -type f | wc -l | tr -d ' ')"
echo "  PDFs:  $(find "$OUT_DIR" -type f \( -iname '*.pdf' \) | wc -l | tr -d ' ')"
echo "  DOCX: $(find "$OUT_DIR" -type f \( -iname '*.docx' \) | wc -l | tr -d ' ')"
echo "  TXT:  $(find "$OUT_DIR" -type f \( -iname '*.txt' \) | wc -l | tr -d ' ')"

echo "✅ Done. Extracted resumes are in: $OUT_DIR"

