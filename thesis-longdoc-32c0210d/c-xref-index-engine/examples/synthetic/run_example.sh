#!/bin/bash
# run_example.sh — xref-index-engine 合成示例一键端到端演示。
# 在 macOS /bin/bash + 系统 python3 下运行；模拟 /input、/app/work、/app/output 三段式。
# 流程：build_index -> check（捕获预埋问题，退出码 1 为预期）-> 按工单修复 ->
#       重建索引 -> impact 级联定位 -> 复检 PASS -> make_result。
# 输出确定性：报告内只含相对文件名与行号，无绝对路径、无时间戳。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPTS="$HERE/../../scripts"
SIM="$HERE/runtime"
NOTE="SYNTHETIC EXAMPLE — 合成示例，非正式案例结果"

rm -rf "$SIM"
mkdir -p "$SIM/input" "$SIM/work" "$SIM/output"
cp "$HERE/input/case.json" "$HERE/input/organizer-edit-workorder.json" "$SIM/input/"
cp -R "$HERE/input/chapters" "$SIM/work/chapters"

echo "== [1/6] build_index：构建跨章节注册表 =="
python3 "$SCRIPTS/build_index.py" --chapters "$SIM/work/chapters" \
    --terms "UV固化胶|紫外固化胶" --note "$NOTE" \
    --out "$SIM/work/index_before_fix.json"

echo
echo "== [2/6] 首检：预期捕获预埋问题（退出码 1 为预期） =="
FIRST=0
python3 "$SCRIPTS/check_consistency.py" --index "$SIM/work/index_before_fix.json" \
    --out "$SIM/work/consistency_report_before_fix.json" || FIRST=$?
echo "首检退出码: $FIRST（非零为预期，存在 error 级问题）"

echo
echo "== [3/6] 按工单修复（修 dangling 引用 + 术语统一 + 重复题注编号），并记录 changes.json =="
CH="$SIM/work/chapters" WORK="$SIM/work" python3 - <<'PYEOF'
import json, os, re

ch, work = os.environ["CH"], os.environ["WORK"]
def load(name):
    with open(os.path.join(ch, name), encoding="utf-8") as fh:
        return fh.read()
def save(name, text):
    with open(os.path.join(ch, name), "w", encoding="utf-8") as fh:
        fh.write(text)

changes = []

# 工单 1：chapter3 的“图 2-3”悬空引用 -> 图 2-2（chapter2 的工艺窗口图）
c3 = load("chapter3.md")
assert c3.count("图 2-3") == 1, "expected exactly one dangling ref"
save("chapter3.md", c3.replace("图 2-3", "图 2-2"))
changes.append({"workorder_id": 1, "file": "chapter3.md", "before": "图 2-3",
                "after": "图 2-2", "reason": "dangling-float-reference：图 2-3 无对应题注"})

# 连带修复（首检 error）：chapter2 第二个“图 2-1”题注实为图 2-2
lines = load("chapter2.md").splitlines()
seen = 0
for idx, l in enumerate(lines):
    if l.startswith("图 2-1"):
        seen += 1
        if seen == 2:
            lines[idx] = l.replace("图 2-1", "图 2-2", 1)
assert seen == 2, "expected duplicate 图 2-1 captions"
save("chapter2.md", "\n".join(lines) + "\n")
changes.append({"workorder_id": None, "file": "chapter2.md", "before": "图 2-1（第二处题注）",
                "after": "图 2-2", "reason": "duplicate-float-number：首检捕获的重复题注编号"})

# 工单 2：术语统一“紫外固化胶”->“UV固化胶”，跳过参考文献条目行（[n] 开头）
total = 0
for name in ("chapter1.md", "chapter2.md", "chapter3.md"):
    out = []
    for l in load(name).splitlines():
        if not re.match(r"^\s*\[\d+\]", l):
            total += l.count("紫外固化胶")
            l = l.replace("紫外固化胶", "UV固化胶")
        out.append(l)
    save(name, "\n".join(out) + "\n")
assert total == 2, "expected 2 body occurrences, got %d" % total
changes.append({"workorder_id": 2, "file": "chapter2.md, chapter3.md",
                "before": "紫外固化胶", "after": "UV固化胶",
                "reason": "术语统一（参考文献条目标题保持原文）"})

with open(os.path.join(work, "changes.json"), "w", encoding="utf-8") as fh:
    json.dump(changes, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print("fixes applied, changes.json written (%d records)" % len(changes))
PYEOF

echo
echo "== [4/6] 重建索引 + impact 级联定位（锚点 figure:2-2）=="
python3 "$SCRIPTS/build_index.py" --chapters "$SIM/work/chapters" \
    --terms "UV固化胶|紫外固化胶" --note "$NOTE" \
    --out "$SIM/work/index.json"
python3 "$SCRIPTS/impact.py" --index "$SIM/work/index.json" \
    --anchor figure:2-2 --out "$SIM/work/impact_report.json"

echo
echo "== [5/6] 复检：预期 PASS（退出码 0）=="
python3 "$SCRIPTS/check_consistency.py" --index "$SIM/work/index.json" \
    --out "$SIM/work/consistency_report.json"
echo "复检退出码: 0（无 error）"

echo
echo "== [6/6] 交付：复制产物到 output 并生成 result.json =="
mkdir -p "$SIM/output/edited_chapters"
cp "$SIM/work/chapters/"*.md "$SIM/output/edited_chapters/"
cp "$SIM/work/consistency_report.json" "$SIM/work/consistency_report_before_fix.json" \
   "$SIM/work/impact_report.json" "$SIM/output/"
python3 "$SCRIPTS/make_result.py" --case "$SIM/input/case.json" \
    --out "$SIM/output/result.json" --status success \
    --report "$SIM/work/consistency_report.json" \
    --impact "$SIM/work/impact_report.json" \
    --changes "$SIM/work/changes.json" \
    --chapters "$SIM/output/edited_chapters" \
    --source "input/chapters/chapter1.md" --source "input/chapters/chapter2.md" \
    --source "input/chapters/chapter3.md" --source "input/organizer-edit-workorder.json" \
    --uncertainty "EVA 跨章重复定义（warn）未处理：不在工单范围内，保留以待作者决定" \
    --note "$NOTE"

echo
echo "DONE. 产物位于: $SIM/output"

echo
echo "== 与 expected/ 冻结产物对比 =="
FAIL=0
count=0
for f in "$HERE/expected/"*.json; do
  count=$((count+1))
  n=$(basename "$f")
  for cand in "$SIM/output/$n" "$SIM/work/$n"; do
    if [ -f "$cand" ]; then
      if diff -q "$f" "$cand" >/dev/null 2>&1; then echo "  MATCH  $n"; else echo "  DIFF   $n"; FAIL=1; fi
      break
    fi
  done
done
if [ "$count" -eq 0 ]; then echo "EXAMPLE FAIL: expected/ 为空"; exit 1; fi
if [ "$FAIL" -eq 0 ]; then echo "EXAMPLE PASS: $count 个产物与 expected/ 逐字节一致"; else echo "EXAMPLE FAIL"; exit 1; fi
