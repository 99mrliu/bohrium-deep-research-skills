#!/usr/bin/env bash
# run_example.sh -- end-to-end SYNTHETIC demonstration of the geometry-typeset-deck
# skill. Everything produced here is fictional and marked synthetic.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
SCRIPTS="$SKILL/scripts"

export CASE_INPUT_DIR="$HERE/work/input"
export CASE_WORK_DIR="$HERE/work/work"
export CASE_OUTPUT_DIR="$HERE/work/app-output"
mkdir -p "$CASE_INPUT_DIR" "$CASE_WORK_DIR" "$CASE_OUTPUT_DIR"

echo "=== 1/8 make_fixture (synthetic template + case + dense plan) ==="
python3 "$HERE/make_fixture.py"

echo "=== 2/8 result_make: secure EARLY partial result.json ==="
python3 "$SCRIPTS/result_make.py" --status partial \
    --set-json synthetic_example=true \
    --exception "pipeline started; final artifacts pending"

echo "=== 3/8 template_probe ==="
python3 "$SCRIPTS/template_probe.py" --template "$CASE_INPUT_DIR/target-template.pptx" \
    --work "$CASE_WORK_DIR"
python3 - "$CASE_WORK_DIR/theme.json" <<'PY'
import json, sys
t = json.load(open(sys.argv[1]))
assert t["source"] == "template", "theme.json source must be 'template'"
assert t["fonts"]["title"] == "Georgia", t["fonts"]
assert t["fonts"]["body"] == "Helvetica", t["fonts"]
assert t["colors"]["accent1"] == "1F4E79", t["colors"]
print("ASSERT OK: theme probed from fixture template (Georgia/Helvetica/#1F4E79)")
PY

echo "=== 4/8 textfit (deterministic layout; overflow policies must fire) ==="
python3 "$SCRIPTS/textfit.py" --plan "$CASE_WORK_DIR/plan.json" \
    --theme "$CASE_WORK_DIR/theme.json" --out "$CASE_WORK_DIR/layout.json"
python3 - "$CASE_WORK_DIR/layout.json" <<'PY'
import json, sys
lay = json.load(open(sys.argv[1]))
cont = [s for s in lay["slides"] if "(cont.)" in s["title"]]
backup = [s for s in lay["slides"] if s["role"] == "backup"]
assert cont, "expected at least one '(cont.)' continuation slide"
assert backup, "expected at least one backup slide (policy c)"
assert lay["actions"], "actions log must not be empty"
sizes = [s["body_box"]["size_pt"] for s in lay["slides"] if s.get("body_box")]
assert min(sizes) >= 14.0, "body font must never go below 14pt"
print("ASSERT OK: %d slides total, %d continuation, %d backup, %d actions, min body %.0fpt"
      % (len(lay["slides"]), len(cont), len(backup), len(lay["actions"]), min(sizes)))
PY

echo "=== 5/8 deck_forge (with theme cloning from fixture template) ==="
python3 "$SCRIPTS/deck_forge.py" --layout "$CASE_WORK_DIR/layout.json" \
    --theme "$CASE_WORK_DIR/theme.json" \
    --template "$CASE_INPUT_DIR/target-template.pptx" \
    --images "$CASE_WORK_DIR" \
    --out "$CASE_OUTPUT_DIR/presentation.pptx"
python3 - "$CASE_OUTPUT_DIR/presentation.pptx" "$CASE_INPUT_DIR/target-template.pptx" <<'PY'
import sys, zipfile
out, tpl = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out) as z:
    names = z.namelist()  # valid zip proves readability
    assert "ppt/theme/theme1.xml" in names
    theme_out = z.read("ppt/theme/theme1.xml")
with zipfile.ZipFile(tpl) as z:
    theme_tpl = z.read("ppt/theme/theme1.xml")
assert theme_out == theme_tpl, "theme1.xml bytes must be cloned verbatim"
assert b"Georgia" in theme_out and b"1F4E79" in theme_out
print("ASSERT OK: pptx valid zip (%d parts); theme1.xml byte-identical to fixture template"
      % len(names))
PY

echo "=== 6/8 preview_render (SVG always; PNG via matplotlib) ==="
python3 "$SCRIPTS/preview_render.py" --layout "$CASE_WORK_DIR/layout.json" \
    --theme "$CASE_WORK_DIR/theme.json" --out "$CASE_OUTPUT_DIR/preview"
python3 - "$CASE_OUTPUT_DIR/preview" <<'PY'
import glob, os, sys
svgs = sorted(glob.glob(os.path.join(sys.argv[1], "slide-*.svg")))
pngs = sorted(glob.glob(os.path.join(sys.argv[1], "slide-*.png")))
assert svgs, "SVG previews missing"
if pngs:  # matplotlib present on this machine
    small = [p for p in pngs if os.path.getsize(p) <= 10 * 1024]
    assert not small, "PNG previews must be >10KB: %s" % small
print("ASSERT OK: %d SVG previews, %d PNG previews (all >10KB)"
      % (len(svgs), len(pngs)))
PY

echo "=== 7/8 export_audit (soffice absent here -> honest RENDERER_MISSING) ==="
python3 "$SCRIPTS/export_audit.py" --pptx "$CASE_OUTPUT_DIR/presentation.pptx" \
    --layout "$CASE_WORK_DIR/layout.json" --out "$CASE_OUTPUT_DIR"
python3 - "$CASE_OUTPUT_DIR/render_audit.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))
assert a["verdict"] in ("RENDERER_MISSING", "PASS"), a["verdict"]
print("ASSERT OK: render_audit verdict=%s (words_checked=%d)"
      % (a["verdict"], a["words_checked"]))
PY

echo "=== 8/8 result_make: final result.json ==="
python3 "$SCRIPTS/result_make.py" --status success \
    --set-json synthetic_example=true \
    --set-json editable_source="\"$CASE_OUTPUT_DIR/presentation.pptx\"" \
    --exception "synthetic example; no real paper or template used" \
    --exception "soffice not installed on this machine; export render audit is RENDERER_MISSING, SVG/PNG previews are the inspection artifact" \
    --exception "slide-master artwork (bitmaps/backgrounds) is not cloned, only theme1.xml bytes"
python3 - "$CASE_OUTPUT_DIR/result.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r["case_id"] == "synthetic-demo-002", r["case_id"]
for f in ("status", "editable_source", "export_artifact",
          "content_map", "compliance_checks", "exceptions"):
    assert f in r, "missing contract field %s" % f
assert r["status"] == "success"
assert r.get("synthetic_example") is True
print("ASSERT OK: result.json case_id=%s, 6 contract fields, synthetic_example=true"
      % r["case_id"])
PY

echo
echo "=== final artifacts ==="
find "$HERE/work" -type f | sort | while read -r f; do
    printf '%9d  %s\n' "$(stat -f%z "$f")" "${f#"$HERE"/}"
done
echo "run_example: ALL OK"
