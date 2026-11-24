---
name: dataset-veritas-gate
description: >-
  当统计分析案例的输入是 CSV + SQLite 原始数据快照、需要在计算任何统计量之前先证明"数据是什么、两个源是否同一份、字段类型/单位口径"时使用本 Skill。
  Use when a statistical-analysis case (CSV + SQLite under /input) requires provenance-first analysis — file inventory with sha256, CSV encoding/delimiter/header sniffing, SQLite type-affinity audit with numeric-in-text trap detection, CSV↔SQLite cross-source consistency (row closure, column mapping, value-level compare), known-dataset fingerprint soft check (UCI Concrete 1030×9 / Iris 150×5 / Wine 178×14, warning-only), deterministic cleaning ledger with replay-verifiable closure law (rows_raw == rows_kept + rows_dropped), then one-command assumption-gated inference (t/Welch/Mann-Whitney/ANOVA/Welch-ANOVA/Kruskal-Wallis + Hedges g/η²/ω²/ε² + bootstrap CI seed=20240501 + Holm) delivering all 9 output_contract fields.
  不做的事：不静默插补、不静默删除异常值、不擅自换算单位、不用指纹硬拒数据、不证明因果。
---

# dataset-veritas-gate（上游数据真实性与跨源一致性门，Bundle A）

## 何时使用 / 边界

**适用**：
- `/input` 下有 case.json + task.md + 数据文件（CSV 和/或 SQLite `.db`），需要先做数据真实性/口径审计再做组间统计推断的案例。
- 数据可能有：无表头、非 UTF-8 编码、缺失 token、完全重复行、异常值、SQLite TEXT 存数值、CSV 与 DB 同源一致性存疑、单位口径歧义。

**不适用 / 边界**：
- 需要因果推断、回归建模、机器学习预测的任务（本 Skill 只做组间比较与描述）。
- 跨源一致 ≠ 数据真实：本 Skill 证明"两个文件记录级一致"，不证明采集过程没有问题。
- 已知指纹只做软核对（warning-only），绝不作为拒收数据的依据。

## 运行契约

- 输入：`/input/case.json` + `/input/task.md` + 数据文件（CSV + SQLite .db）。
- 中间产物：`/app/work`（cleaned_table.csv、cleaning_ledger.json、source_audit.json、digest.md、state.json、decisions.json）。
- 交付：`/app/output/result.json` + `report.md`（另附 cleaned_table.csv、cleaning_ledger.json、source_audit.json 便于复核）。
- `result.json` 必须含 `case_id` 与 `output_contract.required_fields` 全部 9 个字段：
  `case_id, status, cleaning, descriptive, hypothesis_test, effect_size, confidence_interval, interpretation, limitations`，
  另附 `sources`（每个输入文件 sha256）、`reproducibility`（seed/python/platform/utc）、`uncertainty`、`exceptions`、`decisions`。
- 诚实 partial：任何阶段失败或部分完成，写入 `status=partial/failed` 与 `exceptions` 原因，**绝不静默**。
- **不得预制答案**：所有数字必须由脚本从原始输入真实计算；禁止手填统计量。

## 精确命令工作流

```bash
# 0. 定向（1 次模型请求内完成阅读）
cat /input/case.json /input/task.md; ls -la /input

# 探测 SKILL 安装目录（通常 /skills/weekly-skill）
export SKILL_DIR=$(dirname $(find /skills -maxdepth 3 -name SKILL.md -path '*dataset-veritas-gate*' 2>/dev/null | head -1))
[ -z "$SKILL_DIR" ] && export SKILL_DIR=/skills/weekly-skill   # 单 skill 安装时兜底

# 1. 一键 baseline 全流程（0 模型请求）：来源审计→清洗→描述→假设门控推断→效应量+CI→解释草稿→9 字段 result.json
python3 $SKILL_DIR/scripts/pipeline_a.py run --input-dir /input --work-dir /app/work --output-dir /app/output

# 2. 重心机器核验（0 模型请求）
# 2a. 跨源一致性明细（已自动并入 run；需要单独复核时再跑）
python3 $SKILL_DIR/scripts/source_audit.py run --input-dir /input --work-dir /app/work
# 2b. 清洗账本核验门：不信台账，从原始输入重放规则 + 逐行哈希比对；exit 0 才可交付
python3 $SKILL_DIR/scripts/ledger_gate.py check --input-dir /input --work-dir /app/work

# 3. 读 digest（1 次模型请求），确认或覆盖 ≤5 项裁决（默认值已被应用，确认则跳过）
cat /app/work/digest.md
# 如需覆盖（0~5 次，每次一条）：
python3 $SKILL_DIR/scripts/pipeline_a.py decide --work-dir /app/work --output-dir /app/output \
    --key group_column --value <列名> --reason "依据 task.md 第 N 条"

# 4. finalize：应用全部裁决，确定性重跑并重写交付物（0 模型请求）
python3 $SKILL_DIR/scripts/pipeline_a.py finalize --work-dir /app/work --output-dir /app/output

# 5. 交付前自查（0 模型请求；全部 exit 0 才可交付）
python3 $SKILL_DIR/scripts/ledger_gate.py check --input-dir /input --work-dir /app/work
python3 -m json.tool /app/output/result.json > /dev/null && echo "result.json 合法"
python3 - <<'PY'
import json
r = json.load(open("/app/output/result.json", encoding="utf-8"))
req = ["case_id","status","cleaning","descriptive","hypothesis_test",
       "effect_size","confidence_interval","interpretation","limitations"]
assert all(k in r for k in req), "缺字段"
assert r["cleaning"]["closure_holds"], "闭合律不成立"
print("9 字段齐全，闭合律成立，status =", r["status"])
PY
```

可覆盖的裁决 key：`group_column`（分组列）、`alpha`（显著性水平）、`primary_source`（csv/db）、
`outlier_action`（flag/drop，drop 必须写理由）、`variables`（推断变量白名单，逗号分隔）、
`exclude_variables`（逗号分隔）。

## 方法决策规则（硬性）

| # | 规则 | 默认口径 |
|---|---|---|
| 1 | 主数据源 | CSV 优先；跨源 `row_count_mismatch`/`value_mismatch` 时不擅自选择，列 digest 裁决 |
| 2 | 完全重复 | `dedupe_exact_keep_first`（drop），行数必须入账并满足闭合律 |
| 3 | 缺失 | `report_and_exclude`：不零填、不插补、不整行删；按各变量有效 n |
| 4 | 异常值 | 1.5×IQR 栅栏 **flag-only，绝不静默删除**；drop 只能来自 decide 且必须写理由 |
| 5 | 正态性 | D'Agostino K²，n<8 保守按非正态（不检验） |
| 6 | 方差齐性 | Levene（median 中心） |
| 7 | 两组门控 | 正态+齐→Student t；正态不齐→Welch t；否则 Mann-Whitney（tie 校正+连续性校正） |
| 8 | k 组门控 | 全正态+齐→ANOVA；全正态不齐→Welch ANOVA；否则 Kruskal-Wallis（tie 校正） |
| 9 | 效应量+CI | 两组：Hedges g（bootstrap B=2000 seed=20240501 百分位 CI）+ Welch 均值差 CI（非参路线 Hodges-Lehmann）；k 组：η²/ω²（KW 路线 ε²），两两比较与主检验同路线 + Holm |
| 10 | 参照统计量 | 门控路线非经典 ANOVA/t 时，附 `classical_reference`（同清洗口径）与 `raw_data_reference`（未去重原始数据）——均明确标注"非决策依据"，仅用于与文献/外部口径对照 |
| 11 | 指纹核对 | UCI Concrete 1030×9 / Iris 150×5 / Wine 178×14 形状+task.md 关键词软核对，不一致只写 warning |
| 12 | 解释纪律 | 区分统计显著与实际意义；禁用"证明"；携带单位；标注剩余不确定性 |

## 预算表（≤8 次模型请求的典型分配，64 上限内留足余量）

| 步骤 | 内容 | 模型请求 |
|---|---|---|
| 0 | 定向读输入 | 1 |
| 1–2 | pipeline run + source_audit + ledger_gate（脚本执行） | 0 |
| 3 | 读 digest.md，决定覆盖与否 | 1 |
| 3b | decide（0~5 条）+ finalize（脚本执行） | 0~1 |
| 4 | 读 result.json/report.md，撰写最终答复 | 1~2 |
| 5 | 交付前自查（脚本执行） | 0 |
| 余量 | 异常处理 | ≤3 |
| **合计** | | **≤8** |

## 异常处理表

| 情形 | 识别 | 处置 |
|---|---|---|
| 样本量不足（组 n<2） | 该组进 `skipped_groups` | 变量标 `insufficient_groups`，不强行检验，写入 exceptions |
| n<8 | 正态性条目 `note: n<8，保守按非正态处理` | 走 Mann-Whitney / Kruskal-Wallis 路线 |
| 组内方差为零 | Levene 分母为 0 / Welch df 退化 | Levene 按 p=1 处理；检验退化为保守路线并在 exceptions 注明 |
| 缺失比例过高 | R2 账本 per_column_missing | >50% 时该变量推断写入 uncertainty；不插补 |
| 假设不成立 | 门控自动降级（ANOVA→Welch ANOVA→KW） | 路线与理由码写入 `hypothesis_test.*.route`，解释中说明 |
| 单位不明 | units 解析为 `unknown` | 如实标注，进 digest 待确认；禁止编造 |
| SQLite 连接失败/无用户表 | source_audit 捕获 | 以 CSV 为主源继续；exceptions 记录；status=partial |
| CSV 无表头 | detect_header=False | 形状唯一命中指纹→提示性列名（标注 fingerprint_hint 并列裁决项）；否则 c0..cN |
| numeric-in-text | DB 列 affinity=TEXT 且 ≥95% 值可解析数值 | warning + 按数值解析，verdict 标 `consistent_with_type_coercion` |
| 跨源行数/值不一致 | cross_source verdict | 不擅自选源；warning + digest 裁决 `primary_source` |
| 分组列识别失败 | pick_group_column 返回 None | 只交描述统计，`hypothesis_test` 诚实标注 `no_grouping_variable`，提示 decide 指定 |
| 入口级崩溃（目录缺失等） | 兜底 try/except | 写出 status=failed 的 result.json，exceptions 说明缺什么 |

## 文件清单

| 路径 | 作用 |
|---|---|
| `scripts/statcore_a.py` | stdlib 统计核心；`--selftest` 用 scipy 交叉校验（可选，缺失自动跳过） |
| `scripts/pipeline_a.py` | 一键 baseline：`run` / `decide` / `finalize` |
| `scripts/source_audit.py` | 重心1：来源清点+sha256、CSV 嗅探、SQLite affinity 审计、跨源一致性、指纹软核对 |
| `scripts/ledger_gate.py` | 重心2：清洗账本机器核验门（闭合律/规则重放/逐行哈希，exit 0/1 + 违例码） |
| `references/` | 跨源一致性、闭合律账本、SQLite affinity、单位与编码 四篇方法学 |
| `examples/` | 合成示例：make_synthetic.py + run_example.sh（11 项断言）+ minimal-example.md + example_output/ |
