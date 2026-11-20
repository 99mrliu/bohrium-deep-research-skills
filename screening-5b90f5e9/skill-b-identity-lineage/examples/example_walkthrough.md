# 最小调用示例（全部虚构合成数据）

> **声明**：`example_case.json`、`example_exports/`、`filled_arbitrations.json`、
> `filled_screen_judgments.jsonl` 中的所有文献、作者、DOI、数据均为虚构，
> 仅用于演示流水线，不对应任何真实研究，也不是任何真实案例的答案。

## 数据设计（10 条记录 × 2 个来源 → 7 个 canonical）

| 记录对 | 情形 | 期望处理 |
|---|---|---|
| source_a-001 × source_b-001 | DOI 相同（一个带 `https://doi.org/` 前缀且大小写不同） | Tier1 自动合并 |
| source_a-002 × source_b-002 | 题名细微差异（大小写/冒号 vs 破折号），DOI 缺失/未提供 | Tier2 自动合并 |
| source_a-003 × source_b-003 | arXiv 预印本(2021) × 期刊正式版(2022)，题名一致，跨标识符 | Tier3 → 仲裁 merge，版本谱系 |
| source_a-004 × source_b-004 | 标题高度相似（Jaccard 0.9）、同首作者同年，但人群/DOI/期刊不同 | Tier3 → 仲裁 **split** |
| source_a-005 | DOI 与摘要为空（field_status=missing），孤立记录 | 单独成簇，needs_human |
| source_b-005 | 正常孤立记录 | 单独成簇 |

## 运行步骤

```bash
SKILL=/path/to/skill-b-identity-lineage
SIM=/tmp/sim-skill-b
mkdir -p "$SIM/input" "$SIM/work" "$SIM/output"
cp "$SKILL/examples/example_case.json" "$SIM/input/case.json"
cp -r "$SKILL/examples/example_exports" "$SIM/input/"
echo '# 示例任务：去重后筛选' > "$SIM/input/task.md"

python3 "$SKILL/scripts/parse_case.py"       --input-dir "$SIM/input" --work "$SIM/work"
python3 "$SKILL/scripts/scaffold_result.py"  --work "$SIM/work" --output-dir "$SIM/output"
python3 "$SKILL/scripts/import_records.py"   --work "$SIM/work"      # → 10 条 records
python3 "$SKILL/scripts/identity_resolve.py" --work "$SIM/work"      # → 2 auto_merge + 2 pending

# 真实运行时由模型一次性批量产出 arbitrations.json；此处用合成填充件演示
cp "$SKILL/examples/filled_arbitrations.json" "$SIM/work/arbitrations.json"
python3 "$SKILL/scripts/apply_arbitration.py" --work "$SIM/work"     # 1 merge + 1 split → 7 簇

python3 "$SKILL/scripts/build_canonical.py"  --work "$SIM/work"      # → 7 canonical + 4 条冲突留痕

# 真实运行时由模型一次性批量产出 screen_judgments.jsonl；此处用合成填充件演示
cp "$SKILL/examples/filled_screen_judgments.jsonl" "$SIM/work/screen_judgments.jsonl"
python3 "$SKILL/scripts/screen_canonical.py" --work "$SIM/work"      # 3 include / 3 exclude / 1 needs_human

python3 "$SKILL/scripts/audit_check.py"      --work "$SIM/work"      # 计数闭合
python3 "$SKILL/scripts/fill_result.py"      --work "$SIM/work" --output-dir "$SIM/output"
python3 "$SKILL/scripts/selfcheck.py"        --work "$SIM/work" --output-dir "$SIM/output"  # exit 0
```

## 期望计数（审计恒等式）

- identified = 10 = canonical(7) + merged_copies(3)
- screened = 7 = included(3) + excluded(3) + needs_human(1)
- propagated_records = 3（3 个被合并副本经谱系继承 canonical 结论）

## 失败演练

- 把任意 `evidence_quote` 改成摘要中不存在的句子 → `screen_canonical.py` exit 3，
  写 `anchor_failures.json`，修复后重跑该步即可。
- 把任意仲裁 `rationale` 置空 → `apply_arbitration.py` exit 3。

完整真实自测记录见 `selftest_log.md`。
