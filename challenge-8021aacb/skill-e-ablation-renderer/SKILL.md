---
name: ablation-gain-renderer
description: |
  增益对照与结构可视化的诊断呈现管线（Ablation Evidence + Structure Map Rendering）。重心在验证与呈现两端：一端用零模型成本的机械消融基线与 Skill 诊断做同稿同口径对照，产出带诚实声明的增益报告（可核验率/可执行率/维度覆盖/严重度分级四项指标）；另一端把稿件解析成章节—论断—证据结构图，渲染为文本 SVG 与自包含 HTML 报告，让诊断的每个位置判断可视化可分发。
  触发：task.md 要求结构诊断且强调增益可验证、结果可核验可复核时。不触发：语言润色、科学内容裁决；可视化不替代文本证据。
  Trigger: honest internal ablation (mechanical baseline vs skill pass, same manuscript same metrics) plus text-format SVG/HTML structure maps for manuscript structural diagnosis. Not for: language polish, scientific-correctness adjudication.
---

# 消融增益渲染器（Ablation Gain Renderer）

## 0. 定位与差异化

本 Skill 的重心是**验证与呈现**，解决两个常被忽视的问题：

1. **增益无证据**：多数 Skill 只交结果，交不出「我比不用 Skill 好多少」的同稿对照。本管线内置零模型成本的机械基线（`base_pass.py`），同稿同口径跑双程，`gain_compare.py` 产出四项指标的对照报告——成本 <1 秒、不占 64 请求预算。
2. **判断无呈现**：文本诊断难以直观定位。`outline_graph.py` + `render_maps.py` 把稿件渲染成章节—论断—证据结构图（文本 SVG + 自包含 HTML），孤立论断以虚线框标出，提示人工复核位点。

两条纪律贯穿始终：基线**不代表平台基础 Agent**（报告带硬性声明）；`supports?` 边是可视化近似，不自动立案。

## 1. 运行时契约

| 项 | 约定 |
|---|---|
| 输入 | `/input/case.json`、`/input/task.md` 先读；`case.json.output_contract` 逐字段抄录到 result.json，不凭题目猜。 |
| 工作目录 | `/app/work`（结构图 JSON、基线诊断）。 |
| 最终交付 | `/app/output/result.json`（含 `case_id` 与全部契约字段）、`diagnosis.json`、`gain_report.md`、`structure_map.svg`、`report.html`。 |
| 预算 | 64 次模型请求 / 900 秒；基线与渲染均为脚本，零模型消耗。 |
| Skill 安装路径 | `/skills/weekly-skill`；路径不同时替换命令前缀。 |

## 2. 必需工作流（禁止跳步）

### 步骤 0 — 契约与 partial
读 case.json/task.md，立即写有效 partial result.json（`case_id` + 契约字段占位 + status=partial + uncertainty 起步）。把稿件存为 `/app/work/ms.md`（PDF 用 `pdftotext -layout`，不可读部分记 uncertainty）。

### 步骤 1 — 机械基线（先跑，防事后修饰）
```
python3 /skills/weekly-skill/scripts/base_pass.py /app/work/ms.md /app/work/base_diag.json
```
先跑基线再诊断，避免「看了答案再编基线」的嫌疑；基线文件归档不改。

### 步骤 2 — Skill 诊断（模型精读，六维全覆盖）
按任务要求完成六维结构诊断，finding 用统一 schema：`id/dimension/location/quote(逐字)/defect_class/action(操作动词+对象)/severity(high|medium|low)`；无缺陷维度写 `dimension_clearance` 带 `how_checked`。写入 `/app/output/diagnosis.json`。

### 步骤 3 — 结构图渲染
```
python3 /skills/weekly-skill/scripts/outline_graph.py /app/work/ms.md /app/work/graph.json
python3 /skills/weekly-skill/scripts/render_maps.py /app/work/graph.json /app/output/diagnosis.json /app/output
```
目检 `structure_map.svg`：章节顺序是否正确、虚线框孤立论断是否与人工判断一致；不一致时以人工判断为准并在 diagnosis 中说明（图只是提示）。

### 步骤 4 — 双程对照
```
python3 /skills/weekly-skill/scripts/gain_compare.py /app/work/base_diag.json /app/output/diagnosis.json /app/output/gain_report.md
```
保留报告顶部声明；指标低于基线的项如实保留。

### 步骤 5 — 收尾
填契约字段；`change_record` 记录诊断—渲染—对照三程的文件清单；status 规则：契约字段齐且六维有交代 → ok，否则 partial 点名缺项。

## 3. 异常处置

| 情况 | 处置 |
|---|---|
| 稿件无标题 | 结构图退化为论断/证据节点序列，照常渲染并注明 |
| 诊断 finding 为空 | 对照报告照出（基线 6 条 vs 0 条），dimension_clearance 必须齐全 |
| SVG 显示异常 | SVG 是文本：直接检查元素坐标；渲染脚本零依赖，失败即脚本 bug，修后重跑 |
| 预算不足 | 基线+渲染+对照全为脚本，最后补也只需 <1 分钟；优先保 diagnosis.json |

## 4. 自查清单

- [ ] base_diag.json 先于诊断生成且未修改
- [ ] gain_report.md 含「不代表平台基础 Agent」声明
- [ ] SVG/HTML 已目检，孤立论断提示与人工判断的关系已说明
- [ ] 六维 finding 或 clearance 齐全；severity 均为 high/medium/low
- [ ] result.json 契约字段齐、status 诚实

## 5. 最小示例

`examples/`：**合成示例**（非正式案例）。`bash examples/run_example.sh` 演示基线→诊断→渲染→对照全链；`expected/` 为真实跑出的示意输出（含 SVG 与 HTML，均为文本）。
