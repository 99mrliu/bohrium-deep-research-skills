# 最小调用示例（合成示例，非正式案例结果）

输入：`examples/source_en.txt`（**合成**临床摘要，含统计量、引用、图表编号、否定与限定）。

```bash
S=scripts; W=/tmp/fidjob; O=/tmp/fidout; IN=/tmp/fidin; mkdir -p "$IN" $W $O
cp examples/source_en.txt examples/case.json "$IN"/
python3 $S/extract_invariants.py --text "$IN/source_en.txt" --out $W/invariants_src.json
python3 $S/audit_invariants.py --translations examples/translations_good.json \
  --source examples/source_en.txt --out $W/audit.json --review $O/human_review.md
python3 $S/assemble_result.py --case examples/case.json \
  --translations examples/translations_good.json --audit $W/audit.json --out $O
```

把 `translations_good.json` 换成 `translations_bad.json` 可复现检出
（p 值与 HR 改写、引用丢失、凭空增数、否定丢失、限定升格）。

一键自测（10 组断言）：`bash examples/run_example.sh`。

示例译文为作者编写的合成文本，仅用于演示核验机制；
不得当作任何真实文献的翻译结果。
