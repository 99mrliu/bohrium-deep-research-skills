# crossdb-identity-merge

跨库论文身份解析与版本合并 Skill：多源记录全量摄入 → 分块 → 三级决策（自动合并/人工待审/保持分离）→ 干净清单＋合并证据账簿。对应赛题"引文追踪与关联文献发现"的**方向 5（去重与身份合并）**。

## 文件清单

| 文件 | 作用 |
|-|-|
| `SKILL.md` | Skill 本体 |
| `rules/dedup_keys.md` | 规范化、分块键、决策矩阵、版本分类、canonical 选择 |
| `scripts/identity_merge.py` | 主脚本（Python 3.8+，仅标准库） |
| `scripts/verify_merge.py` | 独立自查脚本 |
| `templates/result_fields.md` | result.json 字段契约 |
| `examples/example_walkthrough.md` | 合成数据最小示例（示意） |

## 依赖

Python ≥ 3.8，仅标准库，无网络依赖。输入 `/input/case.json`＋本地记录文件；输出 `/app/output/result.json`（镜像 output_contract）＋ `merge_ledger.json` ＋ `merge_table.md`。

## 使用

```bash
python3 scripts/identity_merge.py --case /input/case.json --out /app/output --workdir /app/work
python3 scripts/verify_merge.py /app/output /app/work
```

## 适用场景与限制

- 适用：多库检索结果去重、预印本/会议/期刊版本对齐、综述清单清洗、合并审计。
- 限制：无硬标识且标题差异大的同文记录会保守地保持分离（宁可漏并）；撤稿/更正只做版本标注与提示，不做主观删除。不做引文追踪与关联打分。

## 维护信息

版本 1.0（challenge-60a8202d 提交版）。决策阈值见 `rules/dedup_keys.md`，`--review-threshold` 可调。
