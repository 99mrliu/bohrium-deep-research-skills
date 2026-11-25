# 自测日志（selftest log）

> 合成示例，非真实评测案例。以下命令均为真实执行，exit code 为真实返回值。
> 执行环境：macOS arm64，python3（仅标准库），工作目录 `bundle-e-transparent-relevance-ranker/scripts`。
> 执行日期：2026-11-25。

准备（真实执行）：

```bash
mkdir -p examples/run/input/materials examples/run/work examples/run/output
cp examples/example_case.json examples/run/input/case.json
cp examples/materials/records.jsonl examples/run/input/materials/records.jsonl
```

## 1. 正向流水线（逐步真实执行）

| # | 命令 | 关键输出 | exit |
| --- | --- | --- | --- |
| 1 | `python3 parse_case.py --input-dir ../examples/run/input --work ../examples/run/work` | case_id=synthetic-rank-demo-01 记录数=11 合同字段数=12 警告数=0 | 0 |
| 2 | `python3 scaffold_result.py --work ../examples/run/work --output-dir ../examples/run/output` | 骨架已写入 result.json，合同字段数=12 | 0 |
| 3 | `python3 build_facets.py --init --work ../examples/run/work` | 骨架已生成（5 个 facet） | 0 |
| 4 | `python3 build_facets.py --validate ../examples/filled_facets.json --work ../examples/run/work` | 校验通过（5 个 facet） | 0 |
| 5 | `python3 build_facets.py --validate ../examples/filled_facets_bad.json --work ../examples/run/work` | 校验通过（结构合法；含不存在词，留给锚定门拦截） | 0 |
| 6 | `python3 anchor_hits.py --work ../examples/run/work --facets ../examples/run/work/filled_facets.json` | 锚定通过：11 个词，共 97 处命中 | 0 |
| 7 | `python3 score_records.py --work ../examples/run/work` | 最高 SYNB-0831=87.6667，最低 SYNM-9005=0.75 | 0 |
| 8 | `python3 tier_and_ties.py --work ../examples/run/work` | high=7 medium=3 low=1；并列组=2 | 0 |
| 9 | `python3 sensitivity.py --work ../examples/run/work` | 10 个方案；换档记录数=3 | 0 |
| 10 | `python3 fill_result.py --work ../examples/run/work --output-dir ../examples/run/output` | status=partial，null 合同字段=1（included_studies） | 2 |
| 11 | `python3 selfcheck.py --work ../examples/run/work --output-dir ../examples/run/output` | 15 项检查：14 PASS + 1 WARN（included_studies 置 null，已说明） | 2 |

## 2. 锚定失败负例（门禁 exit 3，真实执行）

```bash
mkdir -p ../examples/run/work_neg
cp ../examples/run/work/records.json ../examples/run/work_neg/records.json
python3 anchor_hits.py --work ../examples/run/work_neg --facets ../examples/filled_facets_bad.json
```

真实输出：

```
[anchor_hits] 锚定失败: facet=intervention term='吗啡缓释片'（规范化子串匹配在整个语料中零命中）
[anchor_hits] 门禁未通过：请让模型把上述词替换为语料中真实出现的词后重跑（exit 3）
exit=3
```

失败证据留痕于 `run/work_neg/anchors.json` 的 `anchor_failures` 字段。

## 3. 幂等性验证（真实执行）

在 `/tmp/ranker-rerun/{work,output}` 用同一输入完整重跑步骤 1–10（exit 同正向：
parse 0 / scaffold 0 / init 0 / validate 0 / anchor 0 / score 0 / tier 0 / sens 0 / fill 2），
随后对 9 个产物逐一 `diff`：

```
case_summary.json / records.json / facets_skeleton.json / anchors.json /
scores.json / tiers.json / sensitivity.json / result.json / ranking_rationale.md
```

diff 全部无输出 → 重跑字节一致，幂等成立。

## 4. 手工复算抽查（SYNM-8201）

从 scores.json 取 SYNM-8201 的分解单，按 references/scoring_model.md 手工复算：

- population：命中 2/3 词（CIPN、化疗所致周围神经病变）→ 70×0.30×2/3 = 14.0
- intervention：命中 1/2 词（NRC-9）→ 70×0.30×1/2 = 10.5
- comparator：命中 1/1 词（安慰剂）→ 70×0.10×1 = 7.0
- outcome：命中 1/2 词（感觉症状）→ 70×0.20×1/2 = 7.0
- study_design：命中 1/3 词（随机对照试验）→ 70×0.10×1/3 = 2.3333
- 覆盖小计 = 14.0+10.5+7.0+7.0+2.3333 = **40.8333**
- 时效：year=2024 = reference_year → **10.0**
- 类型：randomized controlled trial → 15×1.0 = **15.0**
- 多样性：期刊键"支持治疗学报"共 4 条 → min(5.0, 2.0×(4−1)) = **5.0**（罚）
- total = 40.8333 + 10.0 + 15.0 − 5.0 = **60.8333**

与 scores.json 中 `total_score = 60.8333` 逐位一致；档位 high（≥60）；
与 SYNM-8202 同分并列（T2），共享第 6 名。selfcheck 的"确定性回放"与
"锚定复验（97 处切片全部逐字符复核）"亦独立确认。
