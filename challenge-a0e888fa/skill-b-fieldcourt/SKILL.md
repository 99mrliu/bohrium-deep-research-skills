---
name: fieldcourt-semantic-adjudicator
description: >-
  科研汇总表的字段级语义裁定台：缺失分类学（未检测/低于检出限/录入缺失/真值0）、
  单位注册表内可逆换算、归一化主键去重、物理界异常标记。当案例提供数据表+
  数据字典+单位/QC 规则+清洗工单，要求"每个字段的处理都有明确规则和依据"时
  使用。Agent 只做一件事——对照字典把裁定写进 decisions.json；引擎负责验证
  （覆盖不全/单位越界/无依据一律拒绝）与确定性执行（逐格台账）。
---

# fieldcourt：字段语义裁定台

## 重心

清洗的正确性不在代码而在**裁定**：哪个 token 是"未检测"而不是"真值 0"、
mg/L 与 μg/mL 是否同量纲、哪一列是真实主键、越界值保留还是剔除。
本技能把全部裁定集中到一份人可读的 `decisions.json`（每条带 `source` 依据
定位），引擎 `adjudicate.py` 先校验后执行：**覆盖不全、单位不在注册表、
非默认处置无依据 → 拒绝运行**。铁律：绝不插补缺失/非法源值，绝不推断总体
统计量；未声明的字段原样保留。


脚本路径说明：技能默认安装在 `/skills/weekly-skill`，下文以 `$SK` 代指该目录；
若不在该路径，用 `find / -maxdepth 6 -name 'scripts' -path '*skill*' 2>/dev/null` 定位技能根。
所有脚本均为 Python 3 标准库、确定性、只读输入文件。

## 流程

### 0. 读案与保底（最先做）

```bash
ls -laR /input; cat /input/case.json; cat task.md
mkdir -p /app/work /app/output
```

- 提取 `case_id` 与 `output_contract` 全部字段；立即写 `/app/output/result.json`
  占位版（`"status":"in_progress"` + 全字段占位），每阶段增量刷新。
- 若输入表存在乱码/分隔符异常，先用 utf-8-sig 读入并另存为规范 CSV 到
  `/app/work/`（编码修复逐格留痕），再对规范表勘测。

### 1. 勘测

```bash
python3 $SK/scripts/field_survey.py /app/work/table.csv \
    --dict <数据字典> --out /app/work/survey
```

读 `survey_report.md`：字段画像、哨兵 token 计数、内嵌单位串、主键候选唯一性。

### 2. 裁定（Agent 的核心工作）

复制 `decisions.template.json` 为 `decisions.json`，对照**数据字典、单位/QC
规则、工单**逐项填写：

- 每个哨兵 token 的缺失分类（判定树见 `references/missing_taxonomy.md`）；
- `unit.canonical`（必须在注册表内，见 `references/unit_registry.md`；
  带偏移换算如 ℃→K 一律拒绝，标记保留）；
- `key_columns` 与 `dedup.keep`（裁定依据见
  `references/dedup_key_adjudication.md`）；
- 每个非默认处置的 `source`（文件+行/条目定位）。

### 3. 验证 + 执行

```bash
python3 $SK/scripts/adjudicate.py --decisions /app/work/decisions.json --validate
python3 $SK/scripts/adjudicate.py --decisions /app/work/decisions.json \
    --run --out /app/work/adjudicated
```

校验失败（退出码 4）逐条修订后重跑。产物：`cleaned.csv`、`ledger.csv`（逐格
台账：行/字段/动作/旧值/新值/规则/依据）、`review_queue.csv`（键冲突、未知
单位、换算失败——全部保留原值待复核）、`digest.md`。

### 4. 复核 + 交付

- 逐条处理 `review_queue.csv`：能据字典裁定的回到第 2 步补裁定重跑；不能裁定
  的写入 result.json 的不确定性说明。
- 质量报告数字**从 field_summary.json 与 ledger.csv 重算**，不得手写。
- `/app/output/`：result.json（output_contract 全字段、status 如实）、
  cleaned.csv、ledger.csv、decisions.json、digest.md、review_queue.csv。

## 异常处理

- 空表/无表头 → survey 退出码 3，result.json 记 failed 并说明；
- 未知单位 → 保留原值 + 复核队列，绝不猜测换算；
- 主键冲突（同键不同值）→ 全部保留 + 复核队列，绝不静默删除；
- 时间不足 → 保证 result.json 合法 + ledger/digest 落盘，降级为 partial。

## 最小示例

`examples/`：合成水质汇总表（哨兵码、μg/mL 与 mg/L 混写、大小写/全角近似
重复行、越界值）+ 合成数据字典/工单 + 填写完成的 decisions.json + 真实运行
产物，见 `examples/README.md`。全部为合成数据。
