# 最小调用示例（合成示例，非正式案例结果）

输入：`examples/source_paged.txt`（**合成**两栏摘录，含 `\f` 分页、跨栏断词、
段内单换行、Figure 题注与公式行）。

```bash
S=scripts; W=/tmp/alignjob; O=/tmp/alignout; IN=/tmp/alignin; mkdir -p "$IN" $W $O
cp examples/source_paged.txt examples/case.json "$IN"/
python3 $S/segment_docs.py run --input "$IN" --out $W/segments.json
python3 $S/coverage.py init --segments $W/segments.json --out $W/ledger.json
python3 $S/coverage.py apply --ledger $W/ledger.json --translations examples/translations_full.json
python3 $S/coverage.py report --ledger $W/ledger.json --out $W/coverage_report.json
python3 $S/align_export.py --case examples/case.json --ledger $W/ledger.json \
  --translations examples/translations_full.json --out $O
```

一键自测（13 组断言，含拒绝与缺段测试）：`bash examples/run_example.sh`。

示例译文为作者编写的合成中文，仅用于演示台账与对齐机制；
不得当作任何真实文献的翻译结果。
