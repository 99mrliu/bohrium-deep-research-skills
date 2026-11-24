#!/usr/bin/env bash
# run_example.sh — 端到端演示：severity_gate → fp_screen → adjudicate
# 输入：examples/findings_draft.json（合成示意案例的未校准草稿）
# 输出：examples/output/ 下全部结果（合成示例输出，非正式测评结果）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="${HERE}/../scripts"
OUT="${HERE}/output"
mkdir -p "${OUT}"

echo "== 1/3 severity_gate：严重度规则引擎 =="
python3 "${SCRIPTS}/severity_gate.py" \
  --input "${HERE}/findings_draft.json" \
  --output "${OUT}/gated_findings.json" \
  --log "${OUT}/severity_downgrade_log.json"

echo "== 2/3 fp_screen：误报鉴别筛 =="
python3 "${SCRIPTS}/fp_screen.py" \
  --input "${OUT}/gated_findings.json" \
  --output "${OUT}/screened_findings.json" \
  --log "${OUT}/fp_screen_log.json"

echo "== 3/3 adjudicate：对抗式复核与终审 =="
python3 "${SCRIPTS}/adjudicate.py" \
  --input "${OUT}/screened_findings.json" \
  --output "${OUT}/adjudication.json"

echo "== 汇总：最终 findings 与校准日志 =="
python3 - "${OUT}" <<'PYEOF'
import json, sys, os

out = sys.argv[1]
HEADER = "合成示例输出，非正式测评结果"

def load(name):
    with open(os.path.join(out, name), encoding="utf-8") as fh:
        return json.load(fh)

adj = load("adjudication.json")
gate = load("gated_findings.json")
screen = load("screened_findings.json")

# 最终 findings（终审裁定后），头部注明合成示例
final = {
    "note": HEADER + "：severity_gate → fp_screen → adjudicate 三道闸门后的最终 findings",
    "case_id": "mock-calibration-001",
    "findings": adj.get("findings", []),
    "summary": adj.get("summary", {}),
}
with open(os.path.join(out, "final_findings.json"), "w", encoding="utf-8") as fh:
    json.dump(final, fh, ensure_ascii=False, indent=2)

# 给三个中间产物头部补注合成示例说明
for name in ("gated_findings.json", "screened_findings.json", "adjudication.json"):
    data = load(name)
    data["note"] = HEADER + "：" + str(data.get("note", ""))
    with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

# 人读校准日志：逐条 finding 的处置链路
gate_log = {a["finding_id"]: [] for a in gate.get("audit_trail", [])}
for a in gate.get("audit_trail", []):
    gate_log.setdefault(a["finding_id"], []).append("%s(%s)" % (a["rule"], a["action"]))
fp_log = {e["finding_id"]: e for e in screen.get("fp_log", [])}
cards = {c["finding_id"]: c for c in adj.get("adjudication_cards", [])}

lines = [
    "# 校准日志（%s）" % HEADER,
    "",
    "管道：severity_gate（R1–R8）→ fp_screen（FP-01…FP-10）→ adjudicate（A1–A5）",
    "",
    "| finding | type | 草稿严重度 | 闸门后 | 闸门触发规则 | 误报鉴别 | 终审裁定 | 最终严重度 | 最终状态 |",
    "|---|---|---|---|---|---|---|---|---|",
]
for f in adj.get("findings", []):
    fid = f.get("id", "?")
    fp = fp_log.get(fid, {})
    card = cards.get(fid, {})
    lines.append(
        "| %s | %s | %s | %s | %s | %s(%s) | %s | %s | %s |"
        % (
            fid,
            f.get("type", "?"),
            f.get("claimed_severity", "?"),
            card.get("severity_before", f.get("severity", "?")),
            ", ".join(gate_log.get(fid, ["-"])),
            fp.get("fp_decision", "-"),
            fp.get("fp_rule", "-"),
            card.get("ruling", "（fp_screen 已排除）"),
            f.get("severity", "?"),
            f.get("verdict_status", "?"),
        )
    )
lines += [
    "",
    "## 终审汇总",
    "",
    "```json",
    json.dumps(adj.get("summary", {}), ensure_ascii=False, indent=2),
    "```",
]
with open(os.path.join(out, "calibration_log.md"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")

print("已写出 final_findings.json 与 calibration_log.md")
PYEOF

echo "完成。输出目录：${OUT}"
ls -la "${OUT}"
