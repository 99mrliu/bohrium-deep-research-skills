# 最小调用示例（SYNTHETIC —— 非平台正式案例，示意输出不代表真实案例结果）

本示例演示一次完整调用流程。全部材料为合成（SYNTHETIC），仅供说明接口。

## 输入（示意）

```
examples/synthetic-case/input/
  case.json            # case_id + output_contract（9 个键）；根元数据只属于第一篇
  task.md              # 任务说明
  corpus-manifest.json # 两篇合成论文的 DOI/作者/许可/sha256
  material.json        # 汇总索引（primary / secondary）
  primary-material.json    # SYN-P1 正文段落（JATS paragraph_id + text）
  secondary-material.json  # SYN-P2 正文段落
```

## 调用方式（一条命令跑完流水线与自检）

```bash
cd <bundle根目录>
python3 scripts/run_selftest.py --bundle .
```

等价的分步调用（正式案例在 /input、/app/work、/app/output 上执行）：

```bash
python3 scripts/case_bootstrap.py --input /input --out /app/output
# Agent 阅读材料，手写 nodes.json / relations.json / merge_decisions.json / queries_spec.json
python3 scripts/relation_validate.py --relations relations.json --input /input \
    --nodes nodes.json --out /app/output/relation_audit.json
python3 scripts/condition_lint.py --relations relations.json \
    --out /app/work/relations_linted.json --findings /app/output/lint_findings.json
python3 scripts/conflict_detect.py --relations /app/work/relations_linted.json \
    --out /app/output/conflicts.json
python3 scripts/graph_build.py --nodes nodes.json \
    --relations /app/work/relations_linted.json --merges merge_decisions.json \
    --outdir /app/output
python3 scripts/query_run.py --graph /app/output/graph.jsonl \
    --queries queries_spec.json --out /app/output/queries.json
python3 scripts/graph_preview.py --graph /app/output/graph.json --outdir /app/output
python3 scripts/assemble.py --case /input/case.json --outdir /app/output
```

## 示意输出（SYNTHETIC 标签，摘自 examples/synthetic-case/output/）

- `graph.json` / `graph.jsonl`：**9 节点 / 9 边**，每个节点与边含
  source_id + JATS paragraph_id + 逐字短引；
- `conflicts.json`：1 条 K1 数值冲突（TransB 在 LowMT-100/BLEU/low-resource
  下 29.8 vs 30.5，两条边都保留并标 `in_conflict=true`）；
- `merge_report.json`：合并 LowMT-100 ↔ LowMT100（显式依据）；
  不合并 TransB ≠ TransB-ft（同名不同对象）；
- `queries.json`：**4 个真实执行的查询**，其中 q3 诚实回答
  `no_direct_relation`（TransA 与 DistilT 仅共现，不建边）；
- `graph.svg` / `graph.dot` / `graph_preview.md`：可读预览
  （冲突边红色、cited-background 边虚线）；
- `result.json`：`case_id` + output_contract 全部 9 键动态镜像 +
  status/sources/uncertainty/changes；
- `selftest_report.json`：18/18 通过（8 个流水线步骤 + 6 项正向断言 +
  4 项负例测试：引文不匹配拒收、无指标全局比较降级、
  cited-background 当一手证据被拒、冲突必须标记）。
