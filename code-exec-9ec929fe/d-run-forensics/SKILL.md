---
name: run-forensics
description: 运行调试与过程取证重心。当科研数据分析任务（/input 的 case.json、task.md、CSV/SQLite → /app/output/result.json）要求"过程与失败原因能被他人复核"时使用。核心是把每一次代码执行包装成带完整现场的结构化事件：runcap exec 记录命令行、工作目录、退出码、耗时、stdout/stderr 全文与相关输入哈希，非零退出自动分类根因并给处置建议；init 先固定输入哈希清单与 result.json 诚实骨架；replay 从台账生成可逐步重放的 replay.sh；report 汇总失败分类与重试链（同一命令修了几轮一目了然）；seal 收尾时把台账并入 provenance 并强制未落实字段降级为 partial。不适用：无需执行任何外部命令的纯推理任务。
---

# run-forensics：每一步都留下可以重放的现场

## 重心：运行调试

题目点名的失败恶习是"出错之后不定位原因，换一段代码继续试"。本 Skill 用机制消灭它：所有执行必须经 `runcap exec` 包装，失败自动生成 failure_record（错误分类 + 处置建议），同一 tag 的多次执行形成**重试链**——复核者能看到你每一步修了什么，而不是一串无上下文的报错。

## 固定路径与运行契约

- 工具：`/skills/weekly-skill/scripts/runcap.py`（纯标准库），台账 `/app/work/runs.jsonl`（append-only）
- 输入：`/input/case.json`（case_id、output_contract）、`/input/task.md`、数据文件
- 交付：`/app/output/result.json` 含 `case_id`、output_contract 全部字段、`anomalies`、`provenance`（seal 自动并入台账摘要与未解决失败清单）
- 诚实 partial：seal 发现契约字段为 null、或存在**未解决失败**（某 tag 最后一次执行仍非零）而 missing_fields 为空时，强制 status=partial 并登记原因

## 执行协议

### 第 0 步：建档

```bash
python3 /skills/weekly-skill/scripts/runcap.py init --input /input --work /app/work --output /app/output
```

固定每个输入文件的 sha256（复核者先核对哈希），落盘 result.json 骨架。

### 第 1 步起：一切执行经 runcap 包装

```bash
python3 /skills/weekly-skill/scripts/runcap.py exec --work /app/work \
  --tag profile --hash /input/data.csv -- \
  python3 /skills/weekly-skill/scripts/runcap.py exec --work /app/work --tag inner -- python3 -c '...'
```

规则：

- `--tag` 是逻辑步骤名（profile/clean/stats/figure/sql1）；**修复后重跑用同一个 tag**，自动形成重试链；不同步骤用不同 tag。
- `--hash` 登记本步读取的输入文件，台账中留下其 sha256，事后可证明"这份结果确实出自这份数据"。
- 非零退出时先读 failure_record 的 class 与 advice（依赖缺失/路径/编码/字段名/表名/内存/超时……），**定位根因后**再以同 tag 重跑；禁止绕过台账直接跑命令。

### 收尾：report → replay → seal

```bash
python3 /skills/weekly-skill/scripts/runcap.py report --work /app/work   # run_summary.md：失败分类 + 重试链
python3 /skills/weekly-skill/scripts/runcap.py replay --work /app/work   # replay.sh：复核者可逐步重放
python3 /skills/weekly-skill/scripts/runcap.py seal --input /input --work /app/work --output /app/output
```

seal 通过（exit 0）才允许交付；partial 时必须能在 missing_fields 中指出哪个字段因哪次失败未完成。

## 失败处置原则

详见 `references/failure_playbook.md`。要点：每类失败有固定处置路径（如 `no such table` → 先查 sqlite_master 再改查询）；连续两次同类失败必须停下来写 anomalies 说明，不得第三次盲目重试；所有未解决失败最终都出现在 provenance.unresolved_failures 中，无处隐藏。

## 最小调用示例（合成示例，非正式案例结果）

```bash
cd /skills/weekly-skill/examples && bash run_example.sh
```

对合成数据跑一条三步管道（clean → stats → sql），其中 sql 步第一次故意查询不存在的表（演示失败现场捕获与分类），修复表名后以同 tag 重跑成功，形成 2 步重试链；随后 report/replay/seal 收尾，replay.sh 真实重放成功。示例数据人工合成，不对应任何正式案例。
