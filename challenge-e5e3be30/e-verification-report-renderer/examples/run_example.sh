#!/usr/bin/env bash
# run_example.sh — 端到端演示：pages → skeleton → merge → cards → report → 回写 → validate → gate
# 全部产物写入 examples/out/（可安全删除重跑）。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
S="$ROOT/scripts"
OUT="$HERE/out"
rm -rf "$OUT"
mkdir -p "$OUT"

echo "== 0. paper.txt → pages.jsonl（按换页符 \\f 分页） =="
python3 - "$HERE/paper.txt" "$OUT/pages.jsonl" <<'PY'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
n = 0
with open(dst, "w", encoding="utf-8") as f:
    for i, pg in enumerate(text.split("\f"), 1):
        f.write(json.dumps({"page": i, "text": pg}, ensure_ascii=False) + "\n")
        n += 1
print(f"pages.jsonl: {n} 页")
PY

echo "== 1. contract_assemble skeleton：case.json → result.json 骨架 =="
python3 "$S/contract_assemble.py" skeleton --case "$HERE/case.json" --out "$OUT/result.json"

echo "== 2. merge：写入判定结果（先存后改，status 仍为 partial） =="
python3 - "$HERE" "$OUT" <<'PY'
import json, sys
here, out = sys.argv[1], sys.argv[2]
verdicts = json.load(open(f"{here}/verdicts.json", encoding="utf-8"))
for v in verdicts:
    v.pop("_note", None)
dist = {"supported": 0, "partially_supported": 0,
        "contradicted": 0, "insufficient_evidence": 0}
for v in verdicts:
    dist[v["verdict"]] += 1
new = {
    "verdicts": verdicts,
    "summary": ("3 条论断：C1 支持（甲苯中量子产率 87% 有逐字证据）；"
                "C2 反驳（方法部分明确加热至 120 °C）；"
                "C3 部分支持且文内冲突并列（光学观测无团聚 vs TEM 观测显著团聚）。"),
    "verdict_distribution": dist,
    "sources": [{"type": "paper", "path": "examples/paper.txt",
                 "note": "合成示例论文（虚构）"}],
    "uncertainty": "C3 的光学与电镜观测相互矛盾，未获澄清。",
    "open_questions": ["C3：光学与 TEM 观测矛盾的原因需作者澄清"]
}
json.dump(new, open(f"{out}/new-result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("new-result.json written")
PY
python3 "$S/contract_assemble.py" merge --base "$OUT/result.json" \
    --new "$OUT/new-result.json" --out "$OUT/result.json" --case "$HERE/case.json"

echo "== 3. cards_render：verdicts.json → evidence-cards.md =="
python3 "$S/cards_render.py" --verdicts "$HERE/verdicts.json" \
    --out "$OUT/evidence-cards.md" --title "证据卡片集（DEMO-E-001 合成示例）"

echo "== 4. report_render：报告 Markdown + 真实渲染预览（自动降级链） =="
python3 "$S/report_render.py" --cards "$OUT/evidence-cards.md" \
    --case "$HERE/case.json" --result "$OUT/result.json" --outdir "$OUT"

echo "== 5. 回写产物路径与渲染链，置 status=success，validate =="
python3 - "$OUT" <<'PY'
import json, os, sys
out = sys.argv[1]
info = json.load(open(f"{out}/render-info.json", encoding="utf-8"))
new = {
    "status": "success",
    "evidence_cards_path": os.path.abspath(f"{out}/evidence-cards.md"),
    "report_markdown_path": info["report_markdown_path"],
    "report_preview_path": info["preview_path"],
    "render_chain_used": info["chain"],
}
json.dump(new, open(f"{out}/paths-result.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("paths-result.json written")
PY
python3 "$S/contract_assemble.py" merge --base "$OUT/result.json" \
    --new "$OUT/paths-result.json" --out "$OUT/result.json" --case "$HERE/case.json"

echo "== 5b. 重渲报告（封面反映最终 status=success） =="
python3 "$S/report_render.py" --cards "$OUT/evidence-cards.md" \
    --case "$HERE/case.json" --result "$OUT/result.json" --outdir "$OUT"

python3 "$S/contract_assemble.py" validate --case "$HERE/case.json" --result "$OUT/result.json"

echo "== 6. gate：提交前总闸门 =="
python3 "$S/gate.py" --case "$HERE/case.json" --result "$OUT/result.json" \
    --pages "$OUT/pages.jsonl" --cards "$OUT/evidence-cards.md"

echo "== 产物清单 =="
ls -la "$OUT"
echo "RUN_EXAMPLE: ALL DONE"
