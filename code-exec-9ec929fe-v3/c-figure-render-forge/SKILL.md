---
name: figure-render-forge
description: >-
  将科研图表生产工程化的技能：适用于任务要求产出与数据字典严格绑定的可发表级图表的场景（轴标签等于字段名加单位、单位未知即阻断并标记、确定性渲染、图下数据随附、独立 QC 复核图中全部数值声明）；不适用于无需出图的纯计算案例，或一次性探索性快图——此时绑定与 QC 的工程开销大于收益。
---

# figure-render-forge：图表渲染锻造

## 重心与设计理由

本技能的重心是下游渲染工程，即图表—数据绑定、确定性渲染、图下数据随附与渲染 QC 四个环节。挑战指出的典型静默错误是图的轴、单位、图例与原始数据不一致：图看似合理，数值声明却与数据脱节。为此，本技能将每张图视为一项必须可被独立复核的工程产物：

1. 先声明后渲染。每张图在渲染前以 figure plan JSON 显式声明（标识、类型、列绑定、标题），渲染器只校验、不擅自修改计划。
2. 轴与数据字典硬绑定。轴标签一律为“字典显示名（单位）”；被绘制的列缺少字典条目或单位时，不猜测、不杜撰，记录 `unit_unknown` 异常，使用裸名，并将该图在 manifest 中标记 `needs_review`。
3. 确定性渲染。显式固定 rcParams（分辨率、字体回退链、网格等），全流程无任何随机数；同一输入字节级可复现地产生同一布局决策。
4. 图下数据随附。每张图附带 `<id>.figure_data.csv`，内容为被绘制的精确数值及被剔除的空值行数说明。
5. 渲染 QC。QC 子命令通过独立代码路径从原始 CSV 重新推导 manifest 中的每一项数值声明（样本量、最值、分组计数），并核验 PNG 魔数、轴标签单位字符串与图下数据行数，任何一项不符即整体失败。

## 固定路径与运行契约

- 技能安装路径：`/skills/weekly-skill`；核心脚本为 `/skills/weekly-skill/scripts/figforge.py`。
- 输入只读：`/input/case.json`（含 `case_id` 与 `output_contract`）、`/input/task.md`（中文任务书）、数据字典与数据文件。
- 草稿与中间产物：`/app/work`。
- 交付物：`/app/output`，其中必须包含 `result.json`。
- `result.json` 契约：必须包含 `case_id` 以及 `output_contract` 声明的全部字段；`status` 必须诚实（`success`／`partial`／`failed`）；`anomalies` 逐条记录异常；`provenance` 必须包含各输入文件的 sha256；`change_records` 记录每次写盘动作。部分完成时必须逐项说明受限之处，严禁编造任何数值或图件。
- 图件产物（PNG、可选 SVG、`figure_data.csv`、`figures_manifest.json`）写入 `/app/output/figures/`，并在 `result.json` 中登记路径与 manifest 摘要。

## 执行协议

1. 阅读 `/input/task.md` 与数据字典，起草 figure plan JSON。可先运行 `figforge.py plan` 获得启发式草稿，但必须由代理逐条审阅修订（列绑定、图型、标题），随后将定稿保存至 `/app/work/figure_plan.json`。
2. 运行 `figforge.py render --csv <数据> --dictionary <字典> --plan /app/work/figure_plan.json --outdir /app/output/figures`，生成 PNG、`<id>.figure_data.csv` 与 `figures_manifest.json`。
3. 检查 manifest：确认每张图的 `axes`（列、标签、单位、n_plotted、min、max）、`groups`（分组水平与计数）与 `needs_review` 标记；存在 `needs_review` 的图必须在 `result.json` 的 `anomalies` 中说明原因。
4. 运行 `figforge.py qc --manifest /app/output/figures/figures_manifest.json --csv <数据>`；退出码必须为 0。任何 FAIL 必须先修复数据或计划再重渲染，不得跳过。
5. 将图件路径、manifest 摘要（图数、各图 n_plotted、needs_review 列表、QC 结论）填入 `result.json` 的对应 `output_contract` 字段。
6. 交付前核对清单：`result.json` 含 `case_id` 与全部契约字段；状态诚实；异常与受限项已列明；provenance 含输入 sha256；所有图均通过 QC 或已如实标注未渲染。

## 异常处理

- 无 matplotlib：渲染器降级为仅交付计划回显、`figure_data.csv` 与 manifest（条目状态 `figure_not_rendered`），记录 `matplotlib_missing` 异常并以退出码 3 结束；`result.json` 状态至多记为 `partial` 并说明图件未渲染。
- 未知单位：被绘制列无字典条目或条目无单位时，记录 `unit_unknown` 异常、轴用裸名、图标记 `needs_review`；绝不猜测单位。
- 列不存在或类型不兼容（数值轴列无任何可解析数值）：以 `[figforge]` 前缀报错并以退出码 2 终止，须修正计划后重跑。
- 空分组：某分组水平无任何数值时记录 `empty_group` 异常并标记 `needs_review`；全部为空则报错终止。
- 空值：无法解析为数值的行被剔除，剔除数记入 manifest 的 `dropped_null_rows` 与 `figure_data.csv` 首行注释。

## 预算意识

预算为 64 次模型请求、900 秒。计划定稿后渲染与 QC 均为秒级本地命令，不消耗模型请求；应先保存部分结果（计划、manifest、`result.json` 草稿）再做精修。图件数量以契约为准，不为凑数增加图；QC 一次通过即不再重渲染。

## 最小调用示例（合成示例）

```bash
cd /skills/weekly-skill
bash examples/run_example.sh        # 草稿计划 → 渲染 → QC → 打印 manifest
# 或逐步：
python3 scripts/figforge.py plan --csv examples/synthetic_case/concrete_like_syn.csv \
    --dictionary examples/synthetic_case/data_dictionary.json --out /app/work/draft_plan.json
python3 scripts/figforge.py render --csv examples/synthetic_case/concrete_like_syn.csv \
    --dictionary examples/synthetic_case/data_dictionary.json \
    --plan examples/synthetic_case/figure_plan.json --outdir /app/output/figures
python3 scripts/figforge.py qc --manifest /app/output/figures/figures_manifest.json \
    --csv examples/synthetic_case/concrete_like_syn.csv
```

示例字典故意不给 `water` 列单位，凡绘制 `water` 的图即被标记 `needs_review` 并记录 `unit_unknown`，用于演示诚实阻断路径。

## 局限性

- 仅支持直方图、散点图、分组箱线图与分组均值±标准差条形图四类；折线、热力、双轴等图型需另行扩展。
- 单位只做“是否存在”与“字符串一致”校验，不做物理量纲换算与单位等价判断。
- QC 复核的是图中数值声明与数据的一致性，不判断图型选择是否恰当、结论是否有统计意义。
- 中文标签依赖运行环境可用的中文字体（回退链含 PingFang SC、Noto Sans CJK SC 等）；缺字体时 PNG 中汉字可能显示为方块，但 manifest 中的文本不受影响。
- 单进程渲染，面向千行级 CSV 快照；超大表需先抽样或聚合再入图。
