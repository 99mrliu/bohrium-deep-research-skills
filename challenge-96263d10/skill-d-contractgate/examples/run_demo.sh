#!/usr/bin/env bash
# run_demo.sh -- 合成示例端到端演示（合成示例，非正式案件）。
# 在本目录下造 mini_input/ 与 mini_output/，跑 probe -> checkpoint -> seal 正路，
# 再制造一处契约违例跑 seal 反路。用法: bash examples/run_demo.sh
set -u
cd "$(dirname "$0")/.."
W=examples/work
rm -rf "$W"
mkdir -p "$W/mini_input" "$W/mini_output"

# --- 合成输入 ---
cat > "$W/mini_input/task.md" <<'EOF'
把稿件按目标模板改到可交付（合成示例任务说明）。
EOF
cat > "$W/mini_input/稿件.md" <<'EOF'
# 合成稿件
正文一段，含数字 0.85。
EOF
python3 - "$W/mini_input/case.json" <<'PY'
import json, sys
json.dump({"case_id": "demo-synthetic-001",
           "output_contract": {"adapted_file": "适配后文件路径",
                               "summary": "适配摘要"}}, open(sys.argv[1], "w"), ensure_ascii=False, indent=2)
PY

# --- 正路 ---
python3 scripts/probe.py --input "$W/mini_input" --work "$W" --output "$W/mini_output" || true
# 模拟干活：产出交付物并填写契约字段
cat > "$W/mini_output/adapted.md" <<'EOF'
# 合成稿件（已按模板适配，示意）
正文一段，含数字 0.85。
EOF
python3 - "$W/mini_output/result.json" <<'PY'
import json, sys
p = sys.argv[1]
rj = json.load(open(p, encoding="utf-8"))
rj["adapted_file"] = "adapted.md"
rj["summary"] = "合成示例：样式重绑完成，内容零改动。"
rj["changes"] = [{"unit": "styles", "before": "default", "after": "template", "reason": "任务要求"}]
rj["status"] = "partial"   # 还剩人工目检，诚实保持 partial
rj["limits"] = []
json.dump(rj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
python3 scripts/checkpoint.py --work "$W" --output "$W/mini_output" \
    --stage adapt --note "样式重绑完成" --artifact "$W/mini_output/adapted.md"
python3 scripts/seal.py --case "$W/mini_input/case.json" --output "$W/mini_output" --work "$W"
echo "seal-positive-exit=$?"

# --- 反路：清空一个契约字段 + 谎报 complete ---
cp "$W/mini_output/result.json" "$W/result_backup.json"
python3 - "$W/mini_output/result.json" <<'PY'
import json, sys
p = sys.argv[1]
rj = json.load(open(p, encoding="utf-8"))
rj["summary"] = ""
rj["status"] = "complete"
rj["uncertainties"] = ["题注位置未经渲染确认"]
json.dump(rj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
python3 scripts/seal.py --case "$W/mini_input/case.json" --output "$W/mini_output" --work "$W"
echo "seal-negative-exit=$?"
cp "$W/result_backup.json" "$W/mini_output/result.json"
