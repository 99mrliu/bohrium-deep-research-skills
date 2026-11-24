#!/usr/bin/env bash
# 合成示例（synthetic example）验收脚本，非正式案例结果。
# 用法：bash examples/run.sh
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$HOME/texlive/2026/bin/universal-darwin:$PATH"
export PATH="$HOME/Library/Application Support/com.bohrium.runtime/darwin-aarch64/poppler-2560d3705d5614d7/dependencies/poppler/bin:$PATH"

RUN="$SKILL_DIR/examples/_run"
rm -rf "${RUN:?}"
mkdir -p "$RUN/work/diagnosis" "$RUN/work/diagnosis2" "$RUN/output"

echo "=== [1/5] broken/ 有界多轮编译（缺 ghostmath，预期失败，退出码 1）==="
python3 "$SKILL_DIR/scripts/texbuild.py" \
  --project "$SKILL_DIR/examples/broken" \
  --builddir "$RUN/work/build-broken" \
  --report "$RUN/work/build-broken-report.json"
echo "texbuild(broken) exit=$?"

echo "=== [2/5] broken/ 日志诊断（预期：R1 宏包缺失 + R2 Emergency stop 级联）==="
python3 "$SKILL_DIR/scripts/texlog.py" \
  --log "$RUN/work/build-broken/main.log" \
  --project "$SKILL_DIR/examples/broken" \
  --outdir "$RUN/work/diagnosis" \
  --map "$SKILL_DIR/references/package-map.md"
echo "texlog(broken) exit=$?"

echo "=== [3/5] 模拟 Agent 修掉故障 1 后二次诊断（预期：剩余 3 个根因聚类）==="
# 说明：缺失 .sty 会让 nonstopmode 在 'Enter file name' 处 Emergency stop，
# 其余故障只有修掉故障 1 后才会出现在日志里——这正是本 Skill 的多轮闭环。
cp -R "$SKILL_DIR/examples/broken" "$RUN/work/stage2"
sed -i '' '/\\usepackage{ghostmath}/d' "$RUN/work/stage2/main.tex"
python3 "$SKILL_DIR/scripts/texbuild.py" \
  --project "$RUN/work/stage2" \
  --builddir "$RUN/work/build-stage2" \
  --report "$RUN/work/build-stage2-report.json" >/dev/null
echo "texbuild(stage2) exit=$?"
python3 "$SKILL_DIR/scripts/texlog.py" \
  --log "$RUN/work/build-stage2/main.log" \
  --project "$RUN/work/stage2" \
  --outdir "$RUN/work/diagnosis2" \
  --map "$SKILL_DIR/references/package-map.md"
echo "texlog(stage2) exit=$?"

echo "=== [4/5] fixed/ 修复后重编译验证（预期 complete，退出码 0）==="
python3 "$SKILL_DIR/scripts/texverify.py" \
  --project "$SKILL_DIR/examples/fixed" \
  --case "$SKILL_DIR/examples/case.json" \
  --task "$SKILL_DIR/examples/task.md" \
  --workdir "$RUN/work/verify" \
  --out "$RUN/output" \
  --skill-dir "$SKILL_DIR"
echo "texverify(fixed) exit=$?"

echo "=== [5/5] 降级验证：PATH 置空模拟无 TeX 环境（预期诚实 blocked，退出码 3）==="
env PATH=/usr/bin:/bin python3 "$SKILL_DIR/scripts/texbuild.py" \
  --project "$SKILL_DIR/examples/fixed" \
  --builddir "$RUN/work/build-notool" \
  --report "$RUN/work/build-notool-report.json"
echo "texbuild(no-tex) exit=$?"

echo "=== 产物清单 ==="
find "$RUN" -type f | sort
