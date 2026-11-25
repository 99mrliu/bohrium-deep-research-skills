---
name: rerun-impact-ledger
description: Execute, audit, compare, selectively recompute, and finalize four source-conditioned benchmark-DRAFT runs with immutable lineage.
---

# Rerun Impact Ledger

## 触发与不触发

**触发**：用户要求实际执行命令、失败即失败、不可变运行清单、逐 item 的 source/rubric/raw-output/score 血缘、语义重跑、版本依赖影响分析、选择性重算或严格 SUCCESS/PARTIAL 交付，且任务来自四个 source-conditioned `benchmark-DRAFT` item 的真实段落或表格源。

**不触发**：仅做泛化 source quote 相似度评分、制作 blueprint/UI、进行无执行证据的盲审、只润色答案、只生成文件清单、不需要运行与版本血缘的普通问答。Hash 对比不得替代内容审查。

## 实际中文运行约束

1. 首先读取真实 `/input/case.json`、`/input/task.md` 与 `/input/materials/`。从 case 动态取得原 `case_id`，独立解析 `output_contract`：支持字段名顶层 list、`fields`/`required_fields`/`required_top_fields`/`required_top_level_fields` list（字符串或含 `name` 的 descriptor）、direct field map 与 `properties` map。不得写死替代 ID，也不得漏掉任何顶层字段；即使 contract 未重复声明，也必须输出顶层 `case_id` 和 `status`。逐项核对四个 item 的任务、引用、rubric、计算和真实来源；**内容正确性由 agent 基于真实来源负责**，脚本只证明执行与血缘。
2. 工作目录使用 `/app/work`。初始化后立即写 `/app/output/result.json` 的安全 PARTIAL：保留原 `case_id`，且 `output_contract` 的**每个字段都在顶层**。不得等待命令结束才创建结果。
3. 在 `/app/work` 根据真实输入撰写恰好四个 item、reference answer、rubric、evidence 和 computation 规格。每项必须引用真实段落/表格定位及原文；禁止预填正式答案结果、虚构固定 hash/时间/模型/分数。依赖版本必须单独建 item bank，原件不可覆盖。
4. 所有工具使用 Python 3 标准库；从 bundle 根目录以相对路径调用 `scripts/*.py`。命令必须实际执行，非零、超时、启动失败、缺失 expected output 或超输出预算均为 FAILED，绝不能成为 STABLE/SUCCESS。
5. 模型与 harness 仅能通过 `--model`、`--harness` 或 `DECLARED_MODEL`、`DECLARED_HARNESS` 显式声明；缺省为 `unknown`。时间与 hash 由执行时生成。时间预算与输出预算必须显式传参。
6. 最终只有全部运行门、恰好四个 item、所有血缘校验以及动态字段/type 校验通过才可写 SUCCESS；否则写诚实 PARTIAL，说明 uncertainty、limitations、sources 和 change_records。未识别、无法绑定实际内容的字段保留为 descriptor 对应的 typed empty/null，且必须强制 PARTIAL，绝不能静默 SUCCESS。失败或 PARTIAL finalize 默认非零；只有显式 `--allow-partial` 可把“已生成 PARTIAL”作为工具调用完成，但 PARTIAL 本身永不等于任务成功。

## 执行步骤

### 1. 先写安全网，再初始化真实 run

科学阅读与题卡撰写之前，先执行不依赖 item bank 的安全网命令：

```bash
python3 scripts/early_partial.py --case /input/case.json --output /app/output/result.json
```

完成真实四题及本地 scorer 后，再初始化实际运行；`init_run.py` 要求四题 bank 已存在，因此不得拿它冒充题卡撰写前的早期 partial：

```bash
python3 scripts/init_run.py \
  --input-dir /input --work-root /app/work \
  --output-result /app/output/result.json \
  --item-bank /app/work/item_bank_v1.json \
  --time-budget-seconds 120 --output-budget-bytes 10000000 \
  --model unknown --harness unknown
```

stdout 是新建的唯一 run directory。`manifest.json` 与 `run_config.json` 创建后置为只读；保存输入字节数、SHA-256、Python/平台版本、显式预算和声明值。

### 2. 实际运行

将 argv 编成 JSON 数组，路径参数显式给出；`run_command.py` 固定 `shell=False`：

```bash
python3 scripts/run_command.py \
  --run-dir RUN_DIRECTORY --cwd /app/work \
  --command-json '["python3","scorer.py","--item-bank","item_bank_v1.json","--materials","/input/materials","--run-config","RUN_DIRECTORY/run_config.json","--output-dir","RUN_DIRECTORY"]' \
  --timeout-seconds 100 \
  --expected-output selection.json --expected-output scores.json --expected-output errors.json
```

dirname 绝对化由调用者完成；示例中的数组只是 argv 结构，不是可照抄的执行结果。stdout/stderr、returncode/exit_code、duration 和期望输出 hash 实际保留。运行后生成只读 `command_record.json` 与 `execution.json`，初始 manifest 不被改写。

### 3. 两次真运行与影响分析

用同一 bank/materials 独立初始化两个 run 并各执行一次，然后：

```bash
python3 scripts/compare_runs.py --run-a RUN_A --run-b RUN_B \
  --item-bank BANK --output COMPARISON.json
python3 scripts/impact.py --old-bank OLD_BANK --new-bank NEW_BANK \
  --old-materials OLD_MATERIALS --new-materials NEW_MATERIALS \
  --old-run RUN_A --output IMPACT.json
```

仅允许删除 compare 中声明的 volatile 字段。errors 不相等即不相等并返回非零。`semantic_equal=true` 只表示重跑语义重复，不表示科学正确。

按 `impact.recompute_item_ids` 初始化新版本的独立 run，只对受影响 ID 执行 scorer；未影响分数只有在依赖及适用评分语义均未变时才可比较，不能无条件继承。

### 4. 严格结束

```bash
python3 scripts/finalize.py --case /input/case.json --item-bank BANK \
  --run-dir RUN_A --comparison COMPARISON.json --impact IMPACT.json \
  --selective-run SELECTIVE_RUN --output /app/output/result.json
```

逐项验证 `item -> raw_output_id -> run_config_sha256 -> score_id -> rubric_sha256`，同时核对实际 raw 文件/text、reference-answer hash、来源字节、rubric 组件和分数求和。最终保留 sources、uncertainty、change_records 与 limitations。`items` 及 `benchmark_draft`/`questions` 是四个完整 item record：保留原 bank 的 task/reference_answer/rubric/evidence/computation 等全部内容，并附完整 raw_output、score_record 和常用 score 字段；`item_bank` 是带完整 items 的原 bank object。`scores`、`score_report`、`rollup` 分别绑定完整分数列表、分数报告和汇总；`summary`/`success`/`run_manifest` 也按实际运行内容绑定。未支持的字段名不得伪造内容。

## 本地合成示例

`examples/synthetic/` 自带四个 synthetic、source-conditioned `benchmark-DRAFT` items，两个 case/task/materials/item-bank 版本及本地确定性 scorer。它从真实段落和 CSV 计算百分比、排除后数量、表格聚合及跨源求和，不是通用引文相似度 scorer。每项 rubric 只有两个 0/1 组件（calculation、final_answer），单 item 得分始终为 0/1/2，满分 2；四个正例 item 的总分为 8/8。

```bash
./run_example.sh --output-dir /app/work/synthetic-output
# 或不传参数，由 mktemp 创建 bundle 外目录
./run_example.sh
```

示例执行两个完整正例 run、compare、impact、仅三项的新版本重算、finalize，以及一个真实非零负例。随后 `examples/contract_regression.py` 复用真实正例 run，验证 7 种 SUCCESS contract shape/alias 组合、未知字段与声明 type 不匹配两种 PARTIAL gate，并核对完整 item/raw/score 内容。负例 gate 必须生成 FAILED/PARTIAL 而非 STABLE/SUCCESS；比较 hash 由当前 run 内容重新计算后断言，不使用固定文档 hash。所有日志、raw outputs、manifests、contract cases/results 和 result 均保留在 bundle 外。

详见 `references/run_schema.md` 与 `references/comparability.md`。
