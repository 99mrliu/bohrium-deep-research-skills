---
name: source-fidelity-firewall
description: 上游数据真实性/事实保真防火墙。对 W16 式分章节可编辑工作稿（Markdown 章节 + 可选材料/PDF）执行工单改写时，挖掘事实锚点、逐条回源定位生成证据映射，编辑后把关数字/缩写/[n]引文不得为材料外编造，最后按 case.json 的 output_contract 原子装配 result.json。适用于学位论文/长文档编辑类案例，尤其是任何进入改后文本的事实必须可回溯来源的场景。
---

# source-fidelity-firewall — 事实保真防火墙

## 1. 用途与触发条件

当任务要求对**分章节可编辑工作稿**执行改写/编辑工单，且交付物中的
事实（数字、单位、缩写、引文）必须可回溯到来源时使用本 Skill。
核心承诺：**任何进入改后文本的事实必须可回溯；任何编辑不得引入
材料外事实；引文逐字回源核验（由脚本重验，不信任人工声明）。**

脚本替你做的机械工作（你只做非机械判断）：
- `extract_facts.py`：机械挖出全部事实锚点，省去逐章人工找数字/引文。
- `ground_evidence.py`：机械逐条回源定位并自验，省去人工逐条比对材料。
- `fact_diff_guard.py`：机械判定改后文本是否引入材料外 token，退出码即闸门。
- `make_result.py`：机械按 output_contract 装配并原子写 result.json。

## 2. 输入契约（/input 布局）

```
/input/case.json                     # {"case_id", "task", "output_contract": {"fields": [...]}}
/input/task.md                       # 任务叙述（可选）
/input/organizer-edit-workorder.json # 实际编辑工单：{"items":[{"id","title","action","target","acceptance"}]}
/input/chapters/*.md                 # W16 分章节可编辑工作稿（= 编辑对象 + 事实底稿）
/input/materials/                    # 可选上游材料：.txt/.md 直读，.pdf 需 pdftotext
```

真实案例的 contract 字段集合以**实际 case.json 为准**；本 Skill 运行时
逐字段读取填充，不硬编码。

## 3. 工作流（按序执行；标注【脚本】/【模型】）

设 `S=/skills/weekly-skill`，工作目录 `/app/work`，交付目录 `/app/output`。

```bash
# 步骤0【模型】：读 /input/case.json 与 organizer-edit-workorder.json，
#   确认 output_contract.fields 与每条工单的 target/acceptance。
mkdir -p /app/work /app/output/edited_chapters

# 步骤1【脚本】：挖掘事实锚点 → facts.json
python3 $S/scripts/extract_facts.py --chapters /input/chapters \
  --out /app/work/facts.json

# 步骤2【脚本】：逐条回源定位 → evidence_map.json（材料缺失也可跑，见异常矩阵）
python3 $S/scripts/ground_evidence.py --facts /app/work/facts.json \
  --materials /input/materials --chapters /input/chapters \
  --out /app/work/evidence_map.json

# 步骤3【模型】：复制章节到 /app/output/edited_chapters/ 并在副本上执行工单编辑。
cp /input/chapters/*.md /app/output/edited_chapters/
#   编辑纪律（references/fact_grounding.md §6）：可重组语句，但不得创造
#   数字/单位/缩写/引文；每条工单编辑记入 /app/work/changes.json：
#   [{"id","title","target","before","after"}]

# 步骤4【脚本】：编辑后把关 → guard_report.json；退出码非零即有编造
python3 $S/scripts/fact_diff_guard.py --before /input/chapters \
  --after /app/output/edited_chapters --evidence /app/work/evidence_map.json \
  --materials /input/materials --out /app/work/guard_report.json
```

- 步骤4 退出码为 1 →【模型】读 guard_report.json 的 flags：
  `fabrication_token` = 改后文本出现材料外数字/缩写/引文，必须改回可
  回源表述或删除该论断；`unverified_new_sentence` = 新增含数字/引文
  句子无证据支撑，同样处理。修复后**重跑步骤4**直至 PASS。
  无法修复的论断：删除或原地标注 `【待确认：…】`（格式见
  references/fact_grounding.md §5）。
- 步骤4 退出码为 0 → 步骤5。

```bash
# 步骤5【脚本】：按 output_contract 装配并原子写 result.json
python3 $S/scripts/make_result.py --case /input/case.json \
  --evidence /app/work/evidence_map.json --guard /app/work/guard_report.json \
  --edited-chapters /app/output/edited_chapters \
  --changes /app/work/changes.json --out /app/output/result.json
cp /app/work/evidence_map.json /app/work/guard_report.json /app/output/
```

## 4. 输出契约

`/app/output/result.json` 必含：`case_id`、`status`、`sources`、
`uncertainty`、`change_records`、`problems`，以及 case.json
`output_contract.fields` 声明的**每一个字段**（未知字段填 null 并记入
problems）。字段填充规则（make_result.py 按字段名子串映射）：
`edited/chapter`→改后章节清单；`change`→变更记录；
`evidence/grounding`→evidence_map 路径+统计；`consistency/guard`→guard
摘要；`uncertainty`→未决事实清单；`source`→来源清单。

**诚实 partial 规则**：有任何 problems、guard 非 PASS、unresolved 事实
或【待确认】标注 → `status=partial` 并在 uncertainty 逐条列明。
**先存 partial 再改进**：时间紧张时，先跑步骤1+2+5（可跳过编辑，
changes.json 给空数组 `[]`，guard 传改前==改后或直接省略 --guard，
脚本会如实记 problems）保住可用 result.json，再回头做编辑与把关。

## 5. 异常矩阵

| 异常 | 降级路径 |
|-|-|
| 材料目录缺失/为空 | ground_evidence 自动降级：全部事实回退 `origin=working_chapters`，写 `CORPUS_MISSING` warning；make_result 记入 problems，status=partial，并在 result.json 中显式保留该告警 |
| 有 PDF 但无 pdftotext | 该 PDF 跳过并写 `PDF_UNREADABLE` warning → partial；不得编造 PDF 内容 |
| pdftotext 转换失败 | 同上，warning 含 stderr 摘要 |
| 引文/事实找不到来源（unresolved） | 换用可回源的引文，或删除该论断并在 changes.json 记录；必须保留时标 `【待确认：…】`，交付 partial |
| 工单 target 章节缺失 | 该 item 记入 changes.json 为 `{"id":…,"status":"skipped","reason":"target missing"}`，继续其余 item，status=partial |
| guard FAIL 且时间不足修复 | 保留 guard_report.json（FAIL），先存 partial result.json，再在剩余时间内逐条修 flag 重跑 guard |
| 时间不足（通用） | 立即执行"先存 partial"路径（见 §4），再增量改进 |

## 6. 依赖与文件清单

- 依赖：python3 标准库；唯一可选外部依赖 `pdftotext`（仅当材料含 PDF）。
- 文件清单：
  - `scripts/extract_facts.py` — 事实锚点挖掘 → facts.json
  - `scripts/ground_evidence.py` — 逐条回源定位+自验 → evidence_map.json
  - `scripts/fact_diff_guard.py` — 编辑后防编造把关 → guard_report.json（flag 即非零退出）
  - `scripts/make_result.py` — output_contract 装配，原子写 result.json
  - `references/fact_grounding.md` — 事实类型/定位策略/origin 语义/待确认格式/编辑纪律
  - `references/evidence_map.schema.json` — evidence_map 字段约定
  - `examples/synthetic/` — 合成示例（非正式案例结果），`run_example.sh` 一键跑通，
    演示 guard 捕获注入的材料外数字 92% 后修复至 PASS

## 7. 已知边界

- 只核验**表面 token 级**保真（数字/缩写/引文/带单位数值）；不判断
  论断的科学正确性，也不做语义级释义等价判断（改写后的同义句只要
  不含新 token 即视为可放行，语义审读仍是模型责任）。
- 单位表覆盖常见电化学/材料单位（见 extract_facts.py `UNITS`）；
  表外单位不会成为 `number_with_unit` 事实，但 guard 的数字闸仍覆盖
  一切数字 token。
- 回源匹配为空白折叠后的逐字包含：措辞被改写过的材料不会命中，该
  事实落为 working_chapters 底稿或 unresolved，属保守设计（宁多报
  uncertainty，不放过编造）。
- guard 对纯数字（无单位）只做 token 存在性校验，个位常见数字
  （如 "2"）几乎总在改前文本出现，约束力弱；重点防护对象是新引入的
  非常见数字、缩写与引文编号。
