#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
WORK="$ROOT/examples/work"
INPUT="$WORK/input"
OUT="$ROOT/examples/output"

case "$WORK" in
  "$ROOT"/examples/work) ;;
  *) printf 'Unsafe work path: %s\n' "$WORK" >&2; exit 2 ;;
esac
case "$OUT" in
  "$ROOT"/examples/output) ;;
  *) printf 'Unsafe output path: %s\n' "$OUT" >&2; exit 2 ;;
esac
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { printf 'Python 3 not found: %s\n' "$PYTHON_BIN" >&2; exit 127; }

rm -rf -- "$WORK" "$OUT"
mkdir -p "$INPUT" "$WORK" "$OUT"
cp "$ROOT/examples/mock_case.json" "$INPUT/case.json"
cp "$ROOT/examples/source_note.md" "$INPUT/source_note.md"

"$PYTHON_BIN" "$ROOT/scripts/causal_contrast.py" inspect \
  --case "$INPUT/case.json" \
  --input-dir "$INPUT" \
  --work-dir "$WORK" \
  --output-dir "$OUT"

"$PYTHON_BIN" "$ROOT/scripts/causal_contrast.py" compile \
  --case "$INPUT/case.json" \
  --design-spec "$ROOT/examples/design_spec.json" \
  --input-dir "$INPUT" \
  --output-dir "$OUT"

"$PYTHON_BIN" - "$OUT" <<'PY'
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

out = Path(sys.argv[1])
required = {"inspect.json", "design_spec.template.json", "plan.json", "plan.md", "result.json", "contrast_map.svg", "validation.json"}
missing = sorted(name for name in required if not (out / name).is_file())
if missing:
    raise SystemExit(f"missing runtime artifacts: {missing}")
for name in required:
    text = (out / name).read_text(encoding="utf-8")
    if "合成示例输出，非正式测评结果" not in text:
        raise SystemExit(f"synthetic-output header missing: {name}")
result = json.loads((out / "result.json").read_text(encoding="utf-8"))
validation = json.loads((out / "validation.json").read_text(encoding="utf-8"))
inspection = json.loads((out / "inspect.json").read_text(encoding="utf-8"))
plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
if result["status"] != "complete":
    raise SystemExit(f"expected complete, got {result['status']}: {validation['errors']}")
if validation["errors"]:
    raise SystemExit(f"unexpected scientific FAIL: {validation['errors']}")
if (result["revised_plan"]["total_cost"] != "436" or plan["total_step_minutes"] != "150"
        or plan["time_recompute"]["total_work_minutes"] != "350" or result["revised_plan"]["total_days"] != 4):
    raise SystemExit("cost/time/day recomputation mismatch")
case = json.loads((out.parent / "work" / "input" / "case.json").read_text(encoding="utf-8"))
for field in case["output_contract"]["required_fields"]:
    if field not in result:
        raise SystemExit(f"dynamic required field absent: {field}")
if inspection["candidate_assessment"]["failed_candidate_count"] != 3:
    raise SystemExit("expected three detectable defective candidates")
ids = [c["candidate_id"] for c in inspection["candidate_assessment"]["candidates"]]
if ids != ["CAND_A_PARTIAL", "CAND_B_OPTICAL_GAP", "CAND_C_FULL_OVERDUE"]:
    raise SystemExit(f"canonical version aliases were not preserved: {ids}")
register = inspection["facts"]["resource_register"]
if "EQ_MULTICHANNEL" not in register["resource_ids"]:
    raise SystemExit("note-only equipment absent from resource register")
if not any(origin.startswith("equipment_domain_note@") for origin in register["origins"]["EQ_MULTICHANNEL"]):
    raise SystemExit("note-only equipment origin was not retained")
if not any(r["id"] == "EQ_MULTICHANNEL" for r in plan["resources"]):
    raise SystemExit("compiled design no longer uses note-only equipment")
svg_text = (out / "contrast_map.svg").read_text(encoding="utf-8")
if "<foreignObject" in svg_text:
    raise SystemExit("SVG contains non-portable foreignObject markup")
root = ET.fromstring(svg_text)
controls = root.findall(".//{http://www.w3.org/2000/svg}rect[@class='c']")
if len(controls) != 5:
    raise SystemExit(f"SVG does not contain five control nodes: {len(controls)}")
for control in ["C_VEHICLE", "C_NO_ENZYME", "C_KNOWN_INHIBITOR", "C_COMPOUND_ONLY", "C_DETERGENT"]:
    if control not in (out / "contrast_map.svg").read_text(encoding="utf-8"):
        raise SystemExit(f"SVG control absent: {control}")
print("EXAMPLE_OK status=complete cost=436 single_pass_min=150 total_work_min=350 total_days=4 candidates_FAIL=3 SVG_controls=5 note_resource=EQ_MULTICHANNEL")
PY

# A separate, explicitly NON-synthetic canonical organizer case checks real-case labels,
# version/cost_items aliases, per-line subtotal arithmetic, range steps and note resources.
SMOKE="$WORK/compat_smoke"
mkdir -p "$SMOKE/input"
"$PYTHON_BIN" - "$SMOKE/input/case.json" <<'PY'
import json
from pathlib import Path
import sys
case = {
    "case_id": "canonical-nonsynthetic-smoke",
    "source": {"paper_pdf": None, "citation": None, "key_claim": "Canonical compatibility smoke only."},
    "resource_contract": {
        "disclaimer": "Planning values only.", "currency": "CNY", "budget_cap": 10, "deadline_days": 2,
        "equipment": [{"id": "EQ_MAIN", "name": "Main device", "model": None, "spec": "Declared capability", "price_per_hour": 2,
                       "booking": {"window_days": 2, "slots_per_week": 1, "slot_hours": 1}}],
        "reagents": [{"id": "RS_MAIN", "name": "Declared reagent", "spec": "Declared specification", "unit_price": 1, "unit": "tube", "pack_size": 1}]
    },
    "parameter_domains": {"dose": {"type": "range", "min": 0.1, "max": 1, "step": 0.1, "basis": "Declared test grid", "source": "case"}},
    "equipment_domain_note": "Additional declared equipment: {\"equipment\":[{\"id\":\"EQ_NOTE_ONLY\",\"name\":\"Note device\",\"model\":null,\"spec\":\"Note-only declared capability\",\"price_per_hour\":0,\"booking\":{\"window_days\":2,\"slots_per_week\":1,\"slot_hours\":1}}]}",
    "candidate_plans": [{
        "version": "smoke-v1", "summary": "Intentional arithmetic/domain defects", "parameters": {"dose": 0.15},
        "cost_items": [{"item": "EQ_MAIN", "unit_price": 2, "quantity": 3, "subtotal": 5}],
        "total_cost": 5, "est_days": 1
    }],
    "output_contract": {"required_fields": ["case_id", "revised_plan", "candidate_assessment", "validation", "status", "uncertainty", "sources", "change_log", "confirmation_items"]}
}
Path(sys.argv[1]).write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
"$PYTHON_BIN" "$ROOT/scripts/causal_contrast.py" inspect \
  --case "$SMOKE/input/case.json" --input-dir "$SMOKE/input" --work-dir "$SMOKE/work" --output-dir "$SMOKE/output"
"$PYTHON_BIN" - "$SMOKE/output" <<'PY'
import json
from pathlib import Path
import sys
out = Path(sys.argv[1])
notice = "前瞻性实验方案与机器校验输出；不是实测实验结果"
for name in ("inspect.json", "result.json", "design_spec.template.json"):
    text = (out / name).read_text(encoding="utf-8")
    if "合成示例" in text:
        raise SystemExit(f"non-synthetic smoke output was mislabelled: {name}")
    if json.loads(text)["_header"] != notice:
        raise SystemExit(f"prospective notice mismatch: {name}")
inspection = json.loads((out / "inspect.json").read_text(encoding="utf-8"))
candidate = inspection["candidate_assessment"]["candidates"][0]
assert candidate["candidate_id"] == "smoke-v1", candidate
assert candidate["aliases"]["identifier_field"] == "version", candidate
assert candidate["aliases"]["cost_items_field"] == "cost_items", candidate
assert candidate["status"] == "FAIL", candidate
assert any("cost_items[0].subtotal" in error for error in candidate["errors"]), candidate["errors"]
assert any("total_cost" in error for error in candidate["errors"]), candidate["errors"]
assert any("off step" in error for error in candidate["parameter_domain_violations"]), candidate
register = inspection["facts"]["resource_register"]
assert "EQ_NOTE_ONLY" in register["resource_ids"], register
assert any(origin.startswith("equipment_domain_note@") for origin in register["origins"]["EQ_NOTE_ONLY"]), register
print("COMPAT_SMOKE_OK synthetic_label=false version/cost_items=true subtotal_defect=true range_step_defect=true note_resource=EQ_NOTE_ONLY")
PY

printf 'Generated synthetic demonstration artifacts in %s\n' "$OUT"
printf 'Generated non-synthetic compatibility smoke artifacts in %s\n' "$SMOKE/output"
