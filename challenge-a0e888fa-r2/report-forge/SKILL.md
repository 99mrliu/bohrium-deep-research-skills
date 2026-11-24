---
name: report-forge-deliverable-rendering
description: >-
  当数据清洗案例（如对注入存储/编码故障的已发表汇总表转写件进行清洗）进入交付阶段、
  需要把清洗产物（cleaned.csv / ledger.csv / summary.json）渲染为数据质量报告
  （quality_report.md / quality_report.html）与可检查的 SVG 图表，并通过
  报告 ↔ 结果表 ↔ result.json 三方数字机械一致性门之后再交付时，使用本技能。
  本技能只管"最后一公里"的交付面渲染与一致性工程，不规定清洗算法。
  触发词：数据质量报告、quality_report、figures、SVG 图表、一致性检查、交付渲染、
  result.json 数字对齐。
---

# report-forge-deliverable-rendering：数据质量报告与图表的交付面工程

## 1. 重心与边界

本技能负责清洗完成之后的交付面：

1. **合同先行**：从 `/input/case.json` 与 `task.md` 抽取 output_contract 全部字段，
   result.json 骨架最先落地、随进度增量刷新。
2. **数字只能重算**：报告模板（`references/report_template.md`）只用 `{{placeholder}}`
   占位；`scripts/fill_report.py` 从 cleaned.csv / ledger.csv 重算每个占位符并注入，
   未知占位符拒绝渲染（退出码 4）。产物为 quality_report.md 与 quality_report.html
   （内联 SVG、简洁 CSS）。
3. **图表工程**：`scripts/figures_svg.py` 手写 SVG（纯标准库、确定性、无随机 id /
   时间戳），按 `references/figure_choice.md` 选图，每图配选择依据与图注；
   SVG 本身就是渲染预览（文本、可 diff、可直接浏览）。
4. **一致性门**：`scripts/check_consistency.py` 重算报告与 result.json 中全部数字并
   与产物比对、校验 result.json 含 case_id 与 output_contract 全部字段、校验引用的
   每个文件存在且 sha256 与登记一致；任一失败退出码 5，禁止交付。

**边界**：本技能不替代清洗判断。清洗算法严格按案例工单、数据字典与单位/QC 规则执行；
本技能只要求清洗产物满足最小接口（见第 5 节步骤 1），之后的一切数字由脚本重算，
人不手写。一致性门不过，不交付。

## 2. 铁律（继承赛题，优先级最高）

- 不得推断总体统计量；报告只陈述从产物重算得到的客观数量。
- 不得插补缺失 / 非法源值；非法值只能剔除并留痕。
- 不依据标签补造数据。
- 失败与无法解释处必须如实说明（result.json 的 `status` 与 `uncertainty`）。
- 报告中的每个数字必须能由脚本从产物重算得到；发现数字与产物对不上时，
  回到产物修正后重跑管线，**禁止手改报告迎合**。

## 3. 路径说明

技能安装位置为 `/skills/weekly-skill`。下文的 `$SK` 指技能根目录：

```bash
SK=/skills/weekly-skill
if [ ! -f "$SK/scripts/fill_report.py" ]; then
  SK=$(dirname "$(dirname "$(find / -maxdepth 6 -name 'fill_report.py' 2>/dev/null | head -n 1)")")
fi
[ -f "$SK/scripts/fill_report.py" ] && echo "SK=$SK"
```

## 4. 运行时契约

- 输入：`/input/case.json`（含 `case_id` 与 `output_contract`）与工作目录的
  `task.md`（含 output_contract 原文）；工作区 `/app/work`。
- 最终交付：`/app/output/`，其中 `result.json` 必须含 `case_id` 与 output_contract
  声明的全部字段，含诚实的 `status`（success / partial / failed）、`sources`、
  `uncertainty`、变更记录数。
- 交付物清单：`result.json`、`cleaned.csv`、`ledger.csv`、`summary.json`、
  `quality_report.md`、`quality_report.html`、`figures/*.svg`、
  `figures_index.json`、`consistency_check.json`。
- **骨架先行**：result.json 在步骤 0 就以 `status: "failed"` 骨架落盘，之后增量刷新；
  即使中途预算耗尽，评审看到的也是诚实的失败状态而不是缺文件。
- 预算：64 次模型请求 / 900 秒。本管线三条脚本命令均为秒级本地执行，不要在
  重复渲染上浪费请求；管线幂等，重跑结果逐字节一致。

## 5. 分步 Runbook

### 步骤 0：读案 + 抽合同 + result.json 骨架

```bash
mkdir -p /app/work /app/output/figures
cd /app/work
cat /input/case.json
python3 - <<'PY'
import json
case = json.load(open("/input/case.json", encoding="utf-8"))
contract = case.get("output_contract", {})
skel = {"case_id": case.get("case_id"), "status": "failed",
        "sources": [], "uncertainty": [], "artifact_hashes": {}}
for f in contract.get("required_fields", []):
    skel.setdefault(f, None)
with open("/app/output/result.json", "w", encoding="utf-8") as f:
    json.dump(skel, f, ensure_ascii=False, indent=2)
print(json.dumps(contract, ensure_ascii=False, indent=2))
PY
```

### 步骤 1：按工单清洗，产出最小接口三件

清洗判断完全依据案例工单、数据字典与单位/QC 规则，本技能不加干涉。产物接口：

- `/app/output/cleaned.csv`：UTF-8（可带 BOM）、首行表头；缺失值一律为空单元格。
- `/app/output/ledger.csv`：变更台账，列固定为
  `record_id,row_id,field,action,before,after,rule,note`；`action` 约定取值
  `unit_convert` / `drop_duplicate` / `drop_invalid` / `flag_outlier` /
  `keep_unchanged`；行级动作（如整行去重）`field` 填 `*`。
- `/app/output/summary.json`：至少含 `case_id`、`total_rows`、`total_fields`、
  `missing_values_total`、`missing_rate_pct`、`duplicate_groups_removed`、
  `unit_conversions`、`outliers_flagged`、`invalid_values_dropped`、
  `change_records`、`field_issue_counts`；可选 `histogram_fields`（数组，
  声明哪些连续数值字段画直方图）。**所有统计字段必须与前两件重算值一致，
  一致性门会逐项核验。**

### 步骤 2：fill_report.py 渲染报告

```bash
python3 "$SK/scripts/fill_report.py" \
  --cleaned /app/output/cleaned.csv \
  --ledger /app/output/ledger.csv \
  --summary /app/output/summary.json \
  --figures-index /app/output/figures_index.json \
  --out-md /app/output/quality_report.md \
  --out-html /app/output/quality_report.html
```

第一次运行时 figures_index.json 尚不存在，图表节以文字说明降级，属正常；
步骤 3 出图后**重跑同一条命令**注入图表节（脚本幂等，重跑结果一致）。
退出码 0 成功；4 拒绝渲染（未知占位符或输入缺件），不得绕过。

### 步骤 3：figures_svg.py 出图

```bash
python3 "$SK/scripts/figures_svg.py" \
  --cleaned /app/output/cleaned.csv \
  --ledger /app/output/ledger.csv \
  --summary /app/output/summary.json \
  --out-dir /app/output/figures \
  --index /app/output/figures_index.json
# 出图后重跑步骤 2 的命令，把图表节注入报告
```

生成 `figures/*.svg` 与 `figures_index.json`（每张图含 `kind_label`、`rationale`、
`caption`；被跳过的图在 `skipped` 中写明原因）。SVG 可直接用浏览器打开目检：
坐标轴从 0 开始、柱高与数据成比例、文字无重叠。

### 步骤 3b：刷新 result.json 数字与 artifact_hashes

```bash
cd /app/output && python3 - <<'PY'
import hashlib, glob, json
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()
s = json.load(open("summary.json", encoding="utf-8"))
r = json.load(open("result.json", encoding="utf-8"))
r.update({"case_id": s["case_id"], "status": "success",
          "sources": ["cleaned.csv", "ledger.csv", "summary.json"],
          "change_records": s["change_records"],
          "cleaned_rows": s["total_rows"],
          "missing_rate_pct": s["missing_rate_pct"],
          "duplicates_removed": s["duplicate_groups_removed"],
          "unit_conversions": s["unit_conversions"],
          "outliers_flagged": s["outliers_flagged"]})
files = (["cleaned.csv", "ledger.csv", "summary.json", "quality_report.md",
          "quality_report.html", "figures_index.json"]
         + sorted(glob.glob("figures/*.svg")))
r["artifact_hashes"] = {p: sha(p) for p in files}
with open("result.json", "w", encoding="utf-8") as f:
    json.dump(r, f, ensure_ascii=False, indent=2)
print("result.json refreshed,", len(files), "artifacts hashed")
PY
```

若清洗未全部完成，`status` 必须如实写 `partial` 或 `failed`，并在
`uncertainty` 中说明哪些项未完成、哪些数字因此缺失。

### 步骤 4：check_consistency.py 过门

```bash
python3 "$SK/scripts/check_consistency.py" \
  --case /input/case.json \
  --result /app/output/result.json \
  --cleaned /app/output/cleaned.csv \
  --ledger /app/output/ledger.csv \
  --summary /app/output/summary.json \
  --report-md /app/output/quality_report.md \
  --report-html /app/output/quality_report.html \
  --figures-index /app/output/figures_index.json \
  --out /app/output/consistency_check.json
echo "exit=$?"
```

退出码 0：全部通过，可以交付。退出码 5：读 `consistency_check.json` 中 `FAIL`
项的 `detail`，回到产物修正后按 步骤 2 → 3 → 3b → 4 重跑；**不过门不交付**。

### 步骤 5：交付

```bash
ls -l /app/output /app/output/figures
cat /app/output/consistency_check.json
```

确认 `/app/output/` 内含：result.json、cleaned.csv、ledger.csv、summary.json、
quality_report.md、quality_report.html、figures/*.svg、figures_index.json、
consistency_check.json。

## 6. 异常处理与诚实降级

| 情形 | 脚本行为 | 人的义务 |
| --- | --- | --- |
| 清洗产物缺件（cleaned/ledger/summary 缺一） | fill_report.py 退出码 4，拒绝渲染 | 不得手写报告顶替；result.json 记 `failed`/`partial`，uncertainty 说明缺哪件 |
| 模板含未知占位符 | fill_report.py 退出码 4，stderr 列出未知占位符名字 | 只能使用模板既定占位符；确需新数字时先扩展脚本的重算表，不得手写进模板 |
| 报告 / result.json / summary.json 数字与产物重算不符 | check_consistency.py 退出码 5，detail 指出字段与两值 | 以产物重算为准修正数据源，重跑管线；禁止手改报告迎合 |
| 引用文件缺失或 sha256 与登记不符 | check_consistency.py 退出码 5 | 重跑步骤 3b 重新登记哈希；不得删除登记项蒙混 |
| 图表数据为空（无缺失、无变更、有效值 <3） | figures_svg.py 跳过该图并在 skipped 写明原因，退出码仍为 0 | 报告第 4 节如实列出跳过原因，不得凑图 |
| 900 秒 / 64 请求预算耗尽 | —— | 步骤 0 的骨架保证 result.json 存在且 status 诚实；已完成的每件产物都可独立核验 |

## 7. 最小示例

`examples/` 内含一组**人工编造的合成数据**（模拟土壤重金属汇总表的清洗产物：
cleaned.csv、ledger.csv、summary.json、case.json、result.json）以及
`examples/expected/` 下的真实运行产物（quality_report.md、quality_report.html、
figures/*.svg 共 4 张、figures_index.json、consistency_check.json 为 PASS）。
复现命令见 `examples/README.md`，三条命令依次跑 fill → figures → check 即可
逐字节复现 expected/ 内容。
