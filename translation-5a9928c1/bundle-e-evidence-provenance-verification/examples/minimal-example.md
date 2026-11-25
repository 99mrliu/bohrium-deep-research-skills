# 最小调用示例（合成示例，非正式案例结果）

输入：`examples/source_en.txt`（**合成** ML 摘录，含一处不可读符号）。

```bash
S=scripts; W=/tmp/evjob; O=/tmp/evout; IN=/tmp/evin; mkdir -p "$IN" $W $O
cp examples/source_en.txt examples/case.json "$IN"/
python3 $S/extract_source.py --input "$IN" --out $W/source.md
# 构建带证据的合成译文（quote+offset 由 run_example.sh 内脚本从源文本实际计算）
bash examples/run_example.sh        # 或参照其中 (a) 段构建逻辑
python3 $S/anchor_evidence.py --source $W/source.md --translations $W/translations_clean.json \
  --out $W/evidence_map.json
python3 $S/uncertainty_register.py --translations $W/translations_clean.json \
  --evidence $W/evidence_map.json --out $W/register.json
python3 $S/verification_report.py --translations $W/translations_clean.json \
  --evidence $W/evidence_map.json --register $W/register.json --out $O/verification_report.md
python3 $S/assemble_result.py --case examples/case.json --translations $W/translations_clean.json \
  --evidence $W/evidence_map.json --register $W/register.json --out $O
```

一键自测（12 组断言，含篡改引文、覆盖缺口、诚实 partial）：
`bash examples/run_example.sh`。

示例译文为作者编写的合成中文，仅用于演示证据核验机制；
不得当作任何真实文献的翻译结果。
