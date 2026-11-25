# 最小调用示例（合成示例，非正式案例结果）

输入：`examples/source_en.txt`（**合成**材料学摘要，含 `<!-- zone:... -->` 区带标记）。

```bash
S=scripts; W=/tmp/termjob; O=/tmp/termout; IN=/tmp/termin; mkdir -p "$IN" "$W" "$O"
cp examples/source_en.txt examples/case.json "$IN"/
# 1) 源文与候选术语
python3 $S/extract_source.py --input "$IN" --out $W/source.md
python3 $S/term_extract.py --source $W/source.md --out $W/candidates.json
# 2) 决议并锁定
python3 $S/termbase.py init --candidates $W/candidates.json --out $W/termbase.json
python3 $S/termbase.py decide --termbase $W/termbase.json --term "grain boundary" --preferred "晶界" --reason "标准译名"
python3 $S/termbase.py lock --termbase $W/termbase.json
# 3) （合成）译文 + 审计 + 组装
cp examples/translations_bad.json $W/translations.json
python3 $S/consistency_audit.py --termbase $W/termbase.json --translations $W/translations.json \
  --source $W/source.md --out $W/violations.json --report $O/audit_report.md --apply-lock
python3 $S/assemble_result.py --case examples/case.json --translations $W/translations.json \
  --termbase $W/termbase.json --violations $W/violations.json --out $O
```

一键自测（含 8 组断言）：`bash examples/run_example.sh`。

实际案例中，译文由 Agent 对真实源文逐段产出后写入 translations.json；
本示例的译文为作者编写的合成文本，用于演示审计与回填机制，不得当作任何
真实文献的翻译结果。
