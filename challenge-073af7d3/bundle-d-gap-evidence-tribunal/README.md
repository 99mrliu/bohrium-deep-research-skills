# bundle-d-gap-evidence-tribunal

Playground challenge-073af7d3 提交件。Skill 名：`gap-evidence-tribunal`。

**重心**：研究空白判定的排除证据纪律 + 冲突证据双侧配对。
"没检索到" ≠ "研究空白"：空白声明必须带可机检的排除证据
（范围 / query_ids / 近失记录及 why_not），冲突必须双侧 record_ids + 数值 + 位置。

## 内容

- `SKILL.md` — 技能说明（中文），完整四交付流水线 + 第2/6/7步的机器校验纪律。
- `scripts/build_corpus.py` — json/jsonl/csv/bib/ris/txt/md → canon.jsonl 归一化。
- `scripts/retrieval_log.py` — 检索/筛查日志校验：闭合 hits == kept + len(excluded)；
  排除理由非空；外部引用标记（非致命）。违规 exit 1。
- `scripts/gap_tribunal.py` — 空白法庭：bare_gap_claim / unknown_query /
  irrelevant_near_miss（Jaccard≥0.08 或共享≥2 词的健全性地板）/ unknown_gap_type 等。
  产出 gap_verdicts.json，有违规 exit 1。
- `scripts/conflict_pairs.py` — 冲突双侧校验：missing_side / unknown_record /
  empty_value / not_a_conflict / missing_location。有违规 exit 1。
- `references/gap_taxonomy.md` — 四类空白定义、采信标准、降级措辞规则。
- `references/evidence_schema.md` — 日志/空白/冲突三类 schema 与全部违规码。
- `examples/` — 全合成案例 + `run_example.sh`；`example_output/` 为真实运行产物。

## 快速验证

```
bash examples/run_example.sh
```

good 路径全部 exit 0；bad 路径三类脚本各 exit 1 且对应违规码全部触发（PROOF 行断言）。

全部脚本仅依赖 Python 3 标准库，确定性输出（键排序、无时钟字段）。
合成数据均已标注 synthetic。
