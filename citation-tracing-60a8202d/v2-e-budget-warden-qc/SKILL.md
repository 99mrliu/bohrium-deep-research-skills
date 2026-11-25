---
name: budget-warden-qc
description: 引文追踪与关联文献发现的过程质量控制与预算治理。当需要围绕种子论文做引用扩展、且要求任何时刻中断都有诚实交付、可断点续跑、输出确定性一致、自动 QC 自检修复时触发。输入 /input/case.json 与本地语料缓存，离线确定性产出 /app/output/result.json。
---

# budget-warden-qc：过程质量控制与预算治理

## 立即执行（顺序不可颠倒）

```bash
# 第 1 步：分阶段编排，一条命令跑完全管线（stage0→3，自动 checkpoint）
python3 /skills/weekly-skill/scripts/warden.py \
    --case /input/case.json --out /app/output --workdir /app/work --max-depth 2

# 第 1 步（若中断后重启）：不要重跑全流程，用 --resume 从最近 checkpoint 续跑
python3 /skills/weekly-skill/scripts/warden.py \
    --case /input/case.json --out /app/output --workdir /app/work --max-depth 2 --resume

# 第 2 步：QC 质量回路，自检并安全修复 result.json
python3 /skills/weekly-skill/scripts/qc_loop.py \
    --case /input/case.json --out /app/output --workdir /app/work

# 第 3 步（时间充裕时）：双跑一致性校验，确认 result.json 逐字节稳定
python3 /skills/weekly-skill/scripts/reproduce.py \
    --case /input/case.json --workdir /app/work --runs 2
```

**要点**：warden.py 的 stage0 会在启动后数秒内先写一份 honest partial `result.json`，
此后任何时刻被中断，`/app/output/result.json` 都是可评的诚实交付；续跑一律用
`--resume`，不要从头重跑。脚本只用 Python 3 标准库、默认零网络、位置无关。

## 用途与适用条件

面向「引文追踪与关联文献发现」任务：从种子论文出发沿引用关系扩展候选文献。
本 Skill 的重心不是追踪算法本身，而是**过程治理**：

- **分阶段增量交付**：stage0 立即落盘 honest partial；stage1 ingest；stage2 第 1 层
  扩展；stage3 加深合并。每一阶段完成后写 checkpoint（含阶段号、完成时间、产物摘要
  哈希），任何中断后 `--resume` 从最近 checkpoint 续跑。
- **预算治理**：默认按 900 秒总预算设置 `--time-budget 850`、安全余量 30 秒；临近
  耗尽时跳过加深阶段，直接落盘当前最好版本并标注 `budget_limited`。
- **确定性输出**：所有遍历按排序键迭代、结果按稳定键排序、JSON 以 sort_keys 序列化；
  时间戳只写 `/app/work/run_log.json`，绝不进入 result.json —— 重复运行 result.json
  **字节一致**，可用 reproduce.py 验证。
- **QC 回路**：qc_loop.py 按缺陷清单自检，能安全修复的（补 case_id、补契约镜像、校正
  status）自动修复并写 change_log，不能修复的逐条写入 uncertainty。

适用条件：组织方提供本地语料缓存（Crossref/EuropePMC/OpenAlex/通用 JSON/JSONL/CSV/
TSV/edgelist/bib），无实时远程覆盖。不适用：需要联网实时检索的场景。

## 运行契约

```
/input/case.json + /input/task.md（+ /input 下组织方语料缓存）
    → 工作目录 /app/work（checkpoints/、run_log.json、qc_report.*、reproduce_report.json）
    → /app/output/result.json
```

`result.json` 必须含：

- `case_id`：逐字来自 case.json；
- `contract`：`output_contract` **逐字段镜像**，不允许丢字段；填不了的字段给 null 并在
  `uncertainty` 说明；
- `status`：ok / partial / failed，必须与 `stage_summary.completed_stage` 一致；
- `seed` / `candidates` / `edges` / `sources` / `evidence_records` / `uncertainty`；
- 每条记录与每条边都带 `source: {file, pointer}` 定位，可回指复核。

**预算意识**：64 次模型请求 / 900 秒 / 单次响应 16384 token。正确用法是让 Agent 用一条
命令跑完确定性的 Python 管线（模型请求 ≤ 数次：读 SKILL、发命令、查报告），而不是让
模型逐条手工整理文献。先存 honest partial 再迭代是本 Skill 的第一原则。

## 输入

| 输入 | 位置 | 说明 |
|---|---|---|
| case.json | `--case`，默认 `/input/case.json` | 含 `case_id`、`seed`（DOI 或标题）、`output_contract` |
| 语料缓存 | `--roots` 指定；缺省按 `/input` > `/app/work` > cwd 递归扫描 | 格式位置未知，脚本自动嗅探 |
| task.md | `/input/task.md` | 人读任务说明，不改变管线行为 |

## 输出

| 产物 | 位置 | 说明 |
|---|---|---|
| result.json | `/app/output/result.json` | 最终交付；确定性字节 |
| checkpoints | `/app/work/checkpoints/stage{0..3}.json` | 阶段号、完成时间、产物 sha1、续跑载荷 |
| run_log.json | `/app/work/run_log.json` | 唯一含时间戳的文件，不参与一致性比较 |
| qc_report | `/app/work/qc_report.json` + `.md` | 缺陷清单执行结果与 change_log |
| reproduce_report | `/app/work/reproduce_report.json` | 双跑一致性结论与差异点 |

## 关键方法

1. **阶段编排**：stage0（契约骨架 honest partial）→ stage1（多格式 ingest，全语料来源
   注册表含 sha1 与解析成败）→ stage2（种子解析 + 第 1 层扩展，status 仍为 partial 并
   注明仅 1 层）→ stage3（加深到 `--max-depth`，DOI 规范化 + 标题规范化双键去重合并，
   反向索引恢复前向 citation 边并标注 `direction_restored: true`）。
2. **诚实 stub**：语料内解析不出的引用目标保留为 stub（仅原始指针 + locator），绝不补造
   作者/年份/标题；stub 比例写入 uncertainty。
3. **断点续跑**：checkpoint 内含续跑所需的全部载荷（语料记录、图边、候选），`--resume`
   跳过已完成阶段；预算降级跳过的阶段**不写** checkpoint，续跑时会重新尝试。
4. **确定性**：文件按路径排序扫描、记录与边按稳定键排序、json sort_keys 序列化、
   result.json 内零时间戳。
5. **QC 清单**：见 references/qc_checklist.md（Q1–Q7）。

## 异常处理表

| 异常 | 行为 | 出口 |
|---|---|---|
| case.json 缺失 | 写 status=failed 空骨架后退出 | 退出码 2 |
| 语料文件解析失败 | 记入 sources 注册表（parse_ok=false + error），不中断 | 继续 |
| 种子全部不可解析 | 写 partial，uncertainty 说明，跳过扩展 | 退出码 0 |
| 预算临近耗尽 | 跳过当前/后续加深阶段，落盘最好版本，budget_limited=true | 退出码 0 |
| 中途被 kill | result.json 保持最近完整阶段版本；`--resume` 续跑 | — |
| QC 发现可修复缺陷 | 自动修复并写 change_log | 退出码 0 |
| QC 发现不可修复 critical | 写入 uncertainty，ok=false | 退出码 1 |
| reproduce 双跑不一致 | 报告差异点（首异字节偏移 + unified diff 头部） | 退出码 1 |

## 自查方法

1. `qc_loop.py` 退出码为 0 且 stdout 打印 `ok=true`；
2. 打开 `/app/work/qc_report.md`，确认无未决 critical/major；
3. `reproduce.py` 打印 `identical=true`；
4. 抽查 result.json：每条 candidates/edges 均有 `source.file` 与 `source.pointer`；
   `contract` 覆盖 output_contract 全部字段；`status` 与 `stage_summary` 一致；
5. 模拟中断：删除 `checkpoints/stage3.json` 后 `--resume`，确认只补跑 stage3。

## 最小示例指引

`examples/` 内含**合成示例（SYNTHETIC，全部为虚构文献，DOI 形如 10.0000/synth.*）**：
4 个语料文件（Crossref 风格 JSON、EuropePMC 风格 JSON、OpenAlex 风格 JSONL、CSV 边表）
覆盖 5 篇虚构文献 + 1 个故意无法解析的引用目标（演示 stub）。运行方式与逐步演练见
`examples/walkthrough.md`；`examples/run_out/` 保留了该合成示例的真实运行产物。

## 限制

- 不做全文阅读、引文语境理解、关键词检索与相关性打分；候选即引用闭包。
- 身份合并只有 DOI 规范化精确键 + 标题规范化键两级基线；两键都缺失的记录保持独立。
- 不联网：无 `--allow-net` 之外的任何远程调用，语料外的文献一律只能成为 stub。
- checkpoint 载荷随语料规模线性增长，超大语料（数十万记录）下建议提高存储预算。
- reproduce.py 的双跑各起一个子进程，耗时约为单次管线的 2 倍，预算紧张时可省略。
