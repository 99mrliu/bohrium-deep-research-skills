# 最小调用示例（合成示例，非正式案例）

输入为**手工合成的双栏两页论文词表** `inputs/words.tsv`（生成方式：合成排版行
规格 → 按字号折算词框坐标，坐标为虚构但版式模式真实：页眉页脚、通栏标题/摘要、
双栏正文、跨页续段、题注、参考文献）。`inputs/case.json` 同为合成契约样例。

复现（在任何装有 Python 3 的机器上）：

```bash
python3 ../../scripts/extract_words.py --tsv inputs/words.tsv --out /tmp/ro_work
python3 ../../scripts/order_blocks.py --words /tmp/ro_work/words.tsv --out /tmp/ro_work
python3 ../../scripts/assemble_output.py --blocks /tmp/ro_work/blocks.jsonl \
  --words /tmp/ro_work/words.tsv --case inputs/case.json --out /tmp/ro_out
```

`outputs/` 内是上述命令在技能作者的机器上**真实执行**得到的产物（2026-11-23），
已目检：阅读顺序为 标题→作者→摘要(整宽)→引言(左栏)→方法(右栏)→跨页续接→
结果(右栏)→题注→表格区→参考文献；两处页眉 + 页码被剔除并在 coverage 中记账。
`result.json` 因契约字段 `reading_questions` 无填充来源而如实置空并标 partial。
