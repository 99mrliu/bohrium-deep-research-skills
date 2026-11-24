#!/usr/bin/env bash
# 合成示例（synthetic example），非正式案例结果。
# 本文件是 examples/ 验收时实际执行的命令记录（相对 bundle 根目录）。
# 运行工作区为 examples/_run/，验收后已按规范删除，仅保留输入、
# output-sample/ 留档副本与 VERIFICATION.md。
set -euo pipefail
B="$(cd "$(dirname "$0")/.." && pwd)"          # bundle 根目录
SKILL_DIR="$B"                                  # 平台安装后为 /skills/weekly-skill
IN="$B/examples/input"
W="$B/examples/_run/work"
O="$B/examples/_run/output"
mkdir -p "$W" "$O"

# 可选增强：pdftotext（poppler）加入 PATH；缺失时 matscan 自动降级记 gaps
export PATH="/Users/liuhengshen/Library/Application Support/com.bohrium.runtime/darwin-aarch64/poppler-2560d3705d5614d7/dependencies/poppler/bin:$PATH"

# ---- 主流程（对应 SKILL.md 运行流程）----
# 1. 材料取证
python3 "$SKILL_DIR/scripts/matscan.py" --input "$IN" --work "$W"
# 2. 审计初稿（观察到 matched=2 unmatched=2 conflict=1 材料间冲突=1）
python3 "$SKILL_DIR/scripts/texaudit.py" --draft "$IN/draft.tex" --work "$W"
# 3. Agent 步骤：阅读 coverage.md 与 task.md 后改稿、写 change_log.md，
#    产物放 $O（本仓库的 output-sample/ 留有该阶段产物的副本）
# 4. 对改后稿复检（观察到 matched=3 unmatched=0 conflict=0）
python3 "$SKILL_DIR/scripts/texaudit.py" --draft "$O/draft.tex" --work "$W"
# 5. 装配交付（Agent 已写 source_map.md/change_log.md，finalize 保留；
#    观察到 status=complete，契约 4 字段全部镜像为真实产物路径）
python3 "$SKILL_DIR/scripts/finalize.py" --case "$IN/case.json" --task "$IN/task.md" \
    --work "$W" --output "$O" --input "$IN"

# ---- 降级场景：缺失材料路径 + 自然语言契约 ----
IN2="$B/examples/input-degraded"
W2="$B/examples/_run/work-d"
O2="$B/examples/_run/output-d"
mkdir -p "$W2" "$O2"
python3 "$SKILL_DIR/scripts/matscan.py" --input "$IN2" --work "$W2"
python3 "$SKILL_DIR/scripts/texaudit.py" --draft "$IN2/missing/main.tex" --work "$W2"
python3 "$SKILL_DIR/scripts/finalize.py" --case "$IN2/case.json" --task "$IN2/task.md" \
    --work "$W2" --output "$O2" --input "$IN2"
# 观察到：3 条 gaps 如实记录；status=partial；revised_draft/conflict_memo 给诚实 null

# ---- 附加分支验证 ----
# PDF 提取（pdflatex 现场生成 gen.pdf，pdftotext 抽取，锚点形如 gen.pdf:p1）
# pdftotext 缺失降级（PATH=/usr/bin:/bin 运行，gaps 记"无法提取 PDF 文本"）
# 详见 VERIFICATION.md 第 4、5 节。
