---
name: a-onepass-kg-runner
description: >-
  单命令文献知识图谱流水线（运行工程与预算效率方向）。一个驱动脚本
  scripts/kg_run.py 提供 discover/apply/verify/build/query/assemble/all
  子命令：模型只需写出唯一一个追加式 JSONL 抽取文件（/app/work/extractions.jsonl，
  ops: node/edge/merge/nonmerge/unreported/note），其余全部由 Python3 标准库脚本
  确定性完成——宽容输入发现、引文逐字符子串校验、断点 checkpoint、自动执行
  case.json 查询、合同镜像装配、DOT/SVG 预览与 run_report.json 预算报告。
  为阅读15等文献知识图谱构建赛题在 64 请求/900 秒预算内以最少模型请求完成
  端到端交付而设计。
---

# a-onepass-kg-runner（单命令 KG 流水线 · 运行工程与预算效率）

## 1. 用途与适用条件

- **适用**：输入为 `/input/` 下两篇 JATS-like 文献语料（primary/secondary）+
  `case.json`（含 `output_contract` 与 `query_specs`）的文献知识图谱构建任务。
- **重心**：把模型请求压到最少（目标 ≤3 次），把发现、校验、建图、查询、
  装配、渲染全部交给一个确定性驱动脚本；模型只写**一个** JSONL 文件。
- **不适用**：需要复杂语义推理/本体推理的场景（本 bundle 以可机械校验的
  证据纪律换取吞吐量）。

## 2. 官方运行时契约

- 技能安装于 `/skills/weekly-skill`；输入 `/input/`，工作目录 `/app/work`，
  交付目录 `/app/output`。
- `/app/output/result.json` 必须含 `case_id` 与 `output_contract` 声明的
  **全部键**（动态镜像；产不出的键置 `null` 并在 `contract_notes` 记录原因，
  绝不省略），并含诚实的 `status`（success/partial/unable + reason）、
  `sources`、`uncertainty`、`merge_ledger`、`nonmerge_registry`。
- 证据规则（非协商）：每个实质性 node/edge/merge/nonmerge/unreported 携带
  `source_id` + JATS `paragraph_id` + **逐字符精确子串** quote；脚本机械校验，
  失败即进 quarantine。语料无 PDF 页码，禁止编造页码。来源冲突原样保留
  （`resolution=preserved`），未报告项进 `unreported`。

## 3. 角色分工（模型 vs 脚本）

| 环节 | 执行者 | 说明 |
| --- | --- | --- |
| 读入语料 + 一次性写出抽取 | **模型** | 唯一产物 `/app/work/extractions.jsonl`（逐行 JSON，schema 见 `references/extractions-jsonl-schema.md`）；可按需**追加**修补 |
| 输入发现/归一化 | 脚本 `discover` | 容忍 list / `{"materials":[...]}` / 映射三种 material.json 形态；缺段落 id 自动编址；重复 id 记为歧义地址；manifest 交叉核对；`secondary-publisher.xml` 只登记不解析；根元数据只归 primary |
| JSONL 宽容解析 | 脚本 `apply` | 坏行/未知 op 跳过并逐行告警，不中断 |
| 证据机械校验 | 脚本 `verify` | 引文精确子串 + 地址存在且唯一 + merge 需 normalized_key+reason + nonmerge ≥2 subjects+reason；失败进 quarantine |
| 建图 + DOT/SVG | 脚本 `build` | 确定性排序；merge 吸收（边自动重定向、ledger 记账）；nonmerge 登记；contradicts 保留为冲突档案 |
| 查询 | 脚本 `query` | 自动执行 case.json 的 query_specs（neighborhood/by-relation/path/conflict-check），结果子图带证据与 undetermined |
| 装配 + 预算报告 | 脚本 `assemble` | 合同镜像 result.json；`run_report.json`（签名产物：逐阶段耗时在 run_meta 下、行接收统计、预算清单） |

**红线**：模型不得伪造引文/页码/分数；不得把不同条件/样本/数值并入同一结论；
同名 ≠ 同一物理对象必须显式 nonmerge；冲突不消解。

## 4. 复制粘贴命令序列（6 条，按 64 请求/900 秒预算设计）

```bash
SKILL=/skills/weekly-skill
# 1) 发现输入（写 /app/work/checkpoint_discover.json）
python3 $SKILL/scripts/kg_run.py discover --input /input --work /app/work
# 2) 【模型唯一产物】读 /input/task.md 与两篇 material + case.json，
#    一次性写出 /app/work/extractions.jsonl（schema 见 references/extractions-jsonl-schema.md）
# 3) 解析+校验（坏行跳过；坏证据进 quarantine，看 /app/work/checkpoint_verify.json）
python3 $SKILL/scripts/kg_run.py apply   --work /app/work --force
python3 $SKILL/scripts/kg_run.py verify  --work /app/work --force
# 4) 建图（graph.json + graph.dot + graph.svg 到 /app/work）
python3 $SKILL/scripts/kg_run.py build   --work /app/work --force
# 5) 自动执行 case.json 的全部 query_specs
python3 $SKILL/scripts/kg_run.py query   --work /app/work --force
# 6) 装配交付（result.json + graph.* + verify_report.json + run_report.json）
python3 $SKILL/scripts/kg_run.py assemble --work /app/work --output /app/output
```

等价一键版（且会**在 discover 后立即先写一份诚实的 partial result.json**，
任何后续崩溃/超时都不会交白卷）：

```bash
python3 /skills/weekly-skill/scripts/kg_run.py all --input /input --work /app/work --output /app/output
```

修补流程：看 `/app/output/verify_report.json` 的 quarantine → 往
`extractions.jsonl` **追加**修正行（新 id）→ 重跑
`verify/build/query/assemble` 各加 `--force`。

## 5. 断点续跑与降级

- 每阶段写 `checkpoint_<stage>.json`，重跑自动跳过已完成阶段（`--force` 重算）。
- 时间不足时按 `references/budget-plan.md` 降级：先保 node/edge 主干与
  merge/nonmerge/冲突，note 全省；再不行只写核心 claim + contradicts + 1 条
  unreported，但**引文必须逐字符精确**。极端情况模型没写出文件，流水线仍交付
  `status=partial/unable` 的 result.json。
- 异常处理：缺 primary 语料 → `status=unable`；secondary 缺失 → 单篇照常；
  查询零命中 → 结果为空但 undetermined 显式列出；合同键产不出 → null + 原因。

## 6. 签名产物 run_report.json

`/app/output/run_report.json` 含：`run_meta.stages`（逐阶段秒数，**唯一允许
出现墙钟时间的区域**）、`line_acceptance`（JSONL 行数/接收/跳过明细、
quote_precision、段落覆盖率）、`budget_checklist`（模型产物数、请求预算、
时间预算、查询数、引文精度、合同镜像、checkpoint 可续跑 7 项逐条状态）。
其余交付物（result.json / graph.json / graph.dot / queries）全部确定性
（排序 + 无时间戳），可跨运行逐字节比对。

## 7. 最小示例（SYNTHETIC，端到端可复现）

`examples/synthetic/` 为**合成**语料（每份文件均带 SYNTHETIC 声明），两篇
mini 论文（P1 primary / S1 secondary，钙钛矿太阳能电池主题），一条命令跑通：

```bash
python3 scripts/run_example.py        # 或 sh examples/run_example.sh
```

模拟 `/input → /app/work → /app/output`：模型产物由
`examples/synthetic/extractions.seed.jsonl` 注入（含 2 行故意坏行演示宽容
解析、1 行坏引文演示 quarantine）。产物提交在 `examples/synthetic/output/`
供直接审查——**它们是合成演示数据，不是正式赛题答案**。预期规模：约 12 节点
/ 18 边、1 条跨篇 merge（MAPbI3 ↔ methylammonium lead iodide）、2 条显式
nonmerge（TiO2 同名不同层；21.1% vs 18.7% 不同条件不并入）、1 条 preserved
冲突、1 条 unreported（hysteresis index）、3 条自动执行的查询（实际规模约
10 节点 / 14 边，含 2 个自动 paper 节点与 reported-in 边）。
详见 `examples/README.md`。

## 8. 参考与测试

- `references/extractions-jsonl-schema.md`：模型唯一产物的逐 op schema 与红线；
- `references/query-specs.md`：4 种查询类型的确定性语义；
- `references/budget-plan.md`：请求/时间预算分配与按剩余时间降级路线；
- 每个子命令自带 `--help`；全脚本仅 Python 3 标准库、无网络、确定性输出。
