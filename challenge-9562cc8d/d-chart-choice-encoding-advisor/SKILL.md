---
name: chart-choice-encoding-advisor
description: 图表选型与编码决策优先的科研数据可视化：先用决策引擎把数据画像（类型、基数、偏度、样本量）与分析目的映射成可机读的图表决策——每个图件记录选定图型、编码映射（位置/长度/颜色/分面）、选择理由与被否决图型的否决理由，强制约束（无序类别禁饼图、条形零基线、右偏正值对数轴、色盲安全调色板），渲染严格按决策文件执行。Use when a case requires choosing appropriate chart types and visual encodings for research data with documented rationale (科研数据可视化, 图表选择, 编码方式, 对数轴决策, 饼图禁忌, 分面).
---

# 图表选型与编码决策：先决策、后渲染、决策留痕

## 适用场景

输入科研数据表与出图任务，要求图型与数据结构匹配、编码方式有依据、
被否决的图型说明原因。典型平台场景：`/input/case.json` +
`/input/task.md` + 数据文件，输出写入 `/app/output`。

## 运行契约（平台环境）

```bash
python3 /skills/weekly-skill/scripts/run_case.py \
    --case /input/case.json --input-dir /input \
    --work /app/work --out /app/output
```

- 一条命令跑完；统计完成后先由 `scripts/decide.py` 产出
  `/app/output/chart_decisions.json`（**决策文件是渲染的唯一依据**），
  渲染阶段严格遵循其中的对数轴与面板规则。
- `result.json` 自始以 `partial` 存在、逐阶段更新。
- 依赖：stdlib + numpy + matplotlib（缺失自动 pip 安装；失败交付
  决策与统计文本结果并标注）。

## 本 Skill 的重心：每个视觉选择都有可机读的理由

`chart_decisions.json` 对每个交付图件记录：

- **chosen**：选定图型与编码映射（x/y 位置、颜色、分面、标注）；
- **rationale**：为什么是它（数据类型 × 分析目的）；
- **rejected**：被否决的备选图型 + 否决理由——例如：
  - 饼图/环图 → 无序分类无构成语义，角度与面积编码夸大差异（强制禁止）；
  - dynamite plot（仅均值±误差条）→ 掩盖分布与样本量；
  - 气泡/面积编码 → 面积感知非线性；
  - 双 y 轴 → 相对尺度可任意调节，误导比较；
  - 3D 散点 → 透视失真；未固定色标的热图 → 跨图不可比。
- **panel_rule**：面板排序/取舍规则（分组比较按组间 F 统计量降序取
  前 8；散点按 |r| 降序取前 3 + 任务点名对）。

**全局强制约束**：无序类别禁饼图；条形一律零基线；Okabe-Ito 色盲安全；
类别 >12 个水平给出分面/合并建议（advisory）；右偏（偏度>1）且取值为
正的变量采用对数轴并在轴标注明"对数尺度"——决策连同偏度数值写入
`log_scale_decisions`。

## 决策驱动的渲染

清洗留痕 → 描述统计/分组统计/相关矩阵 → **decide.py 决策** → 按决策
渲染四张图（分布、分组箱线叠加散点、关键变量对散点、相关热图）→
中文图注（n、误差/须线含义、来源、清洗口径）→ 源数据复算校验
（`check_report.json`）。分组列自动识别（任务文本"按 X 分组"或 2–12
水平分类列）；无分组列时按偏斜协变量四分位分箱构造有序分组。

## 输出物（/app/output）

`result.json`（遵守 `output_contract`）、`chart_decisions.json`
（核心交付）、`check_report.json`、`statistics.json/md`、
`cleaning_report.json`、`figures.figdata.json`、`captions.md/json`、
`run_manifest.json`、图件 PNG/PDF/SVG。

## 异常与边界

- 决策引擎失败：记录 `uncertainty`，渲染回退内置默认规则（与决策
  规则同源），流水线不中断。
- 无 CJK 字体：英文图内标注 + 中文图注 + `uncertainty`。
- 不推荐即不画：被否决图型只出现在决策文件的 rejected 列表中。
- 不做统计推断与建模。

## 最小示例

`examples/` 为**合成示例**（模拟数据），按 `examples/README.md` 一条
命令端到端复现；预期文本输出（含 chart_decisions.json）在
`examples/expected_outputs/`。
