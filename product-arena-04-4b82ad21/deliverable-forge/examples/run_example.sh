#!/usr/bin/env bash
# End-to-end SYNTHETIC EXAMPLE for deliverable-forge.
# Renders the synthetic draft into real deliverables under
# examples/sample-output/. Binary artifacts (docx/pdf) are verified and then
# removed, because skill bundles ship text only; re-run to regenerate them.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$HERE/.." && pwd)"
CASE="$HERE/synthetic-case/case.json"
V1="$HERE/synthetic-case/filled/introduction.md"
V2="$HERE/synthetic-case/filled/introduction.v2.md"
OUT="$HERE/sample-output"

rm -rf "$OUT"
mkdir -p "$OUT/work"
cp "$V2" "$OUT/introduction.md"

echo "== Step 1: word budget =="
python3 "$SKILL_DIR/scripts/word_budget.py" --case "$CASE" \
  --draft "$OUT/introduction.md" --out "$OUT/work/word_report.json"

echo "== Step 2: real editable docx =="
python3 "$SKILL_DIR/scripts/md2docx.py" --md "$OUT/introduction.md" \
  --out "$OUT/introduction.docx" --title "Introduction (synthetic example)" --verify

echo "== Step 3: inspectable preview =="
python3 "$SKILL_DIR/scripts/make_preview.py" --md "$OUT/introduction.md" \
  --out-dir "$OUT" --title "Introduction (synthetic example)" || true

echo "== Step 4: change record v1 -> v2 =="
python3 "$SKILL_DIR/scripts/change_record.py" --old "$V1" --new "$V2" \
  --out "$OUT/work/changes.json" \
  --rationale "gap sentence now states the tested remedy; heading renamed to reflect joint gap+present-work move" || true

echo "== evidence of the docx internals (text only) =="
python3 - "$OUT" <<'PY'
import sys, zipfile, re
out = sys.argv[1]
z = zipfile.ZipFile(out + "/introduction.docx")
doc = z.read("word/document.xml").decode("utf-8")
with open(out + "/work/docx_inspection.txt", "w", encoding="utf-8") as fh:
    fh.write("members: %s\n" % z.namelist())
    fh.write("document.xml bytes: %d\n" % len(doc))
    fh.write("text runs: %d\n" % len(re.findall(r"<w:t[ >]", doc)))
    fh.write("contains 'PermaLig': %s\n" % ("PermaLig" in doc))
    fh.write("contains citation marker '[2]': %s\n" % ("[2]" in doc))
print("docx inspected")
PY

# Ship text only: binaries are regenerable by re-running this script.
rm -f "$OUT/introduction.docx" "$OUT/preview.pdf"
echo
echo "Done. Text artifacts kept under $OUT (docx/pdf removed after verification;"
echo "re-run to regenerate). SYNTHETIC EXAMPLE, invented material only."
