# 最小调用示例（说明接口与完整流程；以下输出为 SYNTHETIC 合成示例，非正式案例结果）

## 输入

`/input/` 目录（正式案例由平台提供；本仓库用 `examples/synthetic/input/` 演示）：

```
case.json  task.md  corpus-manifest.json  material.json
primary-material.json  secondary-material.json
```

## 调用

```bash
# 0) 先落诚实 partial（产物缺失时 status=partial，随步骤推进自动升级）
python3 scripts/kg_assemble.py --input-dir /input --work-dir /app/work \
    --output-dir /app/output

# 1) Agent 阅读 primary 并写出 /app/work/baseline-candidates.json 后：
python3 scripts/kg_verify.py --input-dir /input \
    --candidates /app/work/baseline-candidates.json
python3 scripts/kg_apply.py init --input-dir /input \
    --candidates /app/work/baseline-candidates.json --work-dir /app/work

# 2) Agent 阅读 secondary、对照 graph-v1.json 稳定 ID 写出 changeset.json 后：
python3 scripts/kg_verify.py --input-dir /input --changeset /app/work/changeset.json \
    --graph /app/work/graph-v1.json
python3 scripts/kg_apply.py apply --input-dir /input --work-dir /app/work \
    --changeset /app/work/changeset.json

# 3) 版本差异 + 真实执行查询清单（>=3，覆盖 baseline 与 current）
python3 scripts/kg_diff.py --baseline /app/work/graph-v1.json \
    --current /app/work/graph-v2.json --out /app/work/diff.json
python3 scripts/kg_query.py --baseline /app/work/graph-v1.json \
    --current /app/work/graph-v2.json --spec /app/work/query-specs.json \
    --out /app/work/queries.json

# 4) 装配交付
python3 scripts/kg_assemble.py --input-dir /input --work-dir /app/work \
    --output-dir /app/output
```

## 示意输出（截取自 SYNTHETIC 合成示例，仅演示字段形状）

`/app/output/result.json`：

```json
{
  "case_id": "SYNTH-INCREMENTAL-001",
  "status": "success",
  "skill": "05-incremental-change-kg",
  "versions": {"baseline": "graph-baseline.json", "current": "graph-current.json"},
  "summary": "增量文献知识图谱：baseline v1（primary 封存）已建；当前版本 v2。节点 9、边 9；…",
  "uncertainty": ["存在 1 组未裁决冲突边…"],
  "graph": {"baseline": "graph-baseline.json", "current": "graph-current.json", "…": "…"},
  "queries": {"file": "queries.json", "executed": 5},
  "changes": {"file": "changes.json", "summary": {"MERGE": 1, "ADD": 5, "…": "…"}}
}
```

`change-ledger.md` 节选：

```
## seq 1 · MERGE → n_mat_29a6b6b9
- 依据/理由: p2.001 显式给出全称与缩写的同一指称：'an LFP/C composite (LiFePO4/C, …)'…
- 被吸收别名: LFP/C（幸存者保留原 ID，别名与证据追加，不删除记录）
- 证据 [secondary/p2.001]: "an LFP/C composite (LiFePO4/C, hereafter LFP/C)"
```

完整可运行示例见 `examples/synthetic/`（`run_synthetic.sh` 一键复现，
`tests/negative_tests.sh` 负向测试）。
