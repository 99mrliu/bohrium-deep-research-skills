---
name: number-recompute-core
description: 引用与事实核验的"数值与统计重算"中枢。当任务要求审查论文或科研材料中摘要、正文、表格、图注之间的数字、样本量、百分比、显著性表述是否自相矛盾时使用。核心立场：凡可重算的必须重算，重算不过的就是硬证据。机制：number_ledger.py 用正则族把全文数字（计数、百分比、mean±SD、p 值、置信区间）连同页码与宿主句抽成数字账本；recompute.py 在账本上执行五类确定性检查——百分比由分子分母重算、p 值与显著性措辞匹配、组样本量合计与声明总数比对、同名词计数交叉一致、表格合计行重算——矛盾以退出码 1 硬报警。重算只能覆盖机械部分；覆盖不到的一致性判断由 Agent 按 references/stat_reporting.md 完成并落 finding。
---

# number-recompute-core：数字账本与重算矛盾引擎

## 1. 定位与核心立场

统计报告类问题的特点是**可机械判定**：百分比能由分子分母重算、合计能重加、p 值与"显著/高度显著"措辞的匹配是阈值逻辑。基础 Agent 常凭语感判断数字"看起来一致"，漏掉真矛盾、误报假矛盾。本 Skill 的重心是把所有可重算的一致性检查从模型手里拿过来，交给确定性脚本：脚本报的矛盾带完整重算过程（claimed vs recomputed），可直接作为 finding 的 basis；脚本覆盖不到的部分（单位合理性、统计方法适配）才交给 Agent 判断，并在 basis 中注明"非机械判定"。

## 2. 适用条件与不适用范围

适用：含实验数据、样本量、百分比、统计检验表述的论文/报告（电子 PDF、OCR 后扫描件、纯文本）。不适用：数据分析建模（不重跑作者的分析，只做一致性重算）、润色、综述写作。

## 3. 运行契约（Harbor）

- 输入 `/input/case.json`、`/input/task.md`；工作目录 `/app/work`；交付 `/app/output/`。
- `result.json` 含 `case_id` 与 case.json `output_contract`（或 `outputContract`/`outputs`）声明的全部字段（逐字段同名复制，无法填充置 `null` 并记入 uncertainties）。
- 预算 64 次模型请求 / 900 秒 / ≤16384 token 每响应。脚本不占预算；阶段末落盘，可中断恢复；诚实 partial。
- 禁止编造数字、重算结果或工具输出；重算过程必须可从 numbers.jsonl 与 contradictions.json 复盘。

### 防御式输入解析

同常规：`case_id` 多字段回退；材料字段 `paper/pdf/material/document/file/manuscript` 回退到 `/input/` 文件序；`task.md` 要求优先；材料缺失走 blocked（仍写 result.json）。

## 4. 工作流程

### 阶段 0：解析（脚本）

```bash
cd /app/work
python3 <SKILL_DIR>/scripts/ingest_text.py <材料路径> pages.jsonl
```

### 阶段 1：数字账本（脚本）

```bash
python3 <SKILL_DIR>/scripts/number_ledger.py --pages pages.jsonl --out numbers.jsonl
```

每条记录：`{"id","page","kind","value","context","raw"}`，kind ∈ `count | percent | percent_with_fraction | pvalue | mean_sd | ci | table_row`。账本同时是"数字清单"，Agent 阶段 2 的非机械检查必须引用账本 id，不另行凭印象找数字。

### 阶段 2：重算引擎（脚本）

```bash
python3 <SKILL_DIR>/scripts/recompute.py --ledger numbers.jsonl --pages pages.jsonl \
    --out contradictions.json
```

五类检查（语义详见 `references/numeric_checks.md`）：

- **N1 百分比重算**：`X% (a/b)`、`(a/b) = X%`、`a of b (X%)` 三种句式，容差 0.5 个百分点（四舍五入）。
- **N2 p 值—措辞匹配**：p 值 ±80 字符窗口内的显著性措辞：`highly significant` 要求 p<0.01；`significant`（且无 not/no 否定）要求 p<0.05；`not/no significant` 要求 p≥0.05。
- **N3 组量合计**：单句内多个组计数（"group A contained x … group B contained y"）之和必须与全文任一声明总数（"N participants/patients/subjects/samples"）匹配。
- **N4 同名计数交叉**：同一名词（participants 等）在全文的计数取值集合；取值 >1 时输出交叉核对条目（提示 Agent 判断是否摘要-正文矛盾）。
- **N5 表格合计**：管道表格中含 `Total/合计` 行时逐列重加。

N1/N2/N3/N5 违例为**硬矛盾**（退出码 1）；N4 为提示级。每条矛盾含 `claimed`、`recomputed`、`delta`、`page`、`quote`，直接复用为 finding basis。

### 阶段 3：非机械统计审查与六类补全（Agent，约 20–30 次请求）

- 统计报告类：硬矛盾逐条落 finding（severity 按 `references/stat_reporting.md`：核心结论所依赖的数字矛盾 ≥ major）；N4 提示逐条人工判断；统计方法适配性（检验选择、多重比较、样本量依据）按 stat_reporting.md 检查——这些是判断不是重算，basis 写明推理。
- 其余五类（事实核验、引用支持、方法设计、论证链、学术规范）按常规要点审查，每条 finding 带 locator + 逐字 quote。
- 交付 `/app/output/`：`result.json`、`review_report.md`、`run_log.jsonl`、`evidence/`（numbers.jsonl、contradictions.json 副本）。result.json 顶层加 `numeric_audit`：`{"ledger_entries": n, "hard_contradictions": n, "cross_check_notes": n, "checks": {"N1": "run", ...}}`。

### 阶段 4：交付自检（脚本 + Agent）

finding 的 quote 逐字回查 pages.jsonl；统计报告类 finding 的 basis 必须含重算出处（contradictions.json 的条目 id）或注明"非机械判定"。

## 5. 异常处理

| 情况 | 处置 |
|-|-|
| 解析失败 | blocked 流程 |
| 数字抽取覆盖率低（如全文 <5 条账本记录但有数据表） | 在 uncertainties 声明抽取局限，补充人工阅读表格页 |
| 扫描件 OCR 数字误读（0/O、1/l） | 重算矛盾先回看渲染页核对字形再下结论；确认 OCR 误读不算论文错误 |
| 表格非管道格式（PDF 栏对齐文本） | N5 跳过并在 uncertainties 声明；Agent 用阅读方式核对合计 |
| 重算引擎自身异常 | 记录 stderr 到 run_log，降级为纯 Agent 审查并标 partial |

## 6. result.json Schema

```json
{
  "case_id": "...", "skill": "number-recompute-core",
  "status": "completed | partial | blocked",
  "coverage": {"事实核验": "checked", "引用支持": "checked", "方法设计": "checked", "统计报告": "checked", "论证链": "checked", "学术规范": "checked"},
  "numeric_audit": {"ledger_entries": 0, "hard_contradictions": 0, "cross_check_notes": 0,
                    "checks": {"N1": "run", "N2": "run", "N3": "run", "N4": "run", "N5": "run"}},
  "findings": [{"id": "F-01", "category": "统计报告", "issue_type": "事实错误",
    "severity": "major", "location": {"locator": "p.1", "page": 1, "quote": "52.5% (55/120)"},
    "claim": "...", "verdict": "...", "basis": "recompute N1: claimed 52.5% vs 55/120=45.83% (contradiction id C-01)",
    "suggestion": "...", "confidence": "high", "recheck": "python3 scripts/recompute.py ...", "needs_human_review": false}],
  "unchecked_items": [], "uncertainties": [],
  "artifacts": {"report": "review_report.md", "ledger": "evidence/numbers.jsonl", "contradictions": "evidence/contradictions.json", "log": "run_log.jsonl"}
}
```

## 7. 参考资料

- `references/numeric_checks.md`：N1–N5 的精确语义、容差、句式覆盖与已知盲区。
- `references/stat_reporting.md`：非机械统计审查清单与严重度映射。
- `examples/`：**合成示例**——埋了四处矛盾的合成短文，演示账本与重算引擎的硬报警。
